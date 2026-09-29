FROM ghcr.io/astral-sh/uv:0.10.3 AS uv

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    MIA_STANDARDS_ROOT=/app/standards/idta-submodel-templates \
    MIA_THREAD_STORE_PATH=/data/mia-agent.sqlite3 \
    MIA_WORKSPACE_ROOT=/data/workspaces

COPY --from=uv /uv /uvx /bin/

RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

RUN groupadd --system mia && \
    useradd --system --create-home --gid mia --home-dir /app mia && \
    mkdir -p /data && \
    chown mia:mia /data

WORKDIR /app

COPY backend/pyproject.toml backend/uv.lock ./backend/
RUN uv sync --project backend --no-dev --no-install-project

COPY backend/src ./backend/src
RUN uv sync --project backend --no-dev

COPY ["standards/idta-submodel-templates/published/Digital nameplate/3/0/1/IDTA 02006-3-0-1_Template_Digital Nameplate.json", "/app/standards/idta-submodel-templates/published/Digital nameplate/3/0/1/IDTA 02006-3-0-1_Template_Digital Nameplate.json"]
COPY ["standards/idta-submodel-templates/published/Technical_Data/2/0/1/IDTA 02003_2-0-1_Template_TechnicalData.json", "/app/standards/idta-submodel-templates/published/Technical_Data/2/0/1/IDTA 02003_2-0-1_Template_TechnicalData.json"]
COPY ["standards/idta-submodel-templates/published/Digital Product Passport/Digital Product Passport Part-1/1/0/1/IDTA 02099-1_Template Digital Product Passport - Part 1.json", "/app/standards/idta-submodel-templates/published/Digital Product Passport/Digital Product Passport Part-1/1/0/1/IDTA 02099-1_Template Digital Product Passport - Part 1.json"]
COPY ["standards/idta-submodel-templates/published/Carbon Footprint/1/0/1/IDTA 02023-1-0-1 _Template_CarbonFootprint.json", "/app/standards/idta-submodel-templates/published/Carbon Footprint/1/0/1/IDTA 02023-1-0-1 _Template_CarbonFootprint.json"]
COPY ["standards/idta-submodel-templates/published/Handover Documentation/2/0/1/IDTA 02004-2-0-1_Template_HandoverDocumentation.json", "/app/standards/idta-submodel-templates/published/Handover Documentation/2/0/1/IDTA 02004-2-0-1_Template_HandoverDocumentation.json"]
COPY ["standards/idta-submodel-templates/published/Maintenance Instructions/1/0/IDTA_02018_Template_MaintenanceInstructions.json", "/app/standards/idta-submodel-templates/published/Maintenance Instructions/1/0/IDTA_02018_Template_MaintenanceInstructions.json"]

USER mia

EXPOSE 8000

CMD ["sh", "-c", "exec /app/backend/.venv/bin/uvicorn mia_dpp.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
