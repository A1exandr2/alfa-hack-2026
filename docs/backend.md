# Backend

Рекомендуемый запуск всего готового стека из корня: `make up`, затем `make check`. Swagger: http://localhost:8080/docs. Docker применяет миграции автоматически. Подробности: [DevOps](devops.md).

Ниже — альтернативный запуск Python на хосте. Не запускайте его одновременно с Docker-стеком на тех же портах.

## Требования

- Python 3.12 (версия Docker-образа);
- Docker для локального PostgreSQL;
- `curl` для ручной проверки или браузер со Swagger UI.

Все команды ниже выполняются из корня репозитория, если не указано иное.

## 1. Подготовить окружение

Создать виртуальное окружение и установить зависимости:

```bash
cd backend
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cd ..
```

Скопировать настройки:

```bash
cp .env.example .env
```

Файл `.env` не коммитить. Для локального запуска используются:

```text
DATABASE_URL=postgresql+asyncpg://credit:credit@localhost:55432/credit
JWT_SECRET=local-development-secret-change-me
JWT_EXPIRATION_MINUTES=60
```

Для общей или production-среды `JWT_SECRET` нужно заменить на собственный секрет.

## 2. Запустить PostgreSQL

Создать контейнер, если он запускается впервые:

```bash
docker run -d --name credit-postgres \
  -e POSTGRES_USER=credit \
  -e POSTGRES_PASSWORD=credit \
  -e POSTGRES_DB=credit \
  -p 55432:5432 \
  postgres:16-alpine
```

Если контейнер уже создан, запустить его:

```bash
docker start credit-postgres
```

Проверить состояние:

```bash
docker ps --filter name=credit-postgres
```

Внутри контейнера PostgreSQL использует порт `5432`, на хосте проекта — `55432`. Порт `5432` оставлен для уже установленного системного PostgreSQL.

## 3. Применить миграции

```bash
cd backend
.venv/bin/alembic upgrade head
```

Первая миграция создаёт таблицы:

- `companies`;
- `users`;
- `financials`;
- `alembic_version`.

Проверить текущую миграцию:

```bash
.venv/bin/alembic current
```

## 4. Запустить backend

Из папки `backend`:

```bash
.venv/bin/uvicorn app.main:app \
  --host 127.0.0.1 \
  --port 8080 \
  --reload
```

После запуска доступны:

- Swagger UI: http://127.0.0.1:8080/docs;
- OpenAPI JSON: http://127.0.0.1:8080/openapi.json;
- health-check: http://127.0.0.1:8080/api/v1/health.

Остановить backend: `Ctrl+C`.

## 5. Быстрая проверка health-check

В другом терминале:

```bash
curl http://127.0.0.1:8080/api/v1/health
```

Ожидаемый ответ:

```json
{
  "status": "ok",
  "service": "backend"
}
```

## 6. Ручная проверка регистрации, login и `/me`

Регистрация принимает ИНН. Backend автоматически находит компанию по ИНН или получает её данные через локальный Mock Gateway и создаёт компанию в PostgreSQL. Предварительно добавлять компанию SQL-командой не нужно.

### Регистрация

```bash
curl -X POST http://127.0.0.1:8080/api/v1/auth/register \
  -H 'Content-Type: application/json' \
  -d '{
    "email": "ivan@example.com",
    "password": "StrongPass123!",
    "full_name": "Иван Иванов",
    "inn": "7700000000"
  }'
```

Ожидаемый HTTP-код: `201`.

Ответ содержит пользователя и `access_token`:

```json
{
  "user": {
    "id": "uuid",
    "email": "ivan@example.com",
    "full_name": "Иван Иванов",
    "company_id": "uuid"
  },
  "access_token": "JWT",
  "token_type": "bearer"
}
```

Скопируйте значение `access_token` для следующих запросов. Не добавляйте JWT в git или публичные сообщения.

### Login

```bash
curl -X POST http://127.0.0.1:8080/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{
    "email": "ivan@example.com",
    "password": "StrongPass123!"
  }'
```

Ожидаемый HTTP-код: `200`. Login возвращает новый JWT.

### Текущий пользователь

Замените `YOUR_JWT_TOKEN` на токен из регистрации или login:

```bash
curl http://127.0.0.1:8080/api/v1/auth/me \
  -H 'Authorization: Bearer YOUR_JWT_TOKEN'
```

Ожидаемый HTTP-код: `200`.

### Проверка ошибок

Неверный пароль:

```bash
curl -i -X POST http://127.0.0.1:8080/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{
    "email": "ivan@example.com",
    "password": "WrongPass123!"
  }'
```

Ожидаемый код: `401`.

Запрос `/me` без токена должен вернуть `401`:

```bash
curl -i http://127.0.0.1:8080/api/v1/auth/me
```

Регистрация с тем же email должна вернуть `409`. ИНН должен содержать 10 или 12 цифр; иначе backend вернёт `422`.

## 7. Swagger UI

Открыть http://127.0.0.1:8080/docs.

1. Выполнить `POST /api/v1/auth/register` или `POST /api/v1/auth/login`.
2. Скопировать `access_token` из ответа.
3. Нажать `Authorize`.
4. Вставить сам JWT без префикса `Bearer` — Swagger добавит его автоматически.
5. Выполнить `GET /api/v1/auth/me`.

## 8. Автоматические тесты

Из папки `backend`:

```bash
.venv/bin/python -m pytest -q
```

Тесты используют локальную PostgreSQL и проверяют:

- хеширование паролей;
- регистрацию пользователя и автоматическое создание компании;
- login;
- JWT и `/auth/me`;
- модели и миграции;
- health-check и конфигурацию.

## 9. Остановка окружения

Остановить backend: `Ctrl+C` в терминале с Uvicorn.

Остановить PostgreSQL:

```bash
docker stop credit-postgres
```

Удалять контейнер необязательно. Для следующего запуска достаточно выполнить `docker start credit-postgres`.

## Текущие публичные endpoints

```text
GET  /api/v1/health
POST /api/v1/auth/register
POST /api/v1/auth/login
GET  /api/v1/auth/me
```

Endpoints компании, кредитных продуктов, заявок и решений будут добавляться следующими вертикальными срезами.
