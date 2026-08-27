"""Shared SQLAlchemy declarative base without application model imports."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base shared by the root and deep feature models."""
