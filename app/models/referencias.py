"""Cadastros de apoio. Em uso só se inativam; nunca se apagam."""
from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


class _Referencia:
    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120), unique=True)
    ativo: Mapped[bool] = mapped_column(default=True)

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.nome}>"


class Campus(_Referencia, db.Model):
    __tablename__ = "campus"


class Curso(_Referencia, db.Model):
    __tablename__ = "curso"


class Grupo(_Referencia, db.Model):
    """Agrupamento temático das perguntas (global, compartilhado entre questionários)."""

    __tablename__ = "grupo"
