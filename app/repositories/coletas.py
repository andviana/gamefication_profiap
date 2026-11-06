from __future__ import annotations

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import Coleta, Partida


class ColetaRepo:
    def __init__(self, sessao: Session):
        self.s = sessao

    def listar(self) -> list[Coleta]:
        consulta = (select(Coleta).options(selectinload(Coleta.questionario), selectinload(Coleta.campus), selectinload(Coleta.curso))
                    .order_by(Coleta.criada_em.desc(), Coleta.id.desc()))
        return list(self.s.scalars(consulta))

    def por_id(self, coleta_id: int) -> Optional[Coleta]:
        return self.s.get(Coleta, coleta_id)

    def por_codigo(self, codigo: str) -> Optional[Coleta]:
        return self.s.scalar(select(Coleta).where(Coleta.codigo == codigo))

    def codigo_existe(self, codigo: str) -> bool:
        return self.s.scalar(select(Coleta.id).where(Coleta.codigo == codigo).limit(1)) is not None

    def partidas_por_coleta(self) -> dict[int, int]:
        return dict(self.s.execute(select(Partida.coleta_id, func.count()).group_by(Partida.coleta_id)).all())

    def n_partidas(self, coleta_id: int) -> int:
        return self.s.scalar(select(func.count()).select_from(Partida).where(Partida.coleta_id == coleta_id)) or 0

    def duplicadas(self, questionario_id: int, campus_id: int, curso_id: int, ano: int, periodo: int,
                   ignorar_id: Optional[int] = None) -> list[Coleta]:
        consulta = select(Coleta).where(Coleta.questionario_id == questionario_id, Coleta.campus_id == campus_id,
                                        Coleta.curso_id == curso_id, Coleta.ano == ano, Coleta.periodo == periodo)
        if ignorar_id:
            consulta = consulta.where(Coleta.id != ignorar_id)
        return list(self.s.scalars(consulta.order_by(Coleta.id)))

    def adicionar(self, coleta: Coleta) -> None:
        self.s.add(coleta)

    def commit(self) -> None:
        self.s.commit()

    def rollback(self) -> None:
        self.s.rollback()
