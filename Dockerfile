# ============================================================
# Dockerfile — StayKey (Flask + Gunicorn)
# Build:   docker build -t staykey .
# Run:     docker run -p 8000:8000 --env-file .env staykey
# ============================================================

# ── Base ─────────────────────────────────────────────────────
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependências do sistema (psycopg2 precisa de libpq)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

# ── Dependências Python ──────────────────────────────────────
FROM base AS deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Imagem final ─────────────────────────────────────────────
FROM deps AS final

# Copia o código
COPY . .

# Cria pastas necessárias
RUN mkdir -p static/uploads logs

# Usuário não-root para segurança
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser
RUN chown -R appuser:appgroup /app
USER appuser

EXPOSE 8000

# Aplica migrations e inicia o servidor
CMD ["sh", "-c", "flask db upgrade && gunicorn wsgi:app -c gunicorn.conf.py"]
