"""Create local settings once; never overwrite existing secrets."""
import argparse
import os
from pathlib import Path
import secrets
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[2]
path = ROOT / '.env'
# The public example contains names only; runnable local defaults belong here.
DEFAULTS = {
    'COMPOSE_PROJECT_NAME': 'credit', 'APP_BIND': '127.0.0.1', 'APP_PORT': '8080',
    'POSTGRES_USER': 'credit', 'POSTGRES_DB': 'credit', 'POSTGRES_PORT': '55432',
    'JWT_EXPIRATION_MINUTES': '60', 'OLLAMA_MODEL': 'qwen3.5:4b', 'OLLAMA_TIMEOUT': '120',
    'DATA_MODE': 'real', 'ADMIN_LOGIN': 'Admin', 'ADMIN_EMAIL': 'admin@credit.test',
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fresh-local', action='store_true', help='Explicitly generate isolated development/CI secrets instead of decrypting deployment secrets')
    args = parser.parse_args()
    if path.exists():
        print('.env уже существует, настройки сохранены')
        return
    if (ROOT / 'secrets/server.enc.env').exists() and not args.fresh_local:
        raise SystemExit('Найден зашифрованный .env. Сначала выполните make secrets-decrypt; случайный .env не создан.')
    template = (ROOT / '.env.example').read_text()
    password = secrets.token_hex(32)
    replacements = dict(DEFAULTS, POSTGRES_PASSWORD=password, JWT_SECRET=secrets.token_hex(48), ADMIN_PASSWORD=secrets.token_urlsafe(30))
    replacements['DATABASE_URL'] = (
        f"postgresql+asyncpg://{quote(DEFAULTS['POSTGRES_USER'], safe='')}:{password}"
        f"@localhost:{DEFAULTS['POSTGRES_PORT']}/{quote(DEFAULTS['POSTGRES_DB'], safe='')}"
    )
    lines = [f'{key}={replacements.get(key, value)}' if '=' in line and not line.lstrip().startswith('#') else line
             for line in template.splitlines() for key, _, value in [line.partition('=')]]
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write('\n'.join(lines) + '\n')
    print('Создан .env со случайными паролем PostgreSQL и JWT_SECRET')


if __name__ == '__main__':
    main()
