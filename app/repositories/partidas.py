from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Partida


class PartidaRepo:
    def __init__(self, sessao: Session):
        self.s = sessao

    def por_id(self, partida_id: uuid.UUID) -> Optional[Partida]:
        return self.s.get(Partida, partida_id)

    def adicionar(self, partida: Partida) -> None:
        self.s.add(partida)

    def commit(self) -> None:
        self.s.commit()

    def rollback(self) -> None:
        self.s.rollback()
