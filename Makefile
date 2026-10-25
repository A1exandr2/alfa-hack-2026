.DEFAULT_GOAL := help
COMPOSE = docker compose --env-file .env
GPU_COMPOSE = $(COMPOSE) -f docker-compose.yml -f docker-compose.gpu.yml
SERVICE ?=
.PHONY: help init config build up down restart logs status stats test check migrate shell db-shell gitleaks
help:
	@echo 'make up / up-gpu — общий стек с Qwen (CPU / NVIDIA GPU)'
	@echo 'make up-core  — API без Ollama, рекомендации по запасным правилам'
	@echo 'make check-ml — сквозная проверка настоящего ответа LLM'
	@echo 'make local-ai-up / local-ai-status — локальная GPU Ollama и SSH-туннель к VPS'
	@echo 'make down     — остановить стек, сохранив базу'
	@echo 'make status   — контейнеры, CPU/RAM, дисковое пространство'
	@echo 'make logs [SERVICE=backend] — следить за логами'
	@echo 'make test     — тесты с отдельной временной PostgreSQL'
	@echo 'make check    — проверить API, Swagger, регистрацию и login'
	@echo 'make build / config / restart / migrate / shell / db-shell / gitleaks'
	@echo 'make secret-set NAME=VARIABLE — скрытый ввод и автоматическое шифрование'
	@echo 'make server-up / server-check / server-status — запуск из SOPS без .env'
init:
	@python3 devops/scripts/init-env.py $(INIT_ENV_ARGS)
config: init
	@$(COMPOSE) config --quiet
build: config
	$(COMPOSE) build backend
up-core: config
	$(COMPOSE) up -d --build --wait --wait-timeout 180
	@echo 'Стек запущен. Адрес и порт: .env (по умолчанию http://localhost:8080/docs)'
up: up-core
	$(COMPOSE) --profile llm up -d --wait ollama
	$(MAKE) model-pull
up-gpu: up-core
	$(GPU_COMPOSE) --profile llm up -d --wait ollama
	$(MAKE) model-pull
model-pull: init
	$(COMPOSE) exec -T ollama sh -ec 'ollama pull "$$OLLAMA_MODEL"'
check-ml: init
	$(COMPOSE) exec -T backend python - < devops/scripts/smoke-ml.py
down: init
	$(COMPOSE) --profile llm --profile test down --remove-orphans
restart: init
	$(COMPOSE) restart backend nginx
logs: init
	$(COMPOSE) --profile llm logs --tail=100 -f $(SERVICE)
status: init
	@$(COMPOSE) --profile llm ps -a
	@echo 'Запущено контейнеров проекта:'
	@$(COMPOSE) --profile llm ps --status running -q | wc -l
	@ids="$$($(COMPOSE) --profile llm ps --status running -q)"; if [ -n "$$ids" ]; then docker stats --no-stream $$ids; fi
	@echo 'Диск контейнеров проекта (SIZE — writable layer, без volumes):'
	@ids="$$($(COMPOSE) --profile llm ps -a -q)"; if [ -n "$$ids" ]; then for id in $$ids; do docker inspect --size --format '{{.Name}}: writable={{.SizeRw}} bytes, rootfs={{.SizeRootFs}} bytes' "$$id"; done; fi
	@echo 'Docker: суммарный диск ВСЕХ проектов (образы, volumes, build cache):'
	@docker system df
stats: status
test: config
	@$(COMPOSE) --profile test run --build --rm test; result=$$?; $(COMPOSE) --profile test stop test-db; $(COMPOSE) --profile test rm -f test-db; exit $$result
check: init
	$(COMPOSE) exec -T backend python - < devops/scripts/smoke.py
migrate: init
	$(COMPOSE) run --rm migrate
shell: init
	$(COMPOSE) exec backend sh
db-shell: init
	$(COMPOSE) exec postgres sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'
gitleaks:
	docker run --rm -v "$(CURDIR):/repo:ro" zricethezav/gitleaks:v8.18.2 detect --source=/repo --redact --verbose

.PHONY: up-core up-gpu model-pull check-ml

.PHONY: local-ai-up local-ai-status local-ai-stop
local-ai-up: config
	$(GPU_COMPOSE) -f docker-compose.local-ai.yml --profile llm up -d --no-deps ollama
	systemctl --user start credit-local-ai-tunnel.service
local-ai-status:
	systemctl --user status credit-local-ai-tunnel.service --no-pager
	$(COMPOSE) exec -T ollama ollama ps
local-ai-stop:
	systemctl --user stop credit-local-ai-tunnel.service

.PHONY: secrets-key secrets-encrypt secrets-decrypt secrets-check
secrets-key:
	python3 devops/scripts/sops-env.py key
secrets-encrypt:
	python3 devops/scripts/sops-env.py encrypt
secrets-decrypt:
	python3 devops/scripts/sops-env.py decrypt
secrets-check:
	python3 devops/scripts/sops-env.py check

.PHONY: admin-bootstrap
admin-bootstrap: config
	$(COMPOSE) --profile admin run --rm admin-bootstrap

# NAME is passed as environment data, never interpolated into shell code.
export SECRET_NAME = $(NAME)
.PHONY: secret-set secret-set-stdin server-check server-up server-stop server-status server-logs
secret-set:
	@python3 devops/scripts/sops-env.py set
secret-set-stdin:
	@python3 devops/scripts/sops-env.py set --stdin
server-check:
	@python3 devops/scripts/server-runtime.py check
server-up:
	@python3 devops/scripts/server-runtime.py up
server-stop:
	@python3 devops/scripts/server-runtime.py stop
server-status:
	@python3 devops/scripts/server-runtime.py status
server-logs:
	@python3 devops/scripts/server-runtime.py logs

.PHONY: server-package
server-package:
	@python3 devops/scripts/package-server.py

.PHONY: secret-add
secret-add: secret-set

.PHONY: dast-install dast-scan images-cleanup
# PRODUCTION_URL is read from the environment, not interpolated into shell source.
export PRODUCTION_URL
dast-install:
	@python3 devops/scripts/install-dast.py
dast-scan:
	@python3 devops/scripts/dast-scan.py
images-cleanup:
	@python3 devops/scripts/cleanup-images.py --apply

.PHONY: server-install
server-install:
	@python3 devops/scripts/install-server.py
