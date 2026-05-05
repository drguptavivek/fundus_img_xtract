COMPOSE ?= docker compose
TAIL ?= 200
SERVICES ?= web celery-ocr-worker celery-general-worker celery-beat
CELERY_SERVICES ?= celery-ocr-worker celery-general-worker celery-beat
BUILDERS ?= web-venv-builder ocr-venv-builder general-venv-builder beat-venv-builder
PYTEST_ARGS ?= tests/
FLASK_ARGS ?= --help
SCRIPT ?=
ARGS ?=
CACHE_PATTERN ?= fim:cache:*
MOBILE_PWA_DIR ?= static/mobile-pwa

WEB_UV = $(COMPOSE) exec -u $$(id -u):$$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache web uv run

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show available targets.
	@awk 'BEGIN {FS = ":.*##"; print "Usage: make <target> [VAR=value]"; print ""; print "Targets:"} /^[a-zA-Z0-9_.-]+:.*##/ {printf "  %-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

.PHONY: ps
ps: ## Show compose service status.
	$(COMPOSE) ps

.PHONY: up
up: ## Start the main application services in the background.
	$(COMPOSE) up -d $(SERVICES)

.PHONY: up-all
up-all: ## Start all compose services in the background.
	$(COMPOSE) up -d

.PHONY: down
down: ## Stop and remove containers without removing volumes.
	$(COMPOSE) down

.PHONY: stop
stop: ## Stop the main application services.
	$(COMPOSE) stop $(SERVICES)

.PHONY: start
start: ## Start previously stopped main application services.
	$(COMPOSE) start $(SERVICES)

.PHONY: restart
restart: ## Restart the main application services.
	$(COMPOSE) restart $(SERVICES)

.PHONY: restart-celery
restart-celery: ## Restart Celery worker and beat services.
	$(COMPOSE) restart $(CELERY_SERVICES)

.PHONY: restart-all
restart-all: ## Restart all running compose services.
	$(COMPOSE) restart

.PHONY: rebuild
rebuild: ## Build all compose images.
	$(COMPOSE) build

.PHONY: rebuild-main
rebuild-main: ## Build main application service images.
	$(COMPOSE) build $(SERVICES)

.PHONY: mobile-pwa-build
mobile-pwa-build: ## Build Flutter PWA into static/mobile-pwa for Flask /mobile/ serving.
	cd apps/fundus_glaucoma_mobile && flutter build web --release --base-href /mobile/ --dart-define=APP_VERSION=$$(grep '^version:' pubspec.yaml | awk '{print $$2}')
	rm -rf $(MOBILE_PWA_DIR)
	mkdir -p $(MOBILE_PWA_DIR)
	cp -R apps/fundus_glaucoma_mobile/build/web/. $(MOBILE_PWA_DIR)/

.PHONY: rebuild-builders
rebuild-builders: ## Build venv builder images.
	$(COMPOSE) build $(BUILDERS)

.PHONY: up-builders
up-builders: ## Stop app services, then run venv builders to refresh Python environments.
	$(COMPOSE) stop $(SERVICES)
	$(COMPOSE) up $(BUILDERS)

.PHONY: refresh-venvs
refresh-venvs: ## Stop app services, rebuild/run venv builders, then restart app services.
	$(COMPOSE) stop $(SERVICES)
	$(COMPOSE) build $(BUILDERS)
	$(COMPOSE) up $(BUILDERS)
	$(COMPOSE) up -d $(SERVICES)
	$(MAKE) clear-cache

.PHONY: logs
logs: ## Print last 200 log lines for all services. Override with TAIL=100.
	$(COMPOSE) logs --tail=$(TAIL)

.PHONY: logs-tail
logs-tail: ## Follow last 200 log lines for all services. Override with TAIL=100.
	$(COMPOSE) logs --tail=$(TAIL) -f

.PHONY: logs-main
logs-main: ## Print last 200 log lines for web and Celery services.
	$(COMPOSE) logs --tail=$(TAIL) $(SERVICES)

.PHONY: logs-main-tail
logs-main-tail: ## Follow last 200 log lines for web and Celery services.
	$(COMPOSE) logs --tail=$(TAIL) -f $(SERVICES)

.PHONY: logs-web
logs-web: ## Print last 200 web service log lines.
	$(COMPOSE) logs --tail=$(TAIL) web

.PHONY: logs-web-tail
logs-web-tail: ## Follow last 200 web service log lines.
	$(COMPOSE) logs --tail=$(TAIL) -f web

