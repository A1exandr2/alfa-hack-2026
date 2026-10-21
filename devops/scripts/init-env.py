"""Create local settings once; never overwrite existing secrets."""
import os
from pathlib import Path
import secrets

path = Path('.env')
try:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
except FileExistsError:
    print('.env уже существует, настройки сохранены')
else:
    with os.fdopen(fd, 'w') as stream:
        stream.write(Path('.env.example').read_text().replace(
            'local-development-secret-change-me', secrets.token_hex(32)))
    print('Создан .env со случайным JWT_SECRET')
