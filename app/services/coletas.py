"""Coletas: a turma que responde um questionário. O código de acesso identifica (questionário, campus, curso, ano, período).

- O prazo vale de 00:00 de `data_inicio` até 23:59:59 de `data_fim`, no fuso configurado (TIMEZONE).
- Ano: lista com ano atual - 1, atual e atual + 1. Período: 1 ou 2.
- Duplicidade (mesma identidade) é permitida, mas a tela avisa e pede confirmação.
- Depois da 1ª partida a identidade trava; prazo e situação (ativa) seguem editáveis. Coletas não são apagadas.
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import date, datetime
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError

from app import auditoria
from app.config import Settings
from app.errors import Conflito, Duplicidade, Invalido, NaoEncontrado
from app.models import Coleta
from app.models.tipos import agora_utc
from app.repositories.coletas import ColetaRepo
from app.repositories.referencias import ReferenciaRepo
from app.services.questionarios import QuestionarioService

# letras sem as ambíguas (I, L, O): 23 letras, 23^5 = 6,4 milhões de códigos
ALFABETO = "ABCDEFGHJKMNPQRSTUVWXYZ"
TAMANHO_CODIGO = 5
TENTATIVAS_CODIGO = 30

ABERTA, AGENDADA, ENCERRADA, DESATIVADA = "aberta", "agendada", "encerrada", "desativada"


def gera_codigo() -> str:
    return "".join(secrets.choice(ALFABETO) for _ in range(TAMANHO_CODIGO))


def situacao(coleta: Coleta, hoje: date) -> str:
    """Situação em um dia: desativada tem precedência; depois, antes/dentro/depois do prazo (datas inclusivas)."""
    if not coleta.ativo:
        return DESATIVADA
    if hoje < coleta.data_inicio:
        return AGENDADA
    if hoje > coleta.data_fim:
        return ENCERRADA
    return ABERTA


@dataclass
class DadosColeta:
    questionario_id: int
    campus_id: int
    curso_id: int
    ano: int
    periodo: int
    data_inicio: Optional[date]
    data_fim: Optional[date]


class ColetaService:
    IDENTIDADE = ("questionario_id", "campus_id", "curso_id", "ano", "periodo")

    def __init__(self, repo: ColetaRepo, questionarios: QuestionarioService, campus: ReferenciaRepo, cursos: ReferenciaRepo,
                 settings: Settings, relogio: Callable[[], datetime] = agora_utc, gerador: Callable[[], str] = gera_codigo):
        self.repo = repo
        self.questionarios = questionarios
        self.campus = campus
        self.cursos = cursos
        self.settings = settings
        self.relogio = relogio
        self.gerador = gerador

    # ---- tempo ----------------------------------------------------------------------------------
    def hoje(self) -> date:
        """O dia de hoje no fuso configurado (e não em UTC: perto da meia-noite os dois diferem)."""
        return self.relogio().astimezone(ZoneInfo(self.settings.timezone)).date()

    def anos_validos(self) -> list[int]:
        atual = self.hoje().year
        return [atual - 1, atual, atual + 1]

    def situacao(self, coleta: Coleta) -> str:
        return situacao(coleta, self.hoje())

    # ---- consultas ------------------------------------------------------------------------------
    def listar(self, questionario_id: Optional[int] = None, filtro_situacao: Optional[str] = None):
        partidas, hoje = self.repo.partidas_por_coleta(), self.hoje()
        itens = [(c, partidas.get(c.id, 0), situacao(c, hoje)) for c in self.repo.listar()]
        if questionario_id:
            itens = [i for i in itens if i[0].questionario_id == questionario_id]
        if filtro_situacao:
            itens = [i for i in itens if i[2] == filtro_situacao]
        return itens

    def obter(self, coleta_id: int) -> Coleta:
        coleta = self.repo.por_id(coleta_id)
        if coleta is None:
            raise NaoEncontrado("Coleta não encontrada.")
        return coleta

    def n_partidas(self, coleta: Coleta) -> int:
        return self.repo.n_partidas(coleta.id)

    # ---- validação ------------------------------------------------------------------------------
    def _valida(self, dados: DadosColeta, atual: Optional[Coleta] = None) -> None:
        mudou = lambda campo: atual is None or getattr(atual, campo) != getattr(dados, campo)   # noqa: E731
        q = self.questionarios.repo.por_id(dados.questionario_id) if dados.questionario_id else None
        if q is None:
            raise Invalido("Escolha o questionário.", campo="questionario_id")
        if mudou("questionario_id") and self.questionarios.resumo(q).n_perguntas == 0:
            raise Invalido("Este questionário ainda não tem perguntas. Cadastre-as antes de abrir uma coleta.", campo="questionario_id")
        for campo, repo, rotulo in (("campus_id", self.campus, "o campus"), ("curso_id", self.cursos, "o curso")):
            ref = repo.por_id(getattr(dados, campo)) if getattr(dados, campo) else None
            if ref is None:
                raise Invalido(f"Escolha {rotulo}.", campo=campo)
            if mudou(campo) and not ref.ativo:
                raise Invalido(f"{rotulo.capitalize()} está inativo. Escolha outro ou reative-o em Cadastros.", campo=campo)
        if dados.ano not in self.anos_validos() and mudou("ano"):
            raise Invalido(f"O ano deve ser {', '.join(map(str, self.anos_validos()))}.", campo="ano")
        if dados.periodo not in (1, 2):
            raise Invalido("O período deve ser 1 ou 2.", campo="periodo")
        if dados.data_inicio is None:
            raise Invalido("Informe a data de início.", campo="data_inicio")
        if dados.data_fim is None:
            raise Invalido("Informe a data de fim.", campo="data_fim")
        if dados.data_fim < dados.data_inicio:
            raise Invalido("A data de fim não pode ser anterior à de início.", campo="data_fim")

    def _confere_duplicidade(self, dados: DadosColeta, confirmada: bool, ignorar_id: Optional[int] = None) -> None:
        if confirmada:
            return
        iguais = self.repo.duplicadas(dados.questionario_id, dados.campus_id, dados.curso_id, dados.ano, dados.periodo, ignorar_id)
        if iguais:
            raise Duplicidade(iguais)

    def _commit(self) -> None:
        try:
            self.repo.commit()
        except IntegrityError as erro:
            self.repo.rollback()
            raise Conflito("A operação conflita com os dados existentes.") from erro

    # ---- criar, editar, ativar -----------------------------------------------------------------
    def _novo_codigo(self) -> str:
        for _ in range(TENTATIVAS_CODIGO):
            codigo = self.gerador()
            if not self.repo.codigo_existe(codigo):
                return codigo
        raise Conflito("Não foi possível gerar um código único. Tente de novo.")

    def criar(self, ator, dados: DadosColeta, duplicidade_confirmada: bool = False) -> Coleta:
        self._valida(dados)
        self._confere_duplicidade(dados, duplicidade_confirmada)
        coleta = None
        for _ in range(5):          # a corrida entre dois pedidos pode gerar o mesmo código: o banco recusa e tentamos outro
            coleta = Coleta(codigo=self._novo_codigo(), questionario_id=dados.questionario_id, campus_id=dados.campus_id,
                            curso_id=dados.curso_id, ano=dados.ano, periodo=dados.periodo, data_inicio=dados.data_inicio,
                            data_fim=dados.data_fim, ativo=True)
            self.repo.adicionar(coleta)
            try:
                self.repo.commit()
                break
            except IntegrityError:
                self.repo.rollback()
                coleta = None
        if coleta is None:
            raise Conflito("Não foi possível gerar um código único. Tente de novo.")
        auditoria.registrar("coleta_criada", ator, codigo=coleta.codigo, questionario=coleta.questionario_id)
        return coleta

    def editar(self, ator, coleta_id: int, dados: DadosColeta, duplicidade_confirmada: bool = False) -> Coleta:
        coleta = self.obter(coleta_id)
        com_partidas = self.n_partidas(coleta) > 0
        if com_partidas and any(getattr(coleta, c) != getattr(dados, c) for c in self.IDENTIDADE):
            raise Conflito("Esta coleta já tem partidas: o questionário, o campus, o curso, o ano e o período não podem mudar. "
                           "Para outra turma, crie uma nova coleta.")
        self._valida(dados, atual=coleta)
        if any(getattr(coleta, c) != getattr(dados, c) for c in self.IDENTIDADE):
            self._confere_duplicidade(dados, duplicidade_confirmada, ignorar_id=coleta.id)
        for campo in (*self.IDENTIDADE, "data_inicio", "data_fim"):
            setattr(coleta, campo, getattr(dados, campo))      # o código nunca muda
        self._commit()
        auditoria.registrar("coleta_editada", ator, codigo=coleta.codigo)
        return coleta

    def definir_ativo(self, ator, coleta_id: int, ativo: bool) -> Coleta:
        coleta = self.obter(coleta_id)
        coleta.ativo = ativo
        self._commit()
        auditoria.registrar("coleta_ativada" if ativo else "coleta_desativada", ator, codigo=coleta.codigo)
        return coleta
