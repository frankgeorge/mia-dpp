SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.ONESHELL:
.DEFAULT_GOAL := help

UV ?= uv
BACKEND_PORT ?= 8000
FRONTEND_PORT ?= 3000
API_URL ?= http://127.0.0.1:$(BACKEND_PORT)
COMPOSE ?= docker compose
STANDARDS_DIR := standards/idta-submodel-templates
STANDARDS_COMMIT := a9664731a903b29ac5f45e23ab3a25c581f3d92f

.PHONY: help install refs refs-check backend frontend dev lint format typecheck \
	test build check docker-build up down smoke

help: ## Show the available commands.
	@awk 'BEGIN {FS = ":.*## "; print "MIA DPP commands\n"} /^[a-zA-Z0-9_.-]+:.*## / {printf "  %-14s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

refs: ## Initialize the pinned official IDTA template submodule.
	git submodule update --init --recursive $(STANDARDS_DIR)

refs-check:
	@test -f "$(STANDARDS_DIR)/README.md" || { \
		printf 'Missing standards checkout. Run: make refs\n' >&2; exit 1; \
	}
	actual="$$(git -C "$(STANDARDS_DIR)" rev-parse HEAD)"
	test "$$actual" = "$(STANDARDS_COMMIT)" || { \
		printf 'Expected IDTA templates at %s, found %s\n' "$(STANDARDS_COMMIT)" "$$actual" >&2; \
		exit 1; \
	}

install: refs ## Install the locked Python and frontend dependencies.
	$(UV) sync --project backend --locked --group dev
	npm ci

backend: ## Run the Python API at http://127.0.0.1:8000.
	$(UV) run --project backend --no-sync uvicorn mia_dpp.api:app \
		--reload --host 127.0.0.1 --port $(BACKEND_PORT)

frontend: ## Run only the Next.js interface.
	NEXT_PUBLIC_MIA_API_URL="$(API_URL)" \
		npm run dev -- --hostname 127.0.0.1 --port $(FRONTEND_PORT)

dev: ## Run the Python backend and Next.js frontend together.
	@$(UV) run --project backend --no-sync uvicorn mia_dpp.api:app \
		--host 127.0.0.1 --port $(BACKEND_PORT) &
	backend_pid=$$!
	trap 'kill "$$backend_pid" 2>/dev/null || true; wait "$$backend_pid" 2>/dev/null || true' EXIT INT TERM
	NEXT_PUBLIC_MIA_API_URL="$(API_URL)" \
		npm run dev -- --hostname 127.0.0.1 --port $(FRONTEND_PORT)

lint: ## Check Python and TypeScript style and Python formatting.
	cd backend
	$(UV) run --project . --no-sync ruff check src tests
	$(UV) run --project . --no-sync ruff format --check src tests
	cd ..
	npm run lint

format: ## Format Python source and tests.
	cd backend
	$(UV) run --project . --no-sync ruff format src tests

typecheck: ## Run strict Python and TypeScript type checking.
	cd backend
	$(UV) run --project . --no-sync mypy
	cd ..
	npm exec -- tsc --noEmit

test: refs-check ## Run the deterministic Python test suite.
	cd backend
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 $(UV) run --project . --no-sync pytest

build: ## Build the production frontend bundle.
	NEXT_PUBLIC_MIA_API_URL="$(API_URL)" npm run build

check: refs-check lint typecheck test build ## Run the complete local quality gate.
	$(COMPOSE) config --quiet

docker-build: ## Build the self-contained backend and frontend images.
	NEXT_PUBLIC_MIA_API_URL="$(API_URL)" $(COMPOSE) build

up: ## Start the production containers and wait for health checks.
	NEXT_PUBLIC_MIA_API_URL="$(API_URL)" $(COMPOSE) up -d --build --wait

down: ## Stop and remove the local production containers.
	$(COMPOSE) down

smoke: ## Start, probe, and always stop the production containers.
	@trap '$(COMPOSE) down' EXIT
	NEXT_PUBLIC_MIA_API_URL="$(API_URL)" $(COMPOSE) up -d --build --wait
	curl --fail --silent --show-error "$(API_URL)/health" >/dev/null
	curl --fail --silent --show-error "http://127.0.0.1:$(FRONTEND_PORT)/" >/dev/null
