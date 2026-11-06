"""Montagem das dependências (injeção simples, sem framework).

Cada fase acrescenta aqui os repositories e services, montados a partir das settings e da sessão do banco.
Os blueprints recebem o contêiner pelo app (`current_app.extensions["container"]`) e nunca instanciam
services por conta própria, o que mantém a troca de dependências fácil nos testes.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings
from app.extensions import db
from app.models import Campus, Curso, Grupo
from app.models.controle import TIPO_CODIGO
from app.repositories.coletas import ColetaRepo
from app.repositories.dashboard import DashboardRepo
from app.repositories.importacoes import PreviaRepo
from app.repositories.partidas import PartidaRepo
from app.repositories.questionarios import QuestionarioRepo
from app.repositories.referencias import ReferenciaRepo
from app.repositories.tentativas import TentativaRepo
from app.repositories.usuarios import UsuarioRepo
from app.services.auth import AuthService
from app.services.coletas import ColetaService
from app.services.dashboard import DashboardService
from app.services.importacao import ImportacaoService
from app.services.jogo import JogoService
from app.services.ratelimit import LimitadorFalhas
from app.services.perguntas import PerguntaService
from app.services.questionarios import QuestionarioService
from app.services.referencias import ReferenciaService
from app.services.usuarios import UsuarioService


@dataclass(frozen=True)
class Container:
    settings: Settings
    usuarios: UsuarioService
    auth: AuthService
    questionarios: QuestionarioService
    perguntas: PerguntaService
    importacao: ImportacaoService
    coletas: ColetaService
    jogo: JogoService
    dashboard: DashboardService
    referencias: dict   # "campus" | "curso" | "grupo" -> ReferenciaService


def montar_container(settings: Settings) -> Container:
    sessao = db.session   # sessão com escopo de requisição (scoped_session)
    usuarios_repo, tentativas_repo = UsuarioRepo(sessao), TentativaRepo(sessao)
    questionarios_repo, grupos_repo = QuestionarioRepo(sessao), ReferenciaRepo(sessao, Grupo)
    questionarios = QuestionarioService(questionarios_repo)
    coletas_repo = ColetaRepo(sessao)
    coletas = ColetaService(coletas_repo, questionarios, ReferenciaRepo(sessao, Campus), ReferenciaRepo(sessao, Curso), settings)
    return Container(
        settings=settings,
        usuarios=UsuarioService(usuarios_repo, tentativas_repo),
        auth=AuthService(usuarios_repo, tentativas_repo, settings),
        questionarios=questionarios,
        perguntas=PerguntaService(questionarios_repo, questionarios, grupos_repo),
        importacao=ImportacaoService(questionarios_repo, grupos_repo, PreviaRepo(sessao), settings),
        coletas=coletas,
        jogo=JogoService(
            coletas, coletas_repo, questionarios_repo, PartidaRepo(sessao),
            LimitadorFalhas(tentativas_repo, TIPO_CODIGO, settings.rate_limit_falhas, settings.rate_limit_janela_seg,
                            settings.rate_limit_bloqueio_seg),
            settings),
        dashboard=DashboardService(DashboardRepo(sessao), questionarios, settings),
        referencias={
            rotulo: ReferenciaService(ReferenciaRepo(sessao, modelo), rotulo)
            for rotulo, modelo in (("campus", Campus), ("curso", Curso), ("grupo", Grupo))
        },
    )
