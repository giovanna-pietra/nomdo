"""
gunicorn.conf.py
Configuração do Gunicorn para produção.

Documentação: https://docs.gunicorn.org/en/stable/settings.html
"""

import multiprocessing
import os

# ── Workers ──────────────────────────────────────────────────
# Fórmula recomendada: (2 × núcleos_cpu) + 1
workers     = int(os.environ.get("WEB_CONCURRENCY", multiprocessing.cpu_count() * 2 + 1))
worker_class = "sync"          # use "gevent" para apps assíncronas
threads     = 2                # threads por worker

# ── Bind ─────────────────────────────────────────────────────
bind        = f"0.0.0.0:{os.environ.get('PORT', '8000')}"

# ── Timeouts ─────────────────────────────────────────────────
timeout          = 120         # worker reiniciado se não responder em 120s
keepalive        = 5           # segundos para aguardar próxima requisição
graceful_timeout = 30

# ── Logging ──────────────────────────────────────────────────
accesslog   = "-"              # stdout → coletado pelo Docker/systemd
errorlog    = "-"
loglevel    = os.environ.get("LOG_LEVEL", "info")
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)sµs'

# ── Processo ─────────────────────────────────────────────────
proc_name   = "staykey"
preload_app = True             # carrega app uma vez e faz fork → menos memória

# ── Segurança ─────────────────────────────────────────────────
limit_request_line   = 4094
limit_request_fields = 100
