#!/usr/bin/env python3
"""Print changed README diagrams as a PR Architecture delta section."""
import argparse
from pathlib import PurePosixPath
import re
import subprocess


def git(*args: str) -> str:
    return subprocess.check_output(['git', *args], text=True)


def diagrams(markdown: str) -> str:
    """Keep complete Mermaid fences, in document order."""
    return '\n\n'.join(re.findall(r'^```mermaid[^\n]*\n.*?^```[ \t]*$', markdown, re.M | re.S))


def snapshot(revision: str) -> dict[str, str]:
    paths = git('ls-tree', '-r', '--name-only', '-z', revision).split('\0')
    return {path: diagrams(git('show', f'{revision}:{path}'))
            for path in paths if PurePosixPath(path).name == 'README.md'}


def section(before: dict[str, str], after: dict[str, str]) -> str:
    parts = ['## Architecture delta']
    for path in sorted(before.keys() | after.keys()):
        old, new = before.get(path, ''), after.get(path, '')
        if old == new:
            continue
        parts.extend([f'### {path}', '**Before**', old or '_No diagram._',
                      '**After**', new or '_No diagram._'])
    if len(parts) == 1:
        parts.append('None — README diagrams are unchanged.')
    return '\n\n'.join(parts) + '\n'


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', required=True, help="PR base branch, including the preceding layer of a stack")
    parser.add_argument('--head', default='HEAD', help='committed PR head (default: HEAD)')
    args = parser.parse_args()
    head = git('rev-parse', '--verify', f'{args.head}^{{commit}}').strip()
    base = git('merge-base', args.base, head).strip()
    print(section(snapshot(base), snapshot(head)), end='')


if __name__ == '__main__':
    main()
