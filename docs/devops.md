# CI и локальный runner

## CI

Конфигурация: `.github/workflows/ci.yml`. Репозиторий на GitHub, поэтому используется GitHub Actions. На локальном runner `credit-local` (labels: `self-hosted`, `Linux`, `X64`, `credit`) на push в main и PR из этого репозитория запускаются Gitleaks, Semgrep и Trivy зависимостей. Проверки написаны прямо в workflow, без промежуточных shell-скриптов.

Заготовки Maven, Python lint и Docker build/scan выключены. После появления кода включайте нужные repository variables в Settings → Secrets and variables → Actions → Variables:

- `ENABLE_JAVA_CI=true`: ожидается `backend/pom.xml`.
- `ENABLE_PYTHON_CI=true`: проверяется Python в `ml/`.
- `ENABLE_DOCKER_CI=true`: ожидаются рабочие `frontend/Dockerfile` и `backend/Dockerfile`.

AI-review удален. Проверки Alloy/Loki и старого проекта не добавлены: мониторинга еще нет. Deploy добавим после реализации приложения. Пока нет manifests зависимостей и исходников, SCA/SAST не подтверждают качество будущего кода.

Единственная команда Makefile — `make gitleaks`: локальная проверка истории на секреты через Docker.

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

Runner зарегистрирован владельцем, работает как systemd-служба и отображается в GitHub со статусом Idle. Из среды агента доступ к Docker заблокирован; фактический прогон CI проверяется после push.
