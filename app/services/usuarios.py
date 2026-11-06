"""Regras de negócio de usuários: setup da raiz, CRUD, promoção/revogação e senhas."""
from __future__ import annotations

import re
from typing import Callable

from sqlalchemy.exc import IntegrityError

from app import auditoria, permissoes
from app.errors import Conflito, Invalido, NaoEncontrado, Proibido
from app.models.tipos import agora_utc
from app.models.usuario import PERFIL_COMUM, PERFIL_SUPERADMIN, Usuario
from app.repositories.tentativas import TentativaRepo
from app.repositories.usuarios import UsuarioRepo
from app.models.controle import TIPO_LOGIN
from app.services import senha as politica

LOGIN_RE = re.compile(r"^[a-z0-9._-]{3,40}$")


def normaliza_login(login: str) -> str:
    login = (login or "").strip().lower()
    if not LOGIN_RE.match(login):
        raise Invalido("O login deve ter de 3 a 40 caracteres: letras minúsculas, números, ponto, hífen ou sublinhado.",
                       campo="login")
    return login


def normaliza_nome(nome: str) -> str:
    nome = " ".join((nome or "").split())
    if not 2 <= len(nome) <= 120:
        raise Invalido("O nome deve ter de 2 a 120 caracteres.", campo="nome")
    return nome


