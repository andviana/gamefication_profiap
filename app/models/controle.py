"""Tabelas de controle: contadores de tentativas falhas e prévias de importação."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db
from app.models.tipos import UTCDateTime, agora_utc

TIPO_CODIGO = "codigo"   # tentativa falha de código de acesso (chave = IP)
TIPO_LOGIN = "login"     # tentativa falha de login (chave = login do usuário)


class TentativaFalha(db.Model):
    """Serve ao rate limit do código (por IP) e ao bloqueio de login (por usuário)."""

    __tablename__ = "tentativa_falha"
    __table_args__ = (
        CheckConstraint("tipo IN ('codigo', 'login')", name="tipo_valido"),
        Index("ix_tentativa_falha_busca", "tipo", "chave", "momento"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[str] = mapped_column(String(10))
    chave: Mapped[str] = mapped_column(String(120))
    momento: Mapped[datetime] = mapped_column(UTCDateTime, default=agora_utc, index=True)


class ImportacaoPrevia(db.Model):
    """Prévia validada de uma importação de CSV, guardada no banco (e não em memória) porque pode haver vários
    workers. O token é de uso único e expira."""

    __tablename__ = "importacao_previa"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id", ondelete="CASCADE"))
    nome_questionario: Mapped[str] = mapped_column(String(160))
    descricao: Mapped[Optional[str]] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSON)
    criada_em: Mapped[datetime] = mapped_column(UTCDateTime, default=agora_utc)
    expira_em: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    usada: Mapped[bool] = mapped_column(default=False)
