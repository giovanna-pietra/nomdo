"""
app/extensions.py
Instâncias das extensões Flask, criadas sem bind de app (Application Factory).
"""

from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from authlib.integrations.flask_client import OAuth

db = SQLAlchemy()
login_manager = LoginManager() # Instancie aqui para evitar circular imports
migrate = Migrate()
csrf    = CSRFProtect()
oauth   = OAuth()
