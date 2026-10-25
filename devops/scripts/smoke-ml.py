"""Verify actual LLM inference through the public authenticated API (not fallback)."""
import json
from uuid import uuid4

import httpx

with httpx.Client(base_url='http://nginx:8080', timeout=150, trust_env=False) as client:
    response = client.post('/api/v1/auth/register', json={
        'email': f'ml-smoke-{uuid4().hex}@example.com',
        'password': uuid4().hex + '!Aa1', 'full_name': 'ML Smoke',
    })
    response.raise_for_status()
    client.headers['Authorization'] = f"Bearer {response.json()['access_token']}"
    response = client.post('/api/v1/company/link', json={'inn': str(uuid4().int)[:10]})
    response.raise_for_status()
    response = client.post('/api/v1/company/score', json={
        'loan_amount': 1_000_000,
        'user_query': 'Нужен кредит на покупку оборудования. Что подходит нашей компании?',
    })
    assert response.is_success, f'{response.status_code}: {response.text}'
    result = response.json()
    assert result['ai_advice']['source'] == 'AI', result
    assert 0 <= result['risk_score'] <= 100
    assert result['ai_advice']['data']['explanation']
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print('OK: Nginx → authenticated backend → ML facade → Ollama/Qwen; source=AI')
