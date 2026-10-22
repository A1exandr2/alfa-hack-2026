.DEFAULT_GOAL := help
COMPOSE = docker compose --env-file .env
SERVICE ?=
.PHONY: help init config build up down restart logs status stats test check migrate shell db-shell gitleaks
help:
	@echo 'make up       — собрать и запустить PostgreSQL, миграции, API и Nginx'
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
up: config
	$(COMPOSE) up -d --build --wait --wait-timeout 180
	@echo 'Стек запущен. Адрес и порт: .env (по умолчанию http://localhost:8080/docs)'
down: init
	$(COMPOSE) --profile test down --remove-orphans
restart: init
	$(COMPOSE) restart backend nginx
logs: init
	$(COMPOSE) logs --tail=100 -f $(SERVICE)
status: init
	@$(COMPOSE) ps -a
	@echo 'Запущено контейнеров проекта:'
	@$(COMPOSE) ps --status running -q | wc -l
	@ids="$$($(COMPOSE) ps --status running -q)"; if [ -n "$$ids" ]; then docker stats --no-stream $$ids; fi
	@echo 'Диск контейнеров проекта (SIZE — writable layer, без volumes):'
	@ids="$$($(COMPOSE) ps -a -q)"; if [ -n "$$ids" ]; then for id in $$ids; do docker inspect --size --format '{{.Name}}: writable={{.SizeRw}} bytes, rootfs={{.SizeRootFs}} bytes' "$$id"; done; fi
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
