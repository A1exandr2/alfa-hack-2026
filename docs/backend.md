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

Создать локальный `.env` со случайными паролем PostgreSQL и JWT-ключом:

```bash
make init
```

Файл `.env` содержит локальные секреты и не коммитится. `.env.example` секретов не содержит; не копируйте его напрямую вместо `make init`.

## 2. Запустить PostgreSQL

Создать контейнер, если он запускается впервые:

```bash
docker run -d --name credit-postgres \
  --env-file .env \
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

Регистрация создаёт пользователя без привязки компании. После регистрации компания привязывается отдельным запросом по ИНН через интерфейс `CompanyProvider`; сейчас используется синтетический `DemoCompanyProvider`.

### Регистрация

```bash
curl -X POST http://127.0.0.1:8080/api/v1/auth/register \
  -H 'Content-Type: application/json' \
  -d '{
    "email": "ivan@example.com",
    "password": "StrongPass123!",
    "full_name": "Иван Иванов"
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
    "company_id": null
  },
  "access_token": "JWT",
  "token_type": "bearer"
}
```

Скопируйте значение `access_token` для следующих запросов. Не добавляйте JWT в git или публичные сообщения.

### Привязка компании

```bash
curl -X POST http://127.0.0.1:8080/api/v1/company/link \
  -H 'Authorization: Bearer YOUR_JWT_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{"inn": "7700000000"}'
```

Ответ содержит компанию с `data_source: "DEMO"`. После привязки её можно получить через `GET /api/v1/company`.

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

Регистрация с тем же email должна вернуть `409`. При привязке ИНН должен содержать 10 или 12 цифр; иначе backend вернёт `422`.

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
- регистрацию пользователя без компании и последующую привязку через demo provider;
- получение связанной компании;
- получение финансовых данных через demo provider с сохранением в PostgreSQL;
- частичное обновление финансовых данных и валидация значений;
- получение агрегированной кредитной истории через demo provider;
- список и карточку demo-кредитного продукта;
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
POST /api/v1/company/link
GET  /api/v1/company
GET  /api/v1/company/financials
PATCH /api/v1/company/financials
GET  /api/v1/company/credit-history
GET  /api/v1/credit-products
GET  /api/v1/credit-products/{product_id}
```

Заявки и решения будут добавляться следующими вертикальными срезами.
