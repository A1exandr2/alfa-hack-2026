"""Create local settings once; never overwrite existing secrets."""
import os
from pathlib import Path
import secrets
from urllib.parse import quote

path = Path('.env')
try:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
except FileExistsError:
    print('.env уже существует, настройки сохранены')
else:
    template = Path('.env.example').read_text()
    values = {
        key: value
        for line in template.splitlines()
        if line and not line.lstrip().startswith('#') and '=' in line
        for key, value in [line.split('=', 1)]
    }
    postgres_password = secrets.token_hex(32)
    jwt_secret = secrets.token_hex(32)
    database_url = (
        'postgresql+asyncpg://'
        f"{quote(values['POSTGRES_USER'], safe='')}:{postgres_password}"
        f"@localhost:{values['POSTGRES_PORT']}/"
        f"{quote(values['POSTGRES_DB'], safe='')}"
    )
    replacements = {
        'POSTGRES_PASSWORD': postgres_password,
        'DATABASE_URL': database_url,
        'JWT_SECRET': jwt_secret,
    }
    lines = []
    for line in template.splitlines():
        key = line.partition('=')[0]
        if key in replacements:
            line = f'{key}={replacements[key]}'
        lines.append(line)
    with os.fdopen(fd, 'w') as stream:
        stream.write('\n'.join(lines) + '\n')
    print('Создан .env со случайными паролем PostgreSQL и JWT_SECRET')
