from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Usuario


class UsuarioRepo:
    def __init__(self, sessao: Session):
        self.s = sessao

    def por_id(self, usuario_id: int) -> Optional[Usuario]:
        return self.s.get(Usuario, usuario_id)

    def por_login(self, login: str) -> Optional[Usuario]:
        return self.s.scalar(select(Usuario).where(Usuario.login == login))

    def raiz(self) -> Optional[Usuario]:
        return self.s.scalar(select(Usuario).where(Usuario.raiz.is_(True)))

    def existe_algum(self) -> bool:
        return self.s.scalar(select(Usuario.id).limit(1)) is not None

    def listar(self) -> list[Usuario]:
        return list(self.s.scalars(select(Usuario).order_by(Usuario.raiz.desc(), Usuario.perfil.desc(), Usuario.nome)))

    def adicionar(self, usuario: Usuario) -> None:
        self.s.add(usuario)

    def remover(self, usuario: Usuario) -> None:
        self.s.delete(usuario)

    def commit(self) -> None:
        self.s.commit()

    def rollback(self) -> None:
        self.s.rollback()
