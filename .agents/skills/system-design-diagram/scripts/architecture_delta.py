#!/usr/bin/env python3
"""Print changed README diagrams as a PR Architecture delta section."""
import argparse
from pathlib import PurePosixPath
import re
import subprocess
from urllib.parse import urljoin


def git(*args: str) -> str:
    return subprocess.check_output(['git', *args], text=True)


def diagrams(markdown: str) -> str:
    """Keep complete Mermaid fences, in document order."""
    return '\n\n'.join(re.findall(r'^```mermaid[^\n]*\n.*?^```[ \t]*$', markdown, re.M | re.S))


def snapshot(revision: str) -> dict[str, str]:
    paths = git('ls-tree', '-r', '--name-only', '-z', revision).split('\0')
    return {path: diagrams(git('show', f'{revision}:{path}'))
            for path in paths if PurePosixPath(path).name == 'README.md'}


def linked(diagram: str, path: str, revision: str, repository: str) -> str:
    """PR bodies need commit-specific links, not README-relative links."""
    source = f'{repository}/blob/{revision}/{path}'
    diagram = diagram.replace(f'{repository}/blob/main/', f'{repository}/blob/{revision}/')
    return re.sub(r'(\bclick\s+\w+\s+")([^"#]+)(")',
                  lambda match: match[1] + urljoin(source, match[2]) + match[3], diagram)


def section(before: dict[str, str], after: dict[str, str],
            base: str, head: str, repository: str) -> str:
    parts = ['## Architecture delta']
    for path in sorted(before.keys() | after.keys()):
        old, new = before.get(path, ''), after.get(path, '')
        if old == new:
            continue
        parts.extend([f'### {path}', '**Before**', linked(old, path, base, repository) or '_No diagram._',
                      '**After**', linked(new, path, head, repository) or '_No diagram._'])
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
    remote = git('remote', 'get-url', 'origin').strip().removesuffix('.git')
    repository = re.sub(r'^git@([^:]+):', r'https://\1/', remote)
    print(section(snapshot(base), snapshot(head), base, head, repository), end='')


if __name__ == '__main__':
    main()