class UsuarioService:
    def __init__(self, repo: UsuarioRepo, tentativas: TentativaRepo, relogio: Callable = agora_utc):
        self.repo = repo
        self.tentativas = tentativas
        self.relogio = relogio

    # ---- consultas ----------------------------------------------------------------------------
    def existe_algum(self) -> bool:
        return self.repo.existe_algum()

    def listar(self) -> list[Usuario]:
        return self.repo.listar()

    def obter(self, usuario_id: int) -> Usuario:
        usuario = self.repo.por_id(usuario_id)
        if usuario is None:
            raise NaoEncontrado("Usuário não encontrado.")
        return usuario

    def obter_gerenciavel(self, ator: Usuario, usuario_id: int) -> Usuario:
        """Carrega o alvo e exige que o ator possa gerenciá-lo (404 se não existe, 403 se não pode)."""
        alvo = self.obter(usuario_id)
        if not permissoes.pode_gerenciar(ator, alvo):
            raise Proibido("Você não pode gerenciar este usuário.")
        return alvo

    # ---- criação ------------------------------------------------------------------------------
    def _novo(self, nome: str, login: str, senha: str, confirmacao: str | None, **extra) -> Usuario:
        nome, login = normaliza_nome(nome), normaliza_login(login)
        politica.validar_senha(senha)
        if confirmacao is not None and senha != confirmacao:
            raise Invalido("A confirmação não confere com a senha.", campo="confirmacao")
        if self.repo.por_login(login):
            raise Conflito("Já existe um usuário com este login.", campo="login")
        return Usuario(nome=nome, login=login, senha_hash=politica.gerar_hash(senha), **extra)

    def _grava(self, usuario: Usuario) -> None:
        self.repo.adicionar(usuario)
        try:
            self.repo.commit()
        except IntegrityError as erro:  # corrida: outro pedido criou o mesmo login (ou a raiz) primeiro
            self.repo.rollback()
            raise Conflito("Não foi possível gravar: o registro já existe.") from erro

    def criar_raiz(self, nome: str, login: str, senha: str, confirmacao: str | None = None) -> Usuario:
        """Setup do primeiro acesso: só funciona com a tabela de usuários vazia. O criado é a raiz (super admin)."""
        if self.repo.existe_algum():
            raise NaoEncontrado()
        usuario = self._novo(nome, login, senha, confirmacao, perfil=PERFIL_SUPERADMIN, raiz=True)
        self._grava(usuario)
        auditoria.registrar("setup_raiz", alvo=usuario)
        return usuario

    def criar(self, ator: Usuario, nome: str, login: str, senha: str, confirmacao: str | None = None) -> Usuario:
        """Cria um usuário comum (promover é uma ação à parte, só da raiz)."""
        if not ator.eh_superadmin:
            raise Proibido()
        usuario = self._novo(nome, login, senha, confirmacao, perfil=PERFIL_COMUM)
        self._grava(usuario)
        auditoria.registrar("usuario_criado", ator, usuario)
        return usuario

    # ---- alteração ----------------------------------------------------------------------------
    def editar(self, ator: Usuario, usuario_id: int, nome: str, login: str) -> Usuario:
        alvo = self.obter_gerenciavel(ator, usuario_id)
        alvo.nome = normaliza_nome(nome)
        novo_login = normaliza_login(login)
        existente = self.repo.por_login(novo_login)
        if existente and existente.id != alvo.id:
            raise Conflito("Já existe um usuário com este login.", campo="login")
        mudou_login = novo_login != alvo.login
        alvo.login = novo_login
        if mudou_login:
            alvo.renovar_sessao()  # o login é parte da identidade: derruba as sessões abertas
        self._commit_ou_conflito()
        auditoria.registrar("usuario_editado", ator, alvo)
        return alvo

    def redefinir_senha(self, ator: Usuario, usuario_id: int, nova: str, confirmacao: str | None = None) -> Usuario:
        alvo = self.obter_gerenciavel(ator, usuario_id)
        politica.validar_senha(nova, campo="nova")
        if confirmacao is not None and nova != confirmacao:
            raise Invalido("A confirmação não confere com a senha.", campo="confirmacao")
        alvo.senha_hash = politica.gerar_hash(nova)
        alvo.renovar_sessao()
        self.tentativas.limpar(TIPO_LOGIN, alvo.login)   # destrava o usuário, se estiver bloqueado
        self._commit_ou_conflito()
        auditoria.registrar("senha_redefinida", ator, alvo)
        return alvo

    def alterar_propria_senha(self, usuario: Usuario, atual: str, nova: str, confirmacao: str | None = None) -> Usuario:
        """Qualquer usuário (inclusive a raiz) troca a própria senha informando a atual. Derruba as outras sessões."""
        if not politica.confere(usuario.senha_hash, atual or ""):
            raise Invalido("A senha atual está incorreta.", campo="atual")
        politica.validar_senha(nova, campo="nova")
        if confirmacao is not None and nova != confirmacao:
            raise Invalido("A confirmação não confere com a senha.", campo="confirmacao")
        usuario.senha_hash = politica.gerar_hash(nova)
        usuario.renovar_sessao()
        self._commit_ou_conflito()
        auditoria.registrar("senha_propria_alterada", usuario, usuario)
        return usuario

    def redefinir_senha_da_raiz(self, nova: str) -> Usuario:
        """Recuperação de acesso, só pelo CLI no servidor (`flask redefinir-superadmin`)."""
        raiz = self.repo.raiz()
        if raiz is None:
            raise NaoEncontrado("Ainda não existe super admin raiz: faça o setup pela página /setup.")
        politica.validar_senha(nova, campo="nova")
        raiz.senha_hash = politica.gerar_hash(nova)
        raiz.renovar_sessao()
        self.tentativas.limpar(TIPO_LOGIN, raiz.login)
        self._commit_ou_conflito()
        auditoria.registrar("senha_raiz_redefinida_cli", alvo=raiz)
        return raiz

    def promover(self, ator: Usuario, usuario_id: int) -> Usuario:
        alvo = self.obter(usuario_id)
        if not permissoes.pode_promover(ator, alvo):
            raise Proibido("Só o super admin raiz promove usuários comuns.")
        alvo.perfil = PERFIL_SUPERADMIN
        alvo.renovar_sessao()
        self._commit_ou_conflito()
        auditoria.registrar("promovido_a_superadmin", ator, alvo)
        return alvo

    def revogar(self, ator: Usuario, usuario_id: int) -> Usuario:
        alvo = self.obter(usuario_id)
        if not permissoes.pode_revogar(ator, alvo):
            raise Proibido("Só o super admin raiz revoga super admins promovidos.")
        alvo.perfil = PERFIL_COMUM
        alvo.renovar_sessao()
        self._commit_ou_conflito()
        auditoria.registrar("superadmin_revogado", ator, alvo)
        return alvo

    def excluir(self, ator: Usuario, usuario_id: int) -> None:
        alvo = self.obter(usuario_id)
        if alvo.id == ator.id:
            raise Proibido("Você não pode excluir a si mesmo.")
        if not permissoes.pode_gerenciar(ator, alvo):
            raise Proibido("Você não pode excluir este usuário.")
        self.tentativas.limpar(TIPO_LOGIN, alvo.login)
        self.repo.remover(alvo)
        self._commit_ou_conflito()
        auditoria.registrar("usuario_excluido", ator, alvo)

    def _commit_ou_conflito(self) -> None:
        try:
            self.repo.commit()
        except IntegrityError as erro:
            self.repo.rollback()
            raise Conflito("A operação conflita com os dados existentes.") from erro
