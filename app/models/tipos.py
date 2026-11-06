"""Tipos de coluna próprios."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.types import TypeDecorator


def agora_utc() -> datetime:
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """Data e hora sempre em UTC, com fuso, nos dois bancos.

    O SQLite não guarda o fuso: gravamos em UTC e devolvemos com `tzinfo=UTC`, como o Postgres faz.
    Datas sem fuso são recusadas, para nunca misturar horário local com UTC.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("datetime sem fuso horário; use datetime com tzinfo (UTC)")
        return value.astimezone(timezone.utc)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


def render_item(tipo, obj, _contexto):
    """Hook do Alembic: grava `UTCDateTime` como `sa.DateTime(timezone=True)` nas migrações.

    O DDL é idêntico, e a migração fica autossuficiente (não importa código da aplicação).
    """
    if tipo == "type" and isinstance(obj, UTCDateTime):
        return "sa.DateTime(timezone=True)"
    return False
