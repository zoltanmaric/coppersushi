"""Exercise Ghost's dependency wiring with disposable systemd services."""

from pathlib import Path
import os
import re
import subprocess
import sys
import time
import uuid


def systemctl(*args):
    return subprocess.run(
        ["systemctl", *args], check=True, text=True, capture_output=True, timeout=20
    ).stdout.strip()


def main():
    if os.geteuid() != 0 or not Path("/run/systemd/system").is_dir():
        raise SystemExit("Run as root on a Linux host with systemd.")

    prefix = "ghost-recovery-" + uuid.uuid4().hex
    database = prefix + "-mysql.service"
    ghost = prefix + "-ghost.service"
    units = Path("/run/systemd/system")
    template = Path(__file__).parents[1] / "ansible/templates/ghost.service.j2"
    if len(sys.argv) > 1:
        template = Path(sys.argv[1])
    service = template.read_text().replace("{{ domain }}", "example.org")
    service = service.replace("mysql.service", database)
    # Keep the production dependency/install sections; substitute a harmless runtime.
    service = re.sub(
        r"\[Service\].*?(?=\[Install\])",
        "[Service]\nType=oneshot\nRemainAfterExit=yes\nExecStart=/bin/true\n\n",
        service,
        flags=re.S,
    )

    def expect_state(unit, expected):
        deadline = time.monotonic() + 10
        while True:
            actual = systemctl("show", "--property=ActiveState", "--value", unit)
            if actual == expected:
                return
            if time.monotonic() >= deadline:
                raise AssertionError(f"{unit}: expected {expected}, got {actual}")
            time.sleep(0.1)

    try:
        (units / database).write_text(
            "[Service]\nType=oneshot\nRemainAfterExit=yes\nExecStart=/bin/true\n"
        )
        # Begin with the old installation, then refresh links as deployment does.
        (units / ghost).write_text(
            re.sub(r"WantedBy=.*", "WantedBy=multi-user.target", service)
        )
        systemctl("daemon-reload")
        systemctl("enable", "--runtime", "--now", ghost)
        expect_state(ghost, "active")
        (units / ghost).write_text(service)
        systemctl("enable", "--runtime", ghost)
        systemctl("daemon-reload")

        systemctl("stop", database)
        expect_state(ghost, "inactive")
        systemctl("start", database)
        expect_state(ghost, "active")
        print("PASS: database stop/start recovers Ghost", flush=True)

        systemctl("restart", database)
        expect_state(ghost, "active")
        print("PASS: database restart recovers Ghost", flush=True)

        systemctl("stop", ghost)
        expect_state(ghost, "inactive")
        expect_state(database, "active")
        print("PASS: intentional Ghost stop stays stopped", flush=True)
    finally:
        # Cleanup also runs when a regression assertion fails.
        for args in [("disable", "--runtime", ghost), ("stop", ghost, database)]:
            subprocess.run(["systemctl", *args], capture_output=True, timeout=20)
        (units / ghost).unlink(missing_ok=True)
        (units / database).unlink(missing_ok=True)
        systemctl("daemon-reload")


if __name__ == "__main__":
    main()
