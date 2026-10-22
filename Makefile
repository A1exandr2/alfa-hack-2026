.DEFAULT_GOAL := help
COMPOSE = docker compose --env-file .env
GPU_COMPOSE = $(COMPOSE) -f docker-compose.yml -f docker-compose.gpu.yml
SERVICE ?=
.PHONY: help init config build up down restart logs status stats test check migrate shell db-shell gitleaks
help:
	@echo 'make up / up-gpu — общий стек с Qwen (CPU / NVIDIA GPU)'
	@echo 'make up-core  — API без Ollama, рекомендации по запасным правилам'
	@echo 'make check-ml — сквозная проверка настоящего ответа LLM'
	@echo 'make down     — остановить стек, сохранив базу'
	@echo 'make status   — контейнеры, CPU/RAM, дисковое пространство'
	@echo 'make logs [SERVICE=backend] — следить за логами'
	@echo 'make test     — тесты с отдельной временной PostgreSQL'
	@echo 'make check    — проверить API, Swagger, регистрацию и login'
	@echo 'make build / config / restart / migrate / shell / db-shell / gitleaks'
init:
	@python3 devops/scripts/init-env.py
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
