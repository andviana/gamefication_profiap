"""Cadastros de apoio (campus, curso, grupo): criar, renomear e inativar/reativar. Nunca se apagam."""
from __future__ import annotations

from sqlalchemy.exc import IntegrityError

from app import auditoria
from app.errors import Conflito, Invalido, NaoEncontrado
from app.repositories.referencias import ReferenciaRepo


def normaliza_nome(nome: str, rotulo: str) -> str:
    nome = " ".join((nome or "").split())
    if not 2 <= len(nome) <= 120:
        raise Invalido(f"O nome do {rotulo} deve ter de 2 a 120 caracteres.", campo="nome")
    return nome


class ReferenciaService:
    def __init__(self, repo: ReferenciaRepo, rotulo: str):
        self.repo = repo
        self.rotulo = rotulo   # "campus", "curso" ou "grupo" (aparece nas mensagens)

    def listar(self):
        usos = self.repo.usos()
        return [(r, usos.get(r.id, 0)) for r in self.repo.listar()]

    def ativos(self):
        return [r for r in self.repo.listar() if r.ativo]

    def obter(self, ref_id: int):
        registro = self.repo.por_id(ref_id)
        if registro is None:
            raise NaoEncontrado(f"Registro de {self.rotulo} não encontrado.")
        return registro

    def _confere_nome_livre(self, nome: str, ignorar_id: int | None = None) -> None:
        existente = self.repo.por_nome(nome)
        if existente and existente.id != ignorar_id:
            raise Conflito(f"Já existe um registro de {self.rotulo} com este nome.", campo="nome")

    def _commit(self) -> None:
        try:
            self.repo.commit()
        except IntegrityError as erro:   # corrida: o mesmo nome foi criado por outra pessoa
            self.repo.rollback()
            raise Conflito(f"Já existe um registro de {self.rotulo} com este nome.", campo="nome") from erro

    def criar(self, ator, nome: str):
        nome = normaliza_nome(nome, self.rotulo)
        self._confere_nome_livre(nome)
        registro = self.repo.modelo(nome=nome)
        self.repo.adicionar(registro)
        self._commit()
        auditoria.registrar(f"{self.rotulo}_criado", ator, nome=nome)
        return registro

    def renomear(self, ator, ref_id: int, nome: str):
        registro = self.obter(ref_id)
        nome = normaliza_nome(nome, self.rotulo)
        self._confere_nome_livre(nome, ignorar_id=registro.id)
        antigo, registro.nome = registro.nome, nome
        self._commit()
        auditoria.registrar(f"{self.rotulo}_renomeado", ator, de=antigo, para=nome)
        return registro

    def definir_ativo(self, ator, ref_id: int, ativo: bool):
        registro = self.obter(ref_id)
        registro.ativo = ativo
        self._commit()
        auditoria.registrar(f"{self.rotulo}_{'reativado' if ativo else 'inativado'}", ator, nome=registro.nome)
        return registro
