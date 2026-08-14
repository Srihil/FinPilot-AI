"""
Database-agnostic JSON type.
Uses JSONB on PostgreSQL (indexed), falls back to JSON on SQLite (for tests).
"""
from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB
from sqlalchemy.types import TypeDecorator


class CompatibleJSON(TypeDecorator):
    """Uses PostgreSQL JSONB when available, JSON otherwise."""
    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_JSONB())
        return dialect.type_descriptor(JSON())
