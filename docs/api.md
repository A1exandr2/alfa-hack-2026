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

Регистрация создаёт пользователя без компании. Привязка компании по ИНН выполняется отдельным запросом `POST /api/v1/company/link` после входа.

Запрос:

```json
{
  "email": "ivan@example.com",
  "password": "StrongPass123!",
  "full_name": "Иван Иванов"
}
```

Ответ `201 Created`:

```json
{
  "user": {
    "id": "00000000-0000-0000-0000-000000000010",
    "email": "ivan@example.com",
    "full_name": "Иван Иванов",
    "company_id": null
  },
  "access_token": "<jwt>",
  "token_type": "bearer"
}
```

Ошибки:

- `400 Bad Request` — некорректные данные;
- `409 Conflict` — пользователь с таким email уже существует;
- `422 Unprocessable Entity` — ошибка валидации данных запроса.

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
Authorization: Bearer ***
```

Ответ `200 OK`. До привязки компании поле `company_id` равно `null`; после привязки содержит UUID:

```json
{
  "id": "00000000-0000-0000-0000-000000000010",
  "email": "ivan@example.com",
  "full_name": "Иван Иванов",
  "company_id": null
}
```

Ошибки:

- `401 Unauthorized` — токен отсутствует, просрочен или недействителен;
- `404 Not Found` — пользователь из токена не найден.

## Компания

`POST /api/v1/company/link` привязывает компанию к текущему пользователю из JWT. Остальные endpoints раздела возвращают только данные связанной компании; передавать `company_id` в URL для MVP не требуется.

### Привязка компании

```http
POST /api/v1/company/link
Authorization: Bearer ***
Content-Type: application/json
```

Запрос:

```json
{
  "inn": "7700000000"
}
```

Backend ищет уже сохранённую компанию или запрашивает её через `CompanyProvider`. Сейчас подключён `DemoCompanyProvider`; он возвращает явно синтетическую запись. Ответ `200 OK` содержит данные компании и `data_source: "DEMO"`.

Ошибки:

- `401 Unauthorized` — токен отсутствует или недействителен;
- `409 Conflict` — у пользователя уже привязана другая компания;
- `422 Unprocessable Entity` — ИНН содержит не 10 или 12 цифр;
- `502 Bad Gateway` — провайдер компании недоступен или вернул данные с другим ИНН.

### Данные компании

```http
GET /api/v1/company
Authorization: Bearer <access_token>
```

Ответ `200 OK`:

```json
{
  "id": "00000000-0000-0000-0000-000000000001",
  "name": "Демо-компания 7700000000",
  "inn": "7700000000",
  "ogrn": null,
  "registration_date": null,
  "status": "ACTIVE",
  "director_name": null,
  "okved": null,
  "data_source": "DEMO"
}
```

Ошибки:

- `401 Unauthorized` — токен отсутствует или недействителен;
- `404 Not Found` — компания пользователя не найдена.

### Финансовые данные

Получение финансовых показателей. Если запись ещё не создана, Backend получает синтетические данные через `FinancialProvider`, сохраняет их в PostgreSQL и возвращает с `source: "DEMO"`. Повторные запросы читают сохранённую запись.

```http
GET /api/v1/company/financials
Authorization: Bearer <access_token>
```

Ответ `200 OK`:

```json
{
  "revenue_annual": 12500000.00,
  "profit_annual": 2100000.00,
  "expenses_annual": 10400000.00,
  "employees": 8,
  "current_debt": 800000.00,
  "updated_at": "2026-01-15T10:30:00Z",
  "source": "DEMO"
}
```

Частичное обновление показателей перед созданием заявки. В запрос включаются только изменяемые поля:

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
  "expenses_annual": 10700000.00,
  "employees": 9,
  "current_debt": 750000.00
}
```

Ответ `200 OK` возвращает полный объект. Обновляются `updated_at` и `source: "USER_VERIFIED"`.

Ограничения:

- денежные значения не могут быть отрицательными;
- `profit_annual` может быть отрицательным, если компания убыточна;
- число сотрудников не может быть отрицательным;
- пустой запрос, `null` вместо значения и неизвестные поля отклоняются;
- `422 Unprocessable Entity` — ошибка валидации данных.

### Кредитная история

```http
GET /api/v1/company/credit-history
Authorization: Bearer ***
```

Если агрегат ещё не сохранён, Backend запрашивает `CreditHistoryProvider`, сохраняет результат и возвращает его. Сейчас используется `DemoCreditHistoryProvider`; это синтетический агрегат, не реальные данные БКИ.

Ответ `200 OK`:

```json
{
  "active_credits": 2,
  "closed_credits": 5,
  "overdue_count": 0,
  "overdue_amount": 0.00,
  "updated_at": "2026-01-15T10:30:00Z",
  "source": "DEMO"
}
```

## Текущий статус реализации

Реализованы health-check, регистрация пользователя без компании, login, получение текущего пользователя по JWT, привязка и просмотр компании через `CompanyProvider`, GET/PATCH финансов через `FinancialProvider` и просмотр кредитной истории через `CreditHistoryProvider`. Demo-данные маркируются `DEMO`; финансовые показатели после редактирования — `USER_VERIFIED`. Следующие срезы — кредитные продукты и заявки.
