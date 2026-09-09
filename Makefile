UV ?= uv
BACKEND_PORT ?= 8000
FRONTEND_PORT ?= 3000

.PHONY: install backend dev test build check

install:
	$(UV) sync --project backend --group dev
	npm ci

backend:
	$(UV) run --project backend --no-sync \
		uvicorn mia_dpp.api:app --reload --port $(BACKEND_PORT)

dev:
	@set -u; \
	$(UV) run --project backend --no-sync \
		uvicorn mia_dpp.api:app --port $(BACKEND_PORT) & \
	backend_pid=$$!; \
	trap 'kill "$$backend_pid" 2>/dev/null || true' EXIT; \
	NEXT_PUBLIC_MIA_API_URL=http://127.0.0.1:$(BACKEND_PORT) \
		npm run dev -- --hostname 127.0.0.1 --port $(FRONTEND_PORT); \
	frontend_status=$$?; \
	exit "$$frontend_status"

test:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 $(UV) run --project backend --no-sync \
		pytest -c backend/pyproject.toml backend/tests

build:
	npm run build

check: test build
