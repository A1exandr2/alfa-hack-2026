# Инфраструктура и запуск

## Локальное окружение

Требуются Docker Engine, Compose v2+ с поддержкой `--wait`, GNU Make и Python 3. Из корня выполните `make up`. При первом запуске скачиваются образы и Python-зависимости.

Стек: Nginx → FastAPI → PostgreSQL. Одноразовый сервис `migrate` выполняет `alembic upgrade head` после готовности PostgreSQL; backend запускается только после успешных миграций, Nginx — после готовности backend. Frontend пока отсутствует, корень сайта перенаправляет в Swagger.

Backend собирается в несколько стадий: сборка wheels → установка в runtime → отдельная тестовая стадия → production. В runtime нет компилятора, исходники тестов находятся только в тестовом образе. Процесс работает под UID 10001, с read-only filesystem, временным `/tmp`, без Linux capabilities и с лимитом RAM 512 MiB. Docker init пересылает сигналы и убирает дочерние процессы.

PostgreSQL и backend находятся в сети `internal`, Nginx дополнительно подключён к `edge`. Backend не публикует порт на хост. PostgreSQL дополнительно подключён к сети `database-access`, чтобы публиковать порт только на loopback для разработки на хосте. Данные сохраняются в volume `credit_postgres_data` (имя зависит от `COMPOSE_PROJECT_NAME`).

Nginx сохраняет пути `/api/v1`, `/docs`, `/openapi.json`, повторно разрешает Docker DNS после пересоздания backend. `/api/v1/health` проверяет процесс; `/api/v1/ready` выполняет `SELECT 1` в PostgreSQL и возвращает 503 при недоступности базы. Docker healthchecks проверяют готовность через БД. Unhealthy сам по себе не перезапускает контейнер; restart policy срабатывает при завершении процесса.

## Команды

| Команда | Действие |
| --- | --- |
| `make init` | Создать `.env` с правами 0600 и случайным JWT-ключом, если файла ещё нет |
| `make config` | Проверить Compose без вывода секретов |
| `make up` | Собрать и запустить стек, дождаться готовности |
| `make down` | Удалить контейнеры и сети, сохранить данные |
| `make build` | Собрать backend |
| `make restart` | Перезапустить backend и Nginx без применения новых env/build |
| `make logs SERVICE=backend` | Логи выбранного сервиса; без SERVICE — всех |
| `make status` / `make stats` | Состояние, число работающих контейнеров, CPU/RAM и writable layers проекта; общий Docker-диск всех проектов |
| `make check` | HTTP smoke через Nginx: health, readiness, Swagger, register, login, me |
| `make test` | Существующие pytest-тесты и миграции в отдельной временной PostgreSQL |
| `make migrate` | Применить миграции вручную |
| `make shell` / `make db-shell` | Shell backend / psql |
| `make gitleaks` | Проверка истории Git на секреты |

Smoke создаёт одного уникального пользователя в рабочей локальной БД при каждом запуске. Пароли и JWT не печатаются. Тестовая БД хранится в tmpfs и удаляется после тестов; тесты не обращаются к рабочей базе.

`make status` показывает размер writable layers, который не включает volumes. `docker system df` в конце — суммарная статистика Docker на компьютере, включая образы, volumes и build cache других проектов. Команды очистки автоматически не выполняются.

## Переменные и демонстрация

`.env.example` содержит только несекретные настройки и пустые поля для секретов. `make init` создаёт `.env` с правами 0600 и случайными паролями PostgreSQL и JWT; существующий файл не изменяется. Секреты не попадают в образ, Git или пример конфигурации. Compose передаёт backend URL с именем сервиса `postgres:5432`; `DATABASE_URL` в `.env` нужен для запуска Python вне Docker.

- `APP_PORT=8080`, `APP_BIND=127.0.0.1`: внешний адрес Nginx.
- `POSTGRES_PORT=55432`: локальный порт PostgreSQL.
- `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`: начальные настройки БД.
- `JWT_SECRET`, `JWT_EXPIRATION_MINUTES`: подпись и срок JWT.

Пароль БД по умолчанию предназначен для локальной разработки. Для показа по локальной сети задайте `APP_BIND=0.0.0.0`, собственные пароли и JWT-ключ, ограничьте доступ на хосте, выполните `make up`. TLS и production deploy пока не настроены. Изменение POSTGRES_* не перенастраивает уже созданную БД: PostgreSQL использует их только при первой инициализации volume. При смене пароля обновляйте его также в самой БД. В URL пароли с зарезервированными символами требуют percent-encoding; для этого базового окружения используйте буквы, цифры и дефисы.

