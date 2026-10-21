"""Exercise the public gateway and persist one uniquely named demo user."""
import json
from urllib.request import Request, urlopen
from uuid import uuid4

base = 'http://nginx:8080'

def request(path, payload=None, token=None):
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    data = json.dumps(payload).encode() if payload else None
    with urlopen(Request(base + path, data=data, headers=headers), timeout=10) as response:
        body = response.read()
        return json.loads(body) if 'application/json' in response.headers.get('Content-Type', '') else body

assert request('/api/v1/ready')['database'] == 'ok'
assert request('/api/v1/health')['status'] == 'ok'
assert request('/docs')
assert request('/openapi.json')['paths']
email = f'demo-{uuid4().hex}@example.com'
password = uuid4().hex + '!Aa1'
user = request('/api/v1/auth/register', {
    'email': email, 'password': password, 'full_name': 'Demo User',
    'inn': str(uuid4().int)[:10],
})
login = request('/api/v1/auth/login', {'email': email, 'password': password})
assert request('/api/v1/auth/me', token=login['access_token'])['id'] == user['user']['id']
print('OK: Nginx → API → PostgreSQL; health, readiness, Swagger, register, login, me')
print(f'Создан тестовый пользователь {email}; пароль и JWT не выводятся.')
