from dotenv import load_dotenv
load_dotenv()

from app import create_app, db # Importe o 'db' também
from app.models import User    # Importe seus modelos para o SQLAlchemy "conhecê-los"

app = create_app()

# db.create_all() foi removido daqui de propósito: ele cria as tabelas
# direto a partir dos models atuais, por fora do Flask-Migrate/Alembic.
# Isso conflita com "flask db upgrade" (usado no Procfile/deploy) — a
# migration tenta adicionar uma coluna que o create_all() já criou,
# e dá erro de "column already exists" num banco novo (Neon, Render, etc).
# O jeito certo de criar/atualizar as tabelas é sempre via migration:
#   flask db upgrade

if __name__ == "__main__":
    app.run(
    host="0.0.0.0",
    port=5000,
    debug=True
)