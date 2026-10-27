#!/usr/bin/env python3
"""Restore a prepared, trusted Ghost 6 backup. Never accepts Ghost Admin JSON."""
import gzip
import pathlib
import shutil
import subprocess
import sys
import tarfile
import time

STAGING = pathlib.Path('/root/ghost-restore')
SITE = pathlib.Path('/var/www/121gigawatts')
ALLOWED_ROOTS = {'images', 'files', 'media', 'settings', 'themes', 'data', 'logs', 'public'}


def validate_archive(archive):
    for member in archive.getmembers():
        path = pathlib.PurePosixPath(member.name)
        if path.is_absolute() or '..' in path.parts:
            raise ValueError('Archive path escapes content directory')
        if not path.parts and member.isdir():
            continue
        if not path.parts or path.parts[0] not in ALLOWED_ROOTS:
            raise ValueError('Archive must contain content subdirectories, not a site root')
        if not (member.isfile() or member.isdir()):
            raise ValueError('Links and special files are not accepted')


def validate():
    with gzip.open(STAGING / 'database.sql.gz', 'rb') as stream:
        while stream.read(1024 * 1024):
            pass
    with tarfile.open(STAGING / 'content.tar.gz', 'r:gz') as archive:
        validate_archive(archive)


def validate_target():
    result = subprocess.run(
        ['mysql', '--batch', '--skip-column-names', '-e',
         "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='ghost_prod'"],
        check=True, capture_output=True, text=True)
    if result.stdout.strip() != '0':
        raise ValueError('Refusing to overwrite a nonempty database; take a backup and prepare an empty target explicitly')


def restore():
    validate_target()
    with gzip.open(STAGING / 'database.sql.gz', 'rb') as stream:
        process = subprocess.Popen(['mysql', 'ghost_prod'], stdin=subprocess.PIPE)
        try:
            shutil.copyfileobj(stream, process.stdin)
        finally:
            process.stdin.close()
        if process.wait() != 0:
            raise RuntimeError('MySQL import failed; Ghost remains stopped')
    content = SITE / 'content'
    previous = SITE / ('content.before-restore-' + str(time.time_ns()))
    content.rename(previous)
    content.mkdir(mode=0o755)
    with tarfile.open(STAGING / 'content.tar.gz', 'r:gz') as archive:
        archive.extractall(content, filter='data')
    subprocess.run(['chown', '-R', 'ghost:ghost', str(content)], check=True)
    # A restored browser session must not grant access on a new host.
    subprocess.run(['mysql', 'ghost_prod', '-e', 'TRUNCATE TABLE sessions;'], check=True)
    print('Restored. Prior content retained for recovery; verify owner login before cutover.')


if __name__ == '__main__':
    if sys.argv[1:] == ['validate-target']:
        validate()
        validate_target()
        print('Backups and empty target validated')
    elif sys.argv[1:] == ['restore']:
        restore()
    else:
        raise SystemExit('Usage: restore.py validate-target | restore')
