"""SOPS + age tooling. Never prints decrypted values or private key material."""
import argparse
import getpass
import re
import sys
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
KEY = ROOT / '.local/secrets/age/keys.txt'
ENCRYPTED = ROOT / 'secrets/server.enc.env'
ENV = ROOT / '.env'
CONFIG = ROOT / '.sops.yaml'


def run(args, **kwargs):
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs)
    if result.returncode:
        # Do not echo tool input, stdout or environment on an error.
        raise SystemExit(f'{Path(args[0]).name}: operation failed; check key, input and tool configuration')
    return result.stdout


def atomic_write(path, data, mode):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.'+path.name+'-', dir=path.parent)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def tool_env():
    env = os.environ.copy()
    if not env.get('SOPS_AGE_KEY_FILE') and KEY.exists():
        env['SOPS_AGE_KEY_FILE'] = str(KEY)
    return env


def encrypted_bytes(data):
    if not CONFIG.exists():
        raise SystemExit('First run: make secrets-key')
    return run(['sops', '--encrypt', '--config', str(CONFIG), '--filename-override',
                str(ENCRYPTED.relative_to(ROOT)), '--input-type', 'dotenv', '--output-type', 'dotenv', '/dev/stdin'],
               input=data, cwd=ROOT, env=tool_env())


def encrypt(source=ENV, destination=ENCRYPTED):
    # A private key is deliberately not needed for encryption (public recipient only).
    atomic_write(destination, encrypted_bytes(source.read_bytes()), 0o644)


def decrypt(source=ENCRYPTED):
    return run(['sops', '--decrypt', '--input-type', 'dotenv', '--output-type', 'dotenv', str(source)],
               cwd=ROOT, env=tool_env())


def values(data):
    return dict(line.split('=', 1) for line in data.decode().splitlines()
                if line and not line.lstrip().startswith('#') and '=' in line)


def set_secret(name, stdin=False):
    if not name:
        if not sys.stdin.isatty():
            raise SystemExit('Set NAME=VARIABLE_NAME when using stdin')
        name = input('Variable name: ').strip()
    if not re.fullmatch(r'[A-Z][A-Z0-9_]*', name) or name.startswith('SOPS_'):
        raise SystemExit('Use an uppercase environment variable name, without SOPS_ prefix')
    decoded = decrypt()
    if ENV.exists() and values(decoded) != values(ENV.read_bytes()):
        raise SystemExit('Local .env has unsaved changes; run make secrets-encrypt first')
    if stdin:
        value = sys.stdin.read()
        if value.endswith('\n'):
            value = value[:-1]
    else:
        if not sys.stdin.isatty():
            raise SystemExit('Hidden input needs a terminal; use secret-set-stdin for a pipe')
        value = getpass.getpass('Secret value (hidden): ')
    if any(c in value for c in ['\n','\r','\0']):
        raise SystemExit('Only single-line values are supported')
    # Compose dotenv: quote whitespace, escape slashes/quotes and prevent $ interpolation.
    quoted = '"' + value.replace('\\', '\\\\').replace('"', '\\"').replace('$', '$$') + '"'
    lines = decoded.decode().splitlines()
    replacement = name + '=' + quoted
    found = False
    for index, line in enumerate(lines):
        if line.partition('=')[0] == name:
            lines[index] = replacement
            found = True
    if not found:
        lines.append(replacement)
    updated = ('\n'.join(lines)+'\n').encode()
    encrypted = encrypted_bytes(updated)  # Fail before changing any files if encryption fails.
    example = ROOT / '.env.example'
    example_bytes = example.read_bytes()
    if name not in values(example_bytes):
        example_bytes += (('' if example_bytes.endswith(b'\n') else '\n')+name+'=\n').encode()
    atomic_write(ENCRYPTED, encrypted, 0o644)
    if ENV.exists():
        atomic_write(ENV, updated, 0o600)
    atomic_write(example, example_bytes, 0o644)
    print(f'Saved {name} encrypted; .env.example contains only its empty name.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['key', 'encrypt', 'decrypt', 'check', 'set'])
    parser.add_argument('--force', action='store_true', help='Allow replacing an existing local .env during decryption')
    parser.add_argument('--name', default=os.environ.get('SECRET_NAME'))
    parser.add_argument('--stdin', action='store_true', help='Read a value from stdin instead of hidden terminal input')
    args = parser.parse_args()
    if not shutil.which('sops') or not shutil.which('age-keygen'):
        raise SystemExit('Install sops and age first; see docs/secrets.md')
    if args.command == 'key':
        if KEY.exists() or CONFIG.exists():
            raise SystemExit('Key or configuration already exists; nothing was replaced')
        KEY.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        KEY.parent.chmod(0o700)
        run(['age-keygen', '-o', str(KEY)])
        KEY.chmod(0o600)
        recipient = run(['age-keygen', '-y', str(KEY)]).decode().strip()
        atomic_write(CONFIG, ("creation_rules:\n  - path_regex: 'secrets/.*\\.enc\\.env$'\n    age: '"+recipient+"'\n").encode(), 0o644)
        print('Created public .sops.yaml and private .local/secrets/age/keys.txt (0600). Back up the private key separately.')
    elif args.command == 'set':
        set_secret(args.name, args.stdin)
    elif args.command == 'encrypt':
        encrypt()
        print('Encrypted .env -> secrets/server.enc.env. Private key was not copied.')
    elif args.command == 'decrypt':
        if ENV.exists() and not args.force:
            raise SystemExit('.env already exists; use --force only if replacement is intended')
        atomic_write(ENV, decrypt(), 0o600)
        print('Decrypted secrets/server.enc.env -> .env (0600).')
    else:
        decoded = decrypt()
        if ENV.exists() and values(decoded) != values(ENV.read_bytes()):
            raise SystemExit('Encrypted environment differs from local .env')
        print('SOPS integrity verified; decrypted values match local .env.' if ENV.exists() else 'SOPS integrity verified.')


if __name__ == '__main__':
    main()
