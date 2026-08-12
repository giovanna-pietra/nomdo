"""
app/models/base.py
Mixin reutilizável com timestamps automáticos para todos os modelos.
"""

from datetime import datetime
from app.extensions import db


class TimestampMixin:
    """Adiciona created_at e updated_at automaticamente."""
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
