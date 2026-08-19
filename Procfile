# O "release: flask db upgrade" abaixo funciona no Heroku/Railway, mas no
# Render o Pre-Deploy Command (equivalente a essa etapa "release") só está
# disponível em planos pagos — no plano gratuito ele nunca roda, e por isso
# a migration nunca era aplicada (tabelas como "users" nunca existiam no
# banco). Por isso o "web" abaixo já roda a migration antes do gunicorn,
# funcionando em qualquer plano. É seguro rodar em todo start: "flask db
# upgrade" não faz nada se o banco já estiver atualizado.
web: flask db upgrade && gunicorn wsgi:app -c gunicorn.conf.py
release: flask db upgrade
