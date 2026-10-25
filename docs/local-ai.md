# Локальная Qwen для сайта на VPS

Модель `qwen3.5:4b` работает в локальном Docker Ollama на NVIDIA GPU. На VPS модель и Ollama не устанавливаются. Для запросов приложения используется путь:

`backend → private Docker alias ollama → Unix socket → SSH → 127.0.0.1:11434 на компьютере → локальная Ollama`.

На компьютере `docker-compose.local-ai.yml` публикует порт Ollama только на loopback. Внешних портов для модели на VPS нет: SSH создаёт `/var/lib/credit-llm/socket/ollama.sock`, а мост `devops/local-ai/compose.yml` работает только во внутренней сети `credit_internal`. Мост не содержит модели, не пишет запросы/ответы в лог и ограничен восемью соединениями, 64 МБ RAM и 64 процессами/потоками.

## Установленное окружение

- VPS остаётся в `CREDIT_DEPLOY_MODE=core`; локальную серверную Ollama запускать не нужно. Docker alias `ollama` принадлежит мосту. Приложение использует существующие `OLLAMA_HOST=http://ollama:11434` и `OLLAMA_MODEL=qwen3.5:4b` для рекомендаций и разбора документов.
- На VPS пользователь `credit-llm-tunnel` имеет UID/GID 10002. Его ключ разрешает только обратное Unix-socket forwarding: shell, TTY, agent forwarding и X11 выключены настройками sshd; `PermitListen none` запрещает любые TCP listeners. В OpenSSH 9.6 нужен `AllowTcpForwarding remote` вместе с `PermitListen none`, поскольку `AllowTcpForwarding no` блокирует и Unix remote forwarding. Каталог socket имеет права 0700, сам socket — 0600.
- Серверные файлы моста находятся в `/opt/credit-local-ai`, служба — `credit-local-ai-bridge.service`. Она запускается после `credit.service` и Docker; контейнер имеет `restart: unless-stopped`.
- На компьютере туннель запускается пользовательской службой `credit-local-ai-tunnel.service`. Приватный ключ и pinned known_hosts находятся в `.local/secrets/local-ai/` и не входят в Git или deployment archive. Шаблон unit лежит в `devops/local-ai/credit-local-ai-tunnel.service.example`.

## Использование

```sh
make local-ai-up       # локальная GPU Ollama и туннель
make local-ai-status   # состояние туннеля и загруженной модели
make local-ai-stop     # закрыть доступ VPS к локальной модели
```

Туннель переподключается автоматически после разрыва сети. Модель работает, пока компьютер включён и доступен; пользовательская служба запускается после входа пользователя в систему. При недоступном компьютере мост возвращает HTTP 503, а приложение использует уже существующий fallback. Данные не переносятся на сторонний AI API.

## Проверка и сопровождение

`python3 devops/local-ai/test_proxy.py` проверяет реальный обмен байтами через TCP/Unix socket, недоступную модель и лимит соединений. Проверять AI нужно по `source=AI`, поскольку успешная HTTP-готовность сайта сама по себе проверяет API и базу, а не модель.

Обновление моста: перенесите `proxy.py` и `compose.yml` в `/opt/credit-local-ai` и перезапустите его службу. CD основного приложения сохраняет сеть `credit_internal`; мост работает отдельным Compose-проектом `credit-ai-bridge` и не заменяет immutable release приложения. Если меняется Compose project name приложения, обновите external network в конфигурации моста.
