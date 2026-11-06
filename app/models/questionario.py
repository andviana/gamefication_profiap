from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.tipos import UTCDateTime, agora_utc


class Questionario(db.Model):
    """Conjunto de perguntas e o texto de orientações. O estado (rascunho, em coleta, travado) é derivado:
    sem coleta = rascunho; com coleta e sem resposta = em coleta; com alguma resposta = travado."""

    __tablename__ = "questionario"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(160), unique=True)
    descricao: Mapped[Optional[str]] = mapped_column(Text)
    orientacoes: Mapped[str] = mapped_column(Text, default="")
    derivado_de_id: Mapped[Optional[int]] = mapped_column(ForeignKey("questionario.id", ondelete="SET NULL"))
    criado_em: Mapped[datetime] = mapped_column(UTCDateTime, default=agora_utc)

    derivado_de: Mapped[Optional["Questionario"]] = relationship(remote_side="Questionario.id")
    perguntas: Mapped[list["Pergunta"]] = relationship(
        back_populates="questionario", order_by="Pergunta.numero", cascade="all, delete-orphan", passive_deletes=True
    )

    def __repr__(self) -> str:
        return f"<Questionario {self.nome}>"


class Pergunta(db.Model):
    __tablename__ = "pergunta"
    __table_args__ = (UniqueConstraint("questionario_id", "numero"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    # apagar um questionário leva as perguntas junto, mas o banco recusa se alguma já tiver resposta (FK de resposta)
    questionario_id: Mapped[int] = mapped_column(ForeignKey("questionario.id", ondelete="CASCADE"), index=True)
    numero: Mapped[int]
    texto: Mapped[str] = mapped_column(Text)
    titulo: Mapped[str] = mapped_column(String(160))
    grupo_id: Mapped[int] = mapped_column(ForeignKey("grupo.id", ondelete="RESTRICT"), index=True)
    autoajuda: Mapped[Optional[str]] = mapped_column(Text)

    questionario: Mapped[Questionario] = relationship(back_populates="perguntas")
    grupo = relationship("Grupo")
    alternativas: Mapped[list["Alternativa"]] = relationship(
        back_populates="pergunta", order_by="Alternativa.letra", cascade="all, delete-orphan", passive_deletes=True
    )

    def __repr__(self) -> str:
        return f"<Pergunta Q{self.numero} do questionário {self.questionario_id}>"


class Alternativa(db.Model):
    __tablename__ = "alternativa"
    __table_args__ = (
        UniqueConstraint("pergunta_id", "letra"),
        CheckConstraint("length(letra) = 1", name="letra_unica"),
        # no máximo uma alternativa correta por pergunta, garantido pelo banco (índice parcial)
        Index("uq_alternativa_correta", "pergunta_id", unique=True, postgresql_where=text("correta"), sqlite_where=text("correta")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    pergunta_id: Mapped[int] = mapped_column(ForeignKey("pergunta.id", ondelete="CASCADE"))
    letra: Mapped[str] = mapped_column(String(1))
    texto: Mapped[str] = mapped_column(Text)
    correta: Mapped[bool] = mapped_column(default=False)
    texto_acerto: Mapped[Optional[str]] = mapped_column(Text)
    texto_erro: Mapped[Optional[str]] = mapped_column(Text)

    pergunta: Mapped[Pergunta] = relationship(back_populates="alternativas")

    def __repr__(self) -> str:
        return f"<Alternativa {self.letra}{'*' if self.correta else ''} da pergunta {self.pergunta_id}>"
