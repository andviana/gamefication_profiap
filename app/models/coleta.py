from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.tipos import UTCDateTime, agora_utc


class Coleta(db.Model):
    """Turma que responde um questionário: o código identifica (questionário, campus, curso, ano, período)."""

    __tablename__ = "coleta"
    __table_args__ = (
        CheckConstraint("length(codigo) = 5", name="codigo_5_letras"),
        CheckConstraint("periodo IN (1, 2)", name="periodo_valido"),
        CheckConstraint("data_fim >= data_inicio", name="prazo_valido"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(5), unique=True)
    questionario_id: Mapped[int] = mapped_column(ForeignKey("questionario.id", ondelete="RESTRICT"), index=True)
    campus_id: Mapped[int] = mapped_column(ForeignKey("campus.id", ondelete="RESTRICT"), index=True)
    curso_id: Mapped[int] = mapped_column(ForeignKey("curso.id", ondelete="RESTRICT"), index=True)
    ano: Mapped[int]
    periodo: Mapped[int]
    data_inicio: Mapped[date]
    data_fim: Mapped[date]
    ativo: Mapped[bool] = mapped_column(default=True)
    criada_em: Mapped[datetime] = mapped_column(UTCDateTime, default=agora_utc)

    questionario = relationship("Questionario")
    campus = relationship("Campus")
    curso = relationship("Curso")

    def __repr__(self) -> str:
        return f"<Coleta {self.codigo}>"


class Partida(db.Model):
    """Uma partida finalizada de um aluno (anônima). O UUID, gerado no cliente, garante a idempotência do envio."""

    __tablename__ = "partida"
    __table_args__ = (
        CheckConstraint("total_acertos >= 0 AND total_acertos <= total_perguntas", name="totais_coerentes"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    coleta_id: Mapped[int] = mapped_column(ForeignKey("coleta.id", ondelete="RESTRICT"), index=True)
    finalizada_em: Mapped[datetime] = mapped_column(UTCDateTime, default=agora_utc, index=True)
    total_acertos: Mapped[int]
    total_perguntas: Mapped[int]

    coleta = relationship("Coleta")
    respostas: Mapped[list["Resposta"]] = relationship(
        back_populates="partida", cascade="all, delete-orphan", passive_deletes=True
    )


class Resposta(db.Model):
    """Resposta a uma pergunta. Guarda também um snapshot do que o aluno viu, para o histórico não mudar
    quando o texto for corrigido depois."""

    __tablename__ = "resposta"
    __table_args__ = (
        UniqueConstraint("partida_id", "pergunta_id"),
        CheckConstraint("ordem >= 1", name="ordem_positiva"),
        CheckConstraint("tempo_ms >= 0", name="tempo_nao_negativo"),
        Index("ix_resposta_pergunta_acertou", "pergunta_id", "acertou"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    partida_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("partida.id", ondelete="CASCADE"))
    # RESTRICT: o banco recusa apagar pergunta ou alternativa que já tenha resposta
    pergunta_id: Mapped[int] = mapped_column(ForeignKey("pergunta.id", ondelete="RESTRICT"))
    alternativa_id: Mapped[int] = mapped_column(ForeignKey("alternativa.id", ondelete="RESTRICT"))
    acertou: Mapped[bool]
    ordem: Mapped[int]
    tempo_ms: Mapped[int]
    # snapshot
    pergunta_numero: Mapped[int]
    pergunta_titulo: Mapped[str] = mapped_column(String(160))
    grupo_nome: Mapped[str] = mapped_column(String(120))
    alternativa_letra: Mapped[str] = mapped_column(String(1))

    partida: Mapped[Partida] = relationship(back_populates="respostas")
    pergunta = relationship("Pergunta")
    alternativa = relationship("Alternativa")
