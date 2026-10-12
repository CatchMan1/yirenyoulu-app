#!/usr/bin/env python3
"""Conservative publication guard; diagnostics never print matched content.

Checks tracked/untracked non-ignored files, the index, and optionally every
reachable commit tree. This complements manual review; it cannot identify all
personal data or establish rights to assets.
"""
import argparse
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys

DENIED_SUFFIXES = {'.db', '.sqlite', '.sqlite3', '.sql', '.dump', '.backup',
                   '.p12', '.pfx', '.pem', '.key', '.cer', '.crt', '.csr', '.der',
                   '.jks', '.keystore', '.hap', '.app', '.hsp', '.har', '.zip',
                   '.7z', '.tar', '.gz', '.xlsx', '.xls', '.csv', '.heic', '.log'}
DENIED_PARTS = {'material', 'signing', 'signatures', 'node_modules', 'oh_modules',
                '.venv', 'venv', '__pycache__', '.hvigor', '.idea', 'logs', 'backups'}
PATTERNS = {
    'private-key': re.compile(rb'-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----'),
    'provider-token': re.compile(rb'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|sk-[A-Za-z0-9_-]{24,}|AKIA[A-Z0-9]{16})'),
    'credential-assignment': re.compile(rb'''(?im)["']?(?:api[_-]?key|secret[_-]?key|jwt[_-]?secret|storePassword|keyPassword|access_token|refresh_token)["']?\s*[:=]\s*["'][A-Za-z0-9_./+=-]{12,}["']'''),
    'database-credential': re.compile(rb'(?:postgres(?:ql)?|mysql)(?:\+[a-z0-9]+)?://[^\s:/]+:[^\s@]+@'),
}


def inspect_blob(name, content):
    path = PurePosixPath(name)
    reasons = []
    if (path.suffix.lower() in DENIED_SUFFIXES or set(path.parts) & DENIED_PARTS
            or (path.name.startswith('.env') and path.name != '.env.example')
            or path.name in {'local.properties', '.DS_Store'}):
        reasons.append('forbidden-path')
    if path.name == '.env.example':
        for line in content.decode('utf-8', errors='replace').splitlines():
            if line.lstrip().startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            if any(word in key.upper() for word in ('KEY', 'SECRET', 'TOKEN', 'PASSWORD', 'DATABASE_URL')) and value.strip():
                reasons.append('nonempty-sensitive-example')
    for rule, pattern in PATTERNS.items():
        if pattern.search(content):
            reasons.append(rule)
    if content.startswith(b'SQLite format 3\x00'):
        reasons.append('database-content')
    return sorted(set(reasons))


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.DEVNULL)


def scan(root, history=False):
    findings = set()
    names = git(root, 'ls-files', '-z', '--cached', '--others', '--exclude-standard').split(b'\0')
    for raw in names:
        if not raw:
            continue
        name = raw.decode('utf-8', errors='surrogateescape')
        path = root / name
        if path.is_symlink():
            findings.add(('worktree', name, 'symlink'))
        elif path.is_file():
            for reason in inspect_blob(name, path.read_bytes()):
                findings.add(('worktree', name, reason))
    # Read index blobs, not just the working copy: a secret can be staged then
    # removed from the working copy without updating the index.
    for raw in git(root, 'ls-files', '--stage', '-z').split(b'\0'):
        if not raw:
            continue
        meta, name_raw = raw.split(b'\t', 1)
        mode, oid, _stage = meta.split()
        name = name_raw.decode('utf-8', errors='surrogateescape')
        if mode in (b'120000', b'160000'):
            findings.add(('index', name, 'symlink-or-submodule'))
            continue
        for reason in inspect_blob(name, git(root, 'cat-file', 'blob', oid.decode())):
            findings.add(('index', name, reason))
    if history:
        commits = git(root, 'rev-list', '--all').decode().splitlines()
        seen = set()
        for commit in commits:
            for raw in git(root, 'ls-tree', '-rz', commit).split(b'\0'):
                if not raw:
                    continue
                meta, name_raw = raw.split(b'\t', 1)
                mode, kind, oid = meta.split()
                name = name_raw.decode('utf-8', errors='surrogateescape')
                key = (mode, oid, name)
                if key in seen:
                    continue
                seen.add(key)
                if mode in (b'120000', b'160000'):
                    findings.add(('history', name, 'symlink-or-submodule'))
                elif kind == b'blob':
                    for reason in inspect_blob(name, git(root, 'cat-file', 'blob', oid.decode())):
                        findings.add(('history', name, reason))
    return sorted(findings)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--history', action='store_true')
    args = parser.parse_args()
    try:
        findings = scan(args.root.resolve(), args.history)
    except (OSError, subprocess.CalledProcessError):
        print('ERROR: repository scan could not complete; publication blocked')
        return 2
    for scope, name, rule in findings:
        print(f'{scope}: {name!r}: {rule}')
    if findings:
        print(f'BLOCKED: {len(findings)} finding(s)')
        return 1
    print('PASS: publication guard found no configured-rule violations')
    return 0


if __name__ == '__main__':
    sys.exit(main())
