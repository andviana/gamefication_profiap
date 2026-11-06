from __future__ import annotations

from typing import Optional

from sqlalchemy import case, distinct, func, select, update
from sqlalchemy.orm import Session

from app.models import Coleta, Partida, Pergunta, Questionario, Resposta


class QuestionarioRepo:
    def __init__(self, sessao: Session):
        self.s = sessao

    # ---- questionários -----------------------------------------------------------------------
    def listar(self) -> list[Questionario]:
        return list(self.s.scalars(select(Questionario).order_by(Questionario.criado_em.desc(), Questionario.id.desc())))

    def por_id(self, questionario_id: int) -> Optional[Questionario]:
        return self.s.get(Questionario, questionario_id)

    def por_nome(self, nome: str) -> Optional[Questionario]:
        return self.s.scalar(select(Questionario).where(func.lower(Questionario.nome) == nome.lower()))

    def contagens(self) -> dict[int, tuple[int, int, int]]:
        """(perguntas, coletas, respostas) de cada questionário, em poucas consultas."""
        perguntas = dict(self.s.execute(
            select(Pergunta.questionario_id, func.count()).group_by(Pergunta.questionario_id)).all())
        coletas = dict(self.s.execute(
            select(Coleta.questionario_id, func.count()).group_by(Coleta.questionario_id)).all())
        respostas = dict(self.s.execute(
            select(Pergunta.questionario_id, func.count(Resposta.id))
            .join(Resposta, Resposta.pergunta_id == Pergunta.id).group_by(Pergunta.questionario_id)).all())
        ids = set(perguntas) | set(coletas) | set(respostas)
        return {i: (perguntas.get(i, 0), coletas.get(i, 0), respostas.get(i, 0)) for i in ids}

    def adicionar(self, objeto) -> None:
        self.s.add(objeto)

    def remover(self, objeto) -> None:
        self.s.delete(objeto)

    def flush(self) -> None:
        self.s.flush()

    def commit(self) -> None:
        self.s.commit()

    def rollback(self) -> None:
        self.s.rollback()

    # ---- perguntas ---------------------------------------------------------------------------
    def pergunta(self, pergunta_id: int) -> Optional[Pergunta]:
        return self.s.get(Pergunta, pergunta_id)

    def proximo_numero(self, questionario_id: int) -> int:
        ultimo = self.s.scalar(select(func.max(Pergunta.numero)).where(Pergunta.questionario_id == questionario_id))
        return (ultimo or 0) + 1

    def numero_em_uso(self, questionario_id: int, numero: int, ignorar_id: Optional[int] = None) -> bool:
        consulta = select(Pergunta.id).where(Pergunta.questionario_id == questionario_id, Pergunta.numero == numero)
        if ignorar_id:
            consulta = consulta.where(Pergunta.id != ignorar_id)
        return self.s.scalar(consulta.limit(1)) is not None

    def respostas_da_pergunta(self, pergunta_id: int) -> tuple[int, int]:
        """(respostas, partidas distintas) já gravadas para a pergunta."""
        return tuple(self.s.execute(select(func.count(Resposta.id), func.count(distinct(Resposta.partida_id)))
                                    .where(Resposta.pergunta_id == pergunta_id)).one())

    def recalcular_acertos(self, pergunta_id: int, alternativa_correta_id: int) -> None:
        """Depois de trocar o gabarito: refaz `acertou` das respostas da pergunta e o total de acertos das partidas."""
        self.s.execute(update(Resposta).where(Resposta.pergunta_id == pergunta_id).values(
            acertou=case((Resposta.alternativa_id == alternativa_correta_id, True), else_=False)))
        acertos = (select(func.count(Resposta.id))
                   .where(Resposta.partida_id == Partida.id, Resposta.acertou.is_(True))
                   .correlate(Partida).scalar_subquery())
        afetadas = select(Resposta.partida_id).where(Resposta.pergunta_id == pergunta_id)
        self.s.execute(update(Partida).where(Partida.id.in_(afetadas)).values(total_acertos=acertos))
