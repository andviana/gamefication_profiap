from __future__ import annotations

import secrets
from datetime import datetime

from sqlalchemy import CheckConstraint, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db
from app.models.tipos import UTCDateTime, agora_utc

PERFIL_COMUM = "comum"
PERFIL_SUPERADMIN = "superadmin"
PERFIS = (PERFIL_COMUM, PERFIL_SUPERADMIN)


def novo_token_sessao() -> str:
    return secrets.token_hex(16)


class Usuario(db.Model):
    """Usuário do painel. Exatamente um tem `raiz=True` (o primeiro, criado no setup); ele é super admin e imutável."""

    __tablename__ = "usuario"
    __table_args__ = (
        CheckConstraint("perfil IN ('comum', 'superadmin')", name="perfil_valido"),
        CheckConstraint("NOT raiz OR perfil = 'superadmin'", name="raiz_e_superadmin"),
        # no máximo uma linha com raiz verdadeiro (índice parcial, igual no SQLite e no Postgres)
        Index("uq_usuario_raiz", "raiz", unique=True, postgresql_where=text("raiz"), sqlite_where=text("raiz")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120))
    login: Mapped[str] = mapped_column(String(60), unique=True)
    senha_hash: Mapped[str] = mapped_column(String(255))
    perfil: Mapped[str] = mapped_column(String(12), default=PERFIL_COMUM)
    raiz: Mapped[bool] = mapped_column(default=False)
    criado_em: Mapped[datetime] = mapped_column(UTCDateTime, default=agora_utc)
    # muda quando a senha ou o perfil são alterados por outra pessoa: invalida as sessões abertas do usuário
    sessao_token: Mapped[str] = mapped_column(String(32), default=novo_token_sessao)

    @property
    def eh_superadmin(self) -> bool:
        return self.perfil == PERFIL_SUPERADMIN

    def renovar_sessao(self) -> None:
        """Invalida todas as sessões abertas deste usuário."""
        self.sessao_token = novo_token_sessao()

    def get_id(self) -> str:  # Flask-Login: o id da sessão inclui o token, então trocá-lo derruba a sessão
        return f"{self.id}:{self.sessao_token}"

    # propriedades que o Flask-Login espera
    is_authenticated = True
    is_active = True
    is_anonymous = False

    def __repr__(self) -> str:
        return f"<Usuario {self.login} {self.perfil}{' raiz' if self.raiz else ''}>"
