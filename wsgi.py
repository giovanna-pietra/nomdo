from dotenv import load_dotenv
load_dotenv()

from app import create_app, db # Importe o 'db' também
from app.models import User    # Importe seus modelos para o SQLAlchemy "conhecê-los"

app = create_app()

# --- ADICIONE ESTE BLOCO ---
with app.app_context():
    db.create_all()
# ---------------------------

if __name__ == "__main__":
    app.run(
    host="0.0.0.0",
    port=5000,
    debug=True
)