"""Questionários: criar, editar, orientações, duplicar e excluir. O estado é derivado, nunca armazenado:
sem coleta = rascunho; com coleta e sem resposta = em coleta; com alguma resposta = travado."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError

from app import auditoria
from app.errors import Conflito, Invalido, NaoEncontrado
from app.models import Alternativa, Pergunta, Questionario
from app.orientacoes import texto_padrao
from app.repositories.questionarios import QuestionarioRepo

RASCUNHO, EM_COLETA, TRAVADO = "rascunho", "em coleta", "travado"
MAX_ORIENTACOES = 20000


@dataclass(frozen=True)
class Resumo:
    n_perguntas: int
    n_coletas: int
    n_respostas: int

    @property
    def estado(self) -> str:
        if self.n_respostas:
            return TRAVADO
        return EM_COLETA if self.n_coletas else RASCUNHO


def normaliza_nome(nome: str) -> str:
    nome = " ".join((nome or "").split())
    if not 2 <= len(nome) <= 160:
        raise Invalido("O nome do questionário deve ter de 2 a 160 caracteres.", campo="nome")
    return nome


def normaliza_descricao(descricao: str | None) -> str | None:
    descricao = (descricao or "").strip()
    if len(descricao) > 1000:
        raise Invalido("A descrição deve ter no máximo 1000 caracteres.", campo="descricao")
    return descricao or None


class QuestionarioService:
    def __init__(self, repo: QuestionarioRepo):
        self.repo = repo

    # ---- consultas ----------------------------------------------------------------------------
    def listar(self) -> list[tuple[Questionario, Resumo]]:
        contagens = self.repo.contagens()
        return [(q, Resumo(*contagens.get(q.id, (0, 0, 0)))) for q in self.repo.listar()]

    def obter(self, questionario_id: int) -> Questionario:
        q = self.repo.por_id(questionario_id)
        if q is None:
            raise NaoEncontrado("Questionário não encontrado.")
        return q

    def resumo(self, questionario: Questionario) -> Resumo:
        return Resumo(*self.repo.contagens().get(questionario.id, (0, 0, 0)))

    # ---- escrita ------------------------------------------------------------------------------
    def _nome_livre(self, nome: str, ignorar_id: int | None = None) -> None:
        existente = self.repo.por_nome(nome)
        if existente and existente.id != ignorar_id:
            raise Conflito("Já existe um questionário com este nome.", campo="nome")

    def _commit(self) -> None:
        try:
            self.repo.commit()
        except IntegrityError as erro:
            self.repo.rollback()
            raise Conflito("A operação conflita com os dados existentes.") from erro

    def criar(self, ator, nome: str, descricao: str | None = None) -> Questionario:
        nome, descricao = normaliza_nome(nome), normaliza_descricao(descricao)
        self._nome_livre(nome)
        q = Questionario(nome=nome, descricao=descricao, orientacoes=texto_padrao())
        self.repo.adicionar(q)
        self._commit()
        auditoria.registrar("questionario_criado", ator, nome=nome)
        return q

    def editar(self, ator, questionario_id: int, nome: str, descricao: str | None) -> Questionario:
        q = self.obter(questionario_id)
        nome, descricao = normaliza_nome(nome), normaliza_descricao(descricao)
        self._nome_livre(nome, ignorar_id=q.id)
        q.nome, q.descricao = nome, descricao
        self._commit()
        auditoria.registrar("questionario_editado", ator, nome=nome)
        return q

    def atualizar_orientacoes(self, ator, questionario_id: int, texto: str) -> Questionario:
        """Texto das orientações (e do aviso de privacidade). Corrigir texto é permitido em qualquer estado."""
        q = self.obter(questionario_id)
        texto = (texto or "").replace("\r\n", "\n").strip()
        if not texto:
            raise Invalido("O texto das orientações não pode ficar vazio.", campo="orientacoes")
        if len(texto) > MAX_ORIENTACOES:
            raise Invalido(f"O texto deve ter no máximo {MAX_ORIENTACOES} caracteres.", campo="orientacoes")
        q.orientacoes = texto
        self._commit()
        auditoria.registrar("orientacoes_editadas", ator, questionario=q.nome)
        return q

    def duplicar(self, ator, questionario_id: int) -> Questionario:
        """Copia perguntas, alternativas e orientações para um novo rascunho, sem coletas nem respostas."""
        origem = self.obter(questionario_id)
        base = f"{origem.nome[:140]} (cópia)"
        nome, n = base, 1
        while self.repo.por_nome(nome):
            n += 1
            nome = f"{origem.nome[:135]} (cópia {n})"
        copia = Questionario(nome=nome, descricao=origem.descricao, orientacoes=origem.orientacoes, derivado_de_id=origem.id)
        for p in origem.perguntas:
            copia.perguntas.append(Pergunta(
                numero=p.numero, texto=p.texto, titulo=p.titulo, grupo_id=p.grupo_id, autoajuda=p.autoajuda,
                alternativas=[Alternativa(letra=a.letra, texto=a.texto, correta=a.correta,
                                          texto_acerto=a.texto_acerto, texto_erro=a.texto_erro) for a in p.alternativas]))
        self.repo.adicionar(copia)
        self._commit()
        auditoria.registrar("questionario_duplicado", ator, origem=origem.nome, copia=copia.nome)
        return copia

    def excluir(self, ator, questionario_id: int) -> None:
        """Só rascunho (sem coleta) pode ser excluído; o banco ainda recusa se houver respostas."""
        q = self.obter(questionario_id)
        if self.resumo(q).estado != RASCUNHO:
            raise Conflito("Só um questionário em rascunho (sem coletas) pode ser excluído.")
        nome = q.nome
        self.repo.remover(q)
        self._commit()
        auditoria.registrar("questionario_excluido", ator, nome=nome)
