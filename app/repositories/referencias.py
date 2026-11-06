from __future__ import annotations

from typing import Type

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Campus, Coleta, Curso, Pergunta


class ReferenciaRepo:
    """Campus, curso ou grupo (modelos com `nome` e `ativo`)."""

    def __init__(self, sessao: Session, modelo: Type):
        self.s = sessao
        self.modelo = modelo

    def listar(self) -> list:
        return list(self.s.scalars(select(self.modelo).order_by(self.modelo.ativo.desc(), func.lower(self.modelo.nome))))

    def por_id(self, ref_id: int):
        return self.s.get(self.modelo, ref_id)

    def por_nome(self, nome: str):
        """Busca sem diferenciar maiúsculas (o índice único do banco diferencia)."""
        return self.s.scalar(select(self.modelo).where(func.lower(self.modelo.nome) == nome.lower()))

    def usos(self) -> dict[int, int]:
        """Quantas coletas (campus/curso) ou perguntas (grupo) usam cada registro."""
        if self.modelo is Campus:
            col, alvo = Coleta.campus_id, Coleta
        elif self.modelo is Curso:
            col, alvo = Coleta.curso_id, Coleta
        else:
            col, alvo = Pergunta.grupo_id, Pergunta
        return dict(self.s.execute(select(col, func.count()).select_from(alvo).group_by(col)).all())

    def adicionar(self, registro) -> None:
        self.s.add(registro)

    def commit(self) -> None:
        self.s.commit()

    def rollback(self) -> None:
        self.s.rollback()
