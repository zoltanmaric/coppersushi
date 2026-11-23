"""Generate numbered narration clips and their ElevenLabs character timings."""

import base64
import hashlib
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
AUDIO = HERE / "build" / "audio"
VOICE = "JBFqnCBsd6RMkjVDRZzb"
MODEL = "eleven_flash_v2_5"


def main():
    AUDIO.mkdir(parents=True, exist_ok=True)
    for index, paragraph in enumerate(
        (HERE / "narration.txt").read_text().strip().split("\n\n")
    ):
        clip = AUDIO / f"{index:02}.mp3"
        timing = clip.with_suffix(".json")
        fingerprint = hashlib.sha256(paragraph.encode()).hexdigest()
        if (
            clip.is_file()
            and timing.is_file()
            and json.loads(timing.read_text())["text_sha256"] == fingerprint
        ):
            continue
        request = Request(
            f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE}/with-timestamps",
            data=json.dumps({"text": paragraph, "model_id": MODEL}).encode(),
            headers={
                "xi-api-key": os.environ["ELEVENLABS_API_KEY"],
                "Content-Type": "application/json",
            },
        )
        with urlopen(request, timeout=45) as response:
            result = json.load(response)
        clip.with_suffix(".tmp").write_bytes(base64.b64decode(result["audio_base64"]))
        clip.with_suffix(".tmp").replace(clip)
        timing.write_text(
            json.dumps({"text_sha256": fingerprint, **result["alignment"]})
        )


if __name__ == "__main__":
    main()