.PHONY: logs-celery logs-workers
logs-celery: ## Print last 200 Celery worker and beat log lines.
	$(COMPOSE) logs --tail=$(TAIL) $(CELERY_SERVICES)

logs-workers: logs-celery ## Alias for logs-celery.

.PHONY: logs-celery-tail logs-workers-tail
logs-celery-tail: ## Follow last 200 Celery worker and beat log lines.
	$(COMPOSE) logs --tail=$(TAIL) -f $(CELERY_SERVICES)

logs-workers-tail: logs-celery-tail ## Alias for logs-celery-tail.

.PHONY: logs-db
logs-db: ## Print last 200 database and cache log lines.
	$(COMPOSE) logs --tail=$(TAIL) db cache

.PHONY: logs-db-tail
logs-db-tail: ## Follow last 200 database and cache log lines.
	$(COMPOSE) logs --tail=$(TAIL) -f db cache

.PHONY: clear-cache
clear-cache: ## Clear Flask app Redis cache keys. Override with CACHE_PATTERN='fim:cache:public:*'.
	$(COMPOSE) exec -T cache sh -lc 'redis-cli -a "$$REDIS_PASSWORD" --scan --pattern "$(CACHE_PATTERN)" | xargs -r redis-cli -a "$$REDIS_PASSWORD" del'

.PHONY: logs-builders
logs-builders: ## Print last 200 venv builder log lines.
	$(COMPOSE) logs --tail=$(TAIL) $(BUILDERS)

.PHONY: logs-builders-tail
logs-builders-tail: ## Follow last 200 venv builder log lines.
	$(COMPOSE) logs --tail=$(TAIL) -f $(BUILDERS)

.PHONY: backup
backup: ## Run the host-based database backup script.
	python3 ./scripts/backup_db.py

.PHONY: alembic-head alembic-heads
alembic-head: alembic-heads ## Alias for alembic-heads.

alembic-heads: ## Run alembic heads inside the web container.
	$(WEB_UV) alembic heads

.PHONY: alembic-current
alembic-current: ## Run alembic current inside the web container.
	$(WEB_UV) alembic current

.PHONY: alembic-history
alembic-history: ## Run alembic history inside the web container.
	$(WEB_UV) alembic history

.PHONY: alembic-upgrade
alembic-upgrade: ## Run alembic upgrade head inside the web container.
	$(WEB_UV) alembic upgrade head

.PHONY: flask
flask: ## Run a Flask CLI command inside web. Usage: make flask FLASK_ARGS="routes".
	$(WEB_UV) flask $(FLASK_ARGS)

.PHONY: flask-routes
flask-routes: ## Run flask routes inside the web container.
	$(WEB_UV) flask routes

.PHONY: flask-limiter-limits
flask-limiter-limits: ## Show Flask-Limiter configured limits inside the web container.
	$(WEB_UV) flask limiter limits

.PHONY: flask-limiter-config
flask-limiter-config: ## Show Flask-Limiter configuration inside the web container.
	$(WEB_UV) flask limiter config

.PHONY: test
test: ## Start test-db, then run pytest inside web. Override with PYTEST_ARGS=tests/unit -v.
	$(COMPOSE) up -d test-db
	@echo "Waiting for test-db..."
	@i=0; while ! docker exec fundus-img-xtract-test-db pg_isready -U test_user -d fundus_test >/dev/null 2>&1; do \
		i=$$((i + 1)); \
		if [ $$i -ge 30 ]; then echo "test-db failed to become ready"; exit 1; fi; \
		sleep 1; \
	done
	$(WEB_UV) pytest $(PYTEST_ARGS)

.PHONY: script
script: ## Run a Python script inside web. Usage: make script SCRIPT=scripts/name.py ARGS="--flag".
	@test -n "$(SCRIPT)" || (echo 'Usage: make script SCRIPT=scripts/name.py ARGS="--flag"' && exit 2)
	$(WEB_UV) python $(SCRIPT) $(ARGS)

.PHONY: scripts
scripts: script ## Alias for script.

.PHONY: module
module: ## Run a Python module inside web. Usage: make module SCRIPT=scripts.create_user ARGS="admin".
	@test -n "$(SCRIPT)" || (echo 'Usage: make module SCRIPT=scripts.create_user ARGS="admin"' && exit 2)
	$(WEB_UV) python -m $(SCRIPT) $(ARGS)

.PHONY: shell
shell: ## Open a shell inside the web container.
	$(COMPOSE) exec web /bin/bash
