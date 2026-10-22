"""Exercise the public gateway and persist one uniquely named demo user."""
import httpx
from uuid import uuid4

base = 'http://nginx:8080'

def request(path, payload=None, token=None):
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    # Fixed Docker service origin; no file:// support or redirect following.
    with httpx.Client(base_url=base, timeout=10, follow_redirects=False, trust_env=False) as client:
        response = client.request(
            'POST' if payload is not None else 'GET', path,
            json=payload, headers=headers,
        )
        response.raise_for_status()
        return response.json() if 'application/json' in response.headers.get('Content-Type', '') else response.content

assert request('/api/v1/ready')['database'] == 'ok'
assert request('/api/v1/health')['status'] == 'ok'
assert request('/docs')
assert request('/openapi.json')['paths']
email = f'demo-{uuid4().hex}@example.com'
password = uuid4().hex + '!Aa1'
user = request('/api/v1/auth/register', {
    'email': email, 'password': password, 'full_name': 'Demo User',
})
login = request('/api/v1/auth/login', {'email': email, 'password': password})
assert request('/api/v1/auth/me', token=login['access_token'])['id'] == user['user']['id']
print('OK: Nginx → API → PostgreSQL; health, readiness, Swagger, register, login, me')
print(f'Создан тестовый пользователь {email}; пароль и JWT не выводятся.')
