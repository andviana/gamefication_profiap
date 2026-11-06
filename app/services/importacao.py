"""Importação de questionários por CSV (só super admin): upload -> prévia sem gravar -> confirmação.

Cria um questionário NOVO, em rascunho; não apaga nem altera nada que já exista.
A prévia validada fica no banco (e não em memória) porque pode haver vários workers; o token é de uso único e expira.
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Callable

from sqlalchemy.exc import IntegrityError

from app import auditoria
from app.config import Settings
from app.errors import Conflito, Invalido, NaoEncontrado, Proibido
from app.models import Alternativa, Grupo, ImportacaoPrevia, Pergunta, Questionario
from app.models.tipos import agora_utc
from app.orientacoes import texto_padrao
from app.repositories.importacoes import PreviaRepo
from app.repositories.questionarios import QuestionarioRepo
from app.repositories.referencias import ReferenciaRepo
from app.services import csv_import
from app.services.csv_import import Analise, ErroLinha
from app.services.questionarios import normaliza_descricao, normaliza_nome


@dataclass
class Previa:
    nome: str
    descricao: str | None
    analise: Analise
    token: str | None = None                      # só existe quando não há erros
    grupos_novos: list[str] = field(default_factory=list)
    grupos_existentes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.token is not None


class ImportacaoService:
    def __init__(self, questionarios: QuestionarioRepo, grupos: ReferenciaRepo, previas: PreviaRepo, settings: Settings,
                 relogio: Callable = agora_utc):
        self.questionarios = questionarios
        self.grupos = grupos
        self.previas = previas
        self.settings = settings
        self.relogio = relogio

    @staticmethod
    def _exige_super_admin(ator) -> None:
        if not getattr(ator, "eh_superadmin", False):
            raise Proibido("Só super admin importa questionários.")

    def _confere_arquivo(self, rotulo: str, nome_arquivo: str, conteudo: bytes) -> None:
        if not (nome_arquivo or "").lower().endswith(".csv"):
            raise Invalido(f"O arquivo de {rotulo} deve ter a extensão .csv.", campo=f"arquivo_{rotulo}")
        if not conteudo:
            raise Invalido(f"O arquivo de {rotulo} está vazio.", campo=f"arquivo_{rotulo}")
        if len(conteudo) > self.settings.upload_max_bytes:
            limite = self.settings.upload_max_bytes // 1024
            raise Invalido(f"O arquivo de {rotulo} passa do limite de {limite} KB.", campo=f"arquivo_{rotulo}")

    # ---- 1. prévia ------------------------------------------------------------------------------
    def analisar(self, ator, nome: str, descricao: str | None, arquivo_perguntas: tuple[str, bytes],
                 arquivo_alternativas: tuple[str, bytes]) -> Previa:
        """Valida tudo sem gravar o questionário. Sem erros, guarda a prévia (token de uso único) e a devolve."""
        self._exige_super_admin(ator)
        nome, descricao = normaliza_nome(nome), normaliza_descricao(descricao)
        if self.questionarios.por_nome(nome):
            raise Conflito("Já existe um questionário com este nome.", campo="nome")
        self._confere_arquivo("perguntas", *arquivo_perguntas)
        self._confere_arquivo("alternativas", *arquivo_alternativas)

        analise = csv_import.analisar(arquivo_perguntas[1], arquivo_alternativas[1])
        previa = Previa(nome=nome, descricao=descricao, analise=analise)

        existentes = {g.nome.lower(): g for g in self.grupos.listar()}
        vistos: dict[str, str] = {}
        for p in analise.perguntas:
            vistos.setdefault(p["grupo"].lower(), p["grupo"])
        for chave, rotulo in vistos.items():
            existente = existentes.get(chave)
            if existente is None:
                previa.grupos_novos.append(rotulo)
            elif not existente.ativo:
                analise.erros.append(ErroLinha("perguntas.csv", None, f"o grupo “{existente.nome}” existe, mas está inativo; "
                                                                   "reative-o em Cadastros ou use outro nome"))
            else:
                previa.grupos_existentes.append(existente.nome)
        for lista in (previa.grupos_novos, previa.grupos_existentes):
            lista.sort(key=str.lower)

        if analise.erros:
            return previa
        agora = self.relogio()
        self.previas.purgar(agora)
        previa.token = secrets.token_urlsafe(32)
        self.previas.adicionar(ImportacaoPrevia(
            token=previa.token, usuario_id=ator.id, nome_questionario=nome, descricao=descricao,
            payload={"perguntas": analise.perguntas}, criada_em=agora,
            expira_em=agora + timedelta(minutes=self.settings.previa_validade_min)))
        self.previas.commit()
        return previa

    # ---- 2. confirmação ------------------------------------------------------------------------
    def confirmar(self, ator, token: str) -> Questionario:
        """Cria o questionário a partir da prévia. Tudo numa transação: se algo falhar, nada é criado e a prévia segue
        válida. Prévia usada, expirada ou de outra pessoa é recusada."""
        self._exige_super_admin(ator)
        previa = self.previas.obter(token or "")
        if previa is None or previa.usuario_id != ator.id:
            raise NaoEncontrado("Prévia de importação não encontrada. Envie os arquivos de novo.")
        agora = self.relogio()
        if not self.previas.consumir(previa.token, ator.id, agora):
            raise Conflito("Esta prévia já foi usada ou expirou. Envie os arquivos de novo.")
        try:
            if self.questionarios.por_nome(previa.nome_questionario):
                raise Conflito("Já existe um questionário com este nome. Envie os arquivos de novo com outro nome.")
            questionario = self._cria(previa)
            self.questionarios.commit()
        except IntegrityError as erro:
            self.questionarios.rollback()
            raise Conflito("Não foi possível criar o questionário: os dados conflitam com os existentes.") from erro
        except Exception:
            self.questionarios.rollback()   # desfaz também o "usada": a prévia continua valendo
            raise
        auditoria.registrar("questionario_importado", ator, nome=questionario.nome,
                            perguntas=len(questionario.perguntas))
        return questionario

    def _cria(self, previa: ImportacaoPrevia) -> Questionario:
        grupos = {g.nome.lower(): g for g in self.grupos.listar()}
        questionario = Questionario(nome=previa.nome_questionario, descricao=previa.descricao, orientacoes=texto_padrao())
        for dados in previa.payload["perguntas"]:
            grupo = grupos.get(dados["grupo"].lower())
            if grupo is None:
                grupo = Grupo(nome=dados["grupo"])
                self.questionarios.adicionar(grupo)
                grupos[dados["grupo"].lower()] = grupo
            pergunta = Pergunta(numero=dados["numero"], texto=dados["texto"], titulo=dados["titulo"], grupo=grupo,
                                autoajuda=dados["autoajuda"])
            for alt in dados["alternativas"]:
                pergunta.alternativas.append(Alternativa(letra=alt["letra"], texto=alt["texto"], correta=alt["correta"],
                                                         texto_acerto=alt["texto_acerto"], texto_erro=alt["texto_erro"]))
            questionario.perguntas.append(pergunta)
        self.questionarios.adicionar(questionario)
        return questionario