Если порт занят старым контейнером или локальным сервером, измените порт в `.env`. Старые контейнеры и данные автоматически не удаляются. При ошибке миграций смотрите `make logs SERVICE=migrate`, исправьте причину и повторите `make up`.

SOPS + age отложены по договорённости. GraalVM относится к другим runtime; для текущего Python/FastAPI приложения его сборка не требуется. Прямые Python-зависимости закреплены в `backend/requirements.txt`, транзитивные — в `backend/requirements.lock` (Python 3.12/Linux). Docker использует lock как constraints; обновляйте оба файла вместе и прогоняйте `make test`. Теги базовых образов закреплены по версиям, но не по digest.

## CI

Конфигурация: `.github/workflows/ci.yml`. Существующие Gitleaks, Semgrep и Trivy оставлены. Добавлен Docker job: проверка Compose, сборка стека, pytest в изолированной БД, HTTP smoke и очистка контейнеров. CI использует отдельное имя Compose-проекта и динамические host-порты, чтобы не затронуть локальную демонстрацию.

Старые заготовки Maven и ML lint остаются выключенными через repository variables. Опциональные Checkov/build-and-scan проверяют только готовый backend; frontend Dockerfile пока пустой. Автоматическая публикация и deploy отсутствуют; их стоит настроить после выбора сервера. Проверки запускаются на PR из этого репозитория, push в любую ветку и вручную. Чужие fork PR не запускаются на локальном runner.

## Что проверяют security jobs

- Gitleaks ищет случайно закоммиченные секреты в истории Git. Успех не означает отсутствие уязвимых зависимостей.
- Semgrep проверяет шаблоны ошибок в коде и конфигурации. В `nginx.conf` точечно исключено правило `missing-internal`: это публичный reverse proxy с фиксированным upstream `backend:8080`, без клиентского управления адресом. Директива `internal` здесь блокировала бы API и Swagger. Исключение пересмотреть, если upstream начнёт зависеть от запроса клиента.
- Trivy сверяет зависимости с базой известных CVE. PyJWT обновлён с 2.10.1 до 2.14.0 в requirements и lock по результатам отчёта. При новых CVE обновляйте зависимости и повторяйте тесты; порог HIGH/CRITICAL не отключён.
- Docker integration tests проверяет сборку и рабочие сценарии, а не заменяет security jobs.

## Регистрация GitHub runner на своем компьютере

1. Откройте https://github.com/A1exandr2/credit/settings/actions/runners/new . Выберите Linux / x64.
2. В своем терминале создайте папку вне репозитория:

   ```bash
   mkdir -p ~/actions-runner-credit
   cd ~/actions-runner-credit
   ```

3. Выполните команды Download со страницы GitHub, включая проверку контрольной суммы. Версия и SHA256 указаны на странице.
4. Выполните оттуда команду `./config.sh --url ... --token ...`. Это временный registration token, не PAT и не пароль. В дополнительных labels укажите `credit`; остальные ответы можно оставить стандартными. Токен и папку runner не коммитьте.
5. Запустите `./run.sh`. В GitHub должен появиться runner со статусом Idle. Терминал должен оставаться открытым.
6. Для автозапуска вместо foreground-процесса: остановите `run.sh` через Ctrl+C, затем в папке runner выполните:

   ```bash
   sudo ./svc.sh install "$USER"
   sudo ./svc.sh start
   sudo ./svc.sh status
   ```

Runner для Docker-задач должен иметь доступ к Docker: `docker info` должен работать от пользователя службы. Если пользователь еще не в группе docker, добавьте его через `sudo usermod -aG docker "$USER"`, затем перелогиньтесь и перезапустите службу. Группа docker дает административные возможности на хосте.

Чтобы отправить job на этот runner, укажите `runs-on: [self-hosted, Linux, X64, credit]`. Все текущие jobs уже настроены на локальный runner. PR из чужих fork отключены на уровне условий jobs. Не запускайте на своем компьютере jobs из чужих PR.

Документация: https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/add-runners

Runner зарегистрирован владельцем, работает как systemd-служба и отображается в GitHub со статусом Idle. Фактический прогон GitHub Actions проверяется после push.
