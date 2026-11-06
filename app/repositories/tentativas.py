from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import TentativaFalha


class TentativaRepo:
    def __init__(self, sessao: Session):
        self.s = sessao

    def registrar(self, tipo: str, chave: str, momento: datetime) -> None:
        self.s.add(TentativaFalha(tipo=tipo, chave=chave, momento=momento))

    def momentos_desde(self, tipo: str, chave: str, desde: datetime) -> list[datetime]:
        consulta = select(TentativaFalha.momento).where(
            TentativaFalha.tipo == tipo, TentativaFalha.chave == chave, TentativaFalha.momento >= desde
        ).order_by(TentativaFalha.momento)
        return list(self.s.scalars(consulta))

    def limpar(self, tipo: str, chave: str) -> None:
        self.s.execute(delete(TentativaFalha).where(TentativaFalha.tipo == tipo, TentativaFalha.chave == chave))

    def purgar_antes_de(self, limite: datetime) -> None:
        self.s.execute(delete(TentativaFalha).where(TentativaFalha.momento < limite))

    def commit(self) -> None:
        self.s.commit()
