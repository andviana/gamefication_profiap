from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import delete, or_, update
from sqlalchemy.orm import Session

from app.models import ImportacaoPrevia


class PreviaRepo:
    def __init__(self, sessao: Session):
        self.s = sessao

    def adicionar(self, previa: ImportacaoPrevia) -> None:
        self.s.add(previa)

    def obter(self, token: str) -> Optional[ImportacaoPrevia]:
        return self.s.get(ImportacaoPrevia, token)

    def consumir(self, token: str, usuario_id: int, agora: datetime) -> bool:
        """Marca a prévia como usada, de forma atômica (UPDATE condicional). Só uma chamada consegue: duplo clique
        ou dois pedidos simultâneos não criam dois questionários."""
        resultado = self.s.execute(
            update(ImportacaoPrevia)
            .where(ImportacaoPrevia.token == token, ImportacaoPrevia.usuario_id == usuario_id,
                   ImportacaoPrevia.usada.is_(False), ImportacaoPrevia.expira_em > agora)
            .values(usada=True))
        return resultado.rowcount == 1

    def purgar(self, agora: datetime) -> None:
        """Remove prévias expiradas ou já usadas."""
        self.s.execute(delete(ImportacaoPrevia).where(or_(ImportacaoPrevia.expira_em <= agora, ImportacaoPrevia.usada.is_(True))))

    def commit(self) -> None:
        self.s.commit()

    def rollback(self) -> None:
        self.s.rollback()
