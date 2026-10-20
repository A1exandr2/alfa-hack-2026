# API-контракт

Документ фиксирует первый небольшой слой REST API проекта. Реализация будет добавляться в `backend/` постепенно.

## Общие правила

- Базовый префикс: `/api/v1`.
- Формат запросов и ответов: `application/json`.
- Идентификаторы сущностей: UUID в виде строки.
- Время: ISO 8601 в UTC.
- Защищённые endpoints используют заголовок:

```http
Authorization: Bearer <access_token>
```

Успешный ответ возвращает HTTP-код `2xx`. Ошибка возвращается в едином формате:

```json
{
  "detail": "Описание ошибки"
}
```

## Системные endpoints

### Проверка доступности backend

```http
GET /api/v1/health
```

Ответ `200 OK`:

```json
{
  "status": "ok",
  "service": "backend"
}
```

## Авторизация

### Регистрация тестового пользователя

```http
POST /api/v1/auth/register
Content-Type: application/json
```

Запрос:

```json
{
  "email": "ivan@example.com",
  "password": "StrongPass123!",
  "full_name": "Иван Иванов",
  "company_id": "00000000-0000-0000-0000-000000000001"
}
```

Ответ `201 Created`:

```json
{
  "user": {
    "id": "00000000-0000-0000-0000-000000000010",
    "email": "ivan@example.com",
    "full_name": "Иван Иванов",
    "company_id": "00000000-0000-0000-0000-000000000001"
  },
  "access_token": "<jwt>",
  "token_type": "bearer"
}
```

Ошибки:

- `400 Bad Request` — некорректные данные;
- `409 Conflict` — пользователь с таким email уже существует;
- `404 Not Found` — указанная компания не найдена.

### Вход

```http
POST /api/v1/auth/login
Content-Type: application/json
```

Запрос:

```json
{
  "email": "ivan@example.com",
  "password": "StrongPass123!"
}
```

Ответ `200 OK` имеет тот же формат, что и успешная регистрация.

Ошибки:

- `401 Unauthorized` — неверный email или пароль;
- `422 Unprocessable Entity` — ошибка валидации запроса.

### Текущий пользователь

```http
GET /api/v1/auth/me
Authorization: Bearer <access_token>
```

Ответ `200 OK`:

```json
{
  "id": "00000000-0000-0000-0000-000000000010",
  "email": "ivan@example.com",
  "full_name": "Иван Иванов",
  "company_id": "00000000-0000-0000-0000-000000000001"
}
```

Ошибки:

- `401 Unauthorized` — токен отсутствует, просрочен или недействителен;
- `404 Not Found` — пользователь из токена не найден.

## Компания

Все endpoints раздела работают только с компанией пользователя из JWT. Передавать `company_id` в URL для MVP не требуется.

### Данные компании

```http
GET /api/v1/company
Authorization: Bearer <access_token>
```

Ответ `200 OK`:

```json
{
  "id": "00000000-0000-0000-0000-000000000001",
  "name": "ООО «Ромашка»",
  "inn": "7700000000",
  "ogrn": "1027700000000",
  "registration_date": "2015-04-20",
  "status": "ACTIVE",
  "director_name": "Иван Иванов",
  "okved": "62.01"
}
```

Ошибки:

- `401 Unauthorized` — токен отсутствует или недействителен;
- `404 Not Found` — компания пользователя не найдена.

### Финансовые данные

Получение сохранённых финансовых показателей:

```http
GET /api/v1/company/financials
Authorization: Bearer <access_token>
```

Ответ `200 OK`:

```json
{
  "revenue_annual": 12500000.00,
  "profit_annual": 2100000.00,
  "current_debt": 800000.00,
  "updated_at": "2026-01-15T10:30:00Z",
  "source": "USER_VERIFIED"
}
```

Обновление показателей перед созданием заявки:

```http
PATCH /api/v1/company/financials
Authorization: Bearer <access_token>
Content-Type: application/json
```

Запрос может содержать только изменяемые поля:

```json
{
  "revenue_annual": 13000000.00,
  "profit_annual": 2300000.00,
  "current_debt": 750000.00
}
```

Ответ `200 OK` возвращает полный объект финансовых данных с обновлённым `updated_at` и `source: "USER_VERIFIED"`.

Ограничения:

- денежные значения не могут быть отрицательными;
- `profit_annual` может быть отрицательным, если компания убыточна;
- неизвестные поля отклоняются;
- `422 Unprocessable Entity` — ошибка валидации данных.

## Ограничение текущего этапа

На этом этапе описаны контракты авторизации, данных компании и финансовых данных. Реализация, модели базы данных и следующие endpoints будут добавляться отдельными небольшими изменениями.
