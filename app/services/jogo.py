"""API pública do jogo: validar o código da turma, entregar o questionário e gravar a partida finalizada.

- Os alunos são anônimos: nada identifica a pessoa; a partida é ligada só ao código da coleta.
- Só falhas de código contam no limitador por IP (código válido não gasta o limite).
- O servidor é a autoridade do acerto: `acertou` é recalculado a partir da alternativa enviada, nunca do que o cliente diz.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from sqlalchemy.exc import IntegrityError

from app.config import Settings
from app.errors import Conflito, Encerrado, Invalido, LimiteExcedido, NaoEncontrado
from app.models import Coleta, Partida, Resposta
from app.models.tipos import agora_utc
from app.repositories.coletas import ColetaRepo
from app.repositories.partidas import PartidaRepo
from app.repositories.questionarios import QuestionarioRepo
from app.services import gabarito
from app.services.coletas import ABERTA, AGENDADA, DESATIVADA, ColetaService
from app.services.ratelimit import LimitadorFalhas

CODIGO_RE = re.compile(r"^[A-Z]{5}$")
MAX_TEMPO_MS = 3_600_000          # uma hora por pergunta é o teto: acima disso o dado é lixo
MAX_RESPOSTAS = 300


@dataclass(frozen=True)
class PartidaGravada:
    partida: Partida
    duplicada: bool               # True quando o UUID já estava gravado (reenvio idempotente)


def normaliza_codigo(bruto: Any) -> str | None:
    """Maiúsculas, sem espaços; None se não tiver o formato de um código (5 letras)."""
    if not isinstance(bruto, str):
        return None
    codigo = bruto.strip().upper()
    return codigo if CODIGO_RE.match(codigo) else None


class JogoService:
    def __init__(self, coletas: ColetaService, coletas_repo: ColetaRepo, questionarios: QuestionarioRepo, partidas: PartidaRepo,
                 limitador: LimitadorFalhas, settings: Settings, relogio: Callable = agora_utc):
        self.coletas = coletas
        self.coletas_repo = coletas_repo
        self.questionarios = questionarios
        self.partidas = partidas
        self.limitador = limitador
        self.settings = settings
        self.relogio = relogio

    # ---- código ---------------------------------------------------------------------------------
    def _falha(self, ip: str, erro: Exception):
        """Registra a falha (conta para o limite do IP) e a relança."""
        self.limitador.registrar(ip)
        raise erro

    def _coleta_aberta(self, codigo_bruto: Any, ip: str, *, no_envio: bool = False) -> Coleta:
        espera = self.limitador.espera(ip)
        if espera > 0:
            raise LimiteExcedido("Muitas tentativas com código errado. Aguarde um pouco e tente de novo.", espera_seg=espera)
        codigo = normaliza_codigo(codigo_bruto)
        coleta = self.coletas_repo.por_codigo(codigo) if codigo else None
        if coleta is None:
            self._falha(ip, NaoEncontrado("Código não encontrado. Confira as 5 letras com o seu professor.", motivo="inexistente"))
        situacao = self.coletas.situacao(coleta)
        if situacao == ABERTA:
            return coleta
        if no_envio:   # ao salvar, o aluno só precisa saber que a coleta fechou
            self._falha(ip, Encerrado("Esta coleta foi encerrada; suas respostas não foram salvas.", motivo="coleta_encerrada"))
        if situacao == DESATIVADA:
            self._falha(ip, Encerrado("Esta coleta está desativada. Fale com o seu professor.", motivo="inativa"))
        if situacao == AGENDADA:
            self._falha(ip, Encerrado("Esta coleta ainda não começou.", motivo="fora_do_prazo"))
        self._falha(ip, Encerrado("O prazo desta coleta já terminou.", motivo="fora_do_prazo"))

    # ---- 1. iniciar -----------------------------------------------------------------------------
    def iniciar(self, codigo_bruto: Any, ip: str) -> dict:
        """Valida o código e devolve o questionário da coleta: orientações e perguntas, sem campo `correta`."""
        coleta = self._coleta_aberta(codigo_bruto, ip)
        q = self.questionarios.por_id(coleta.questionario_id)
        sal = self.settings.gabarito_sal
        perguntas = []
        for p in q.perguntas:
            correta = next(a for a in p.alternativas if a.correta)
            perguntas.append({
                "numero": p.numero, "titulo": p.titulo, "grupo": p.grupo.nome, "texto": p.texto, "autoajuda": p.autoajuda,
                "token_correta": gabarito.token(sal, q.id, p.numero, correta.letra),
                "alternativas": [{"letra": a.letra, "texto": a.texto, "texto_acerto": a.texto_acerto, "texto_erro": a.texto_erro}
                                 for a in p.alternativas],
            })
        return {"coleta": {"codigo": coleta.codigo},
                "questionario": {"id": q.id, "nome": q.nome, "sal": sal, "orientacoes": q.orientacoes, "perguntas": perguntas}}

    # ---- 2. gravar a partida ----------------------------------------------------------------------
    @staticmethod
    def _uuid(bruto: Any) -> uuid.UUID:
        try:
            return uuid.UUID(str(bruto))
        except (ValueError, AttributeError, TypeError):
            raise Invalido("Identificador da partida inválido.", campo="uuid")

    @staticmethod
    def _inteiro(valor: Any, campo: str, minimo: int, maximo: int) -> int:
        if isinstance(valor, bool) or not isinstance(valor, int) or not minimo <= valor <= maximo:
            raise Invalido(f"Valor inválido em “{campo}”.", campo=campo)
        return valor

    def registrar_partida(self, uuid_bruto: Any, codigo_bruto: Any, respostas_brutas: Any, ip: str) -> PartidaGravada:
        """Grava a partida e as respostas numa única transação. Reenviar o mesmo UUID é seguro (idempotente)."""
        partida_id = self._uuid(uuid_bruto)
        coleta = self._coleta_aberta(codigo_bruto, ip, no_envio=True)

        existente = self.partidas.por_id(partida_id)
        if existente is not None:
            if existente.coleta_id != coleta.id:
                raise Conflito("Este identificador de partida já foi usado em outra coleta.", motivo="uuid_em_uso")
            return PartidaGravada(existente, True)

        if not isinstance(respostas_brutas, list) or not 1 <= len(respostas_brutas) <= MAX_RESPOSTAS:
            raise Invalido("Envie a lista de respostas da partida.", campo="respostas")
        questionario = self.questionarios.por_id(coleta.questionario_id)
        perguntas = {p.numero: p for p in questionario.perguntas}

        vistos: set[int] = set()
        linhas = []
        for item in respostas_brutas:
            if not isinstance(item, dict):
                raise Invalido("Cada resposta deve ser um objeto.", campo="respostas")
            numero = self._inteiro(item.get("pergunta"), "pergunta", 1, 10**6)
            if numero in vistos:
                raise Invalido(f"A pergunta {numero} foi respondida mais de uma vez.", campo="respostas")
            vistos.add(numero)
            if numero not in perguntas:
                raise Conflito("O questionário mudou durante a partida; suas respostas não foram salvas.", motivo="questionario_alterado")
            linhas.append((numero, item))
        if vistos != set(perguntas):
            raise Conflito("O questionário mudou durante a partida; suas respostas não foram salvas.", motivo="questionario_alterado")

        n = len(perguntas)
        ordens = set()
        respostas, acertos = [], 0
        for numero, item in linhas:
            p = perguntas[numero]
            letra = item.get("alternativa")
            alt = next((a for a in p.alternativas if isinstance(letra, str) and a.letra == letra.strip().upper()), None)
            if alt is None:
                raise Invalido(f"A alternativa da pergunta {numero} é inválida.", campo="alternativa")
            tempo = self._inteiro(item.get("tempo_ms"), "tempo_ms", 0, MAX_TEMPO_MS)
            ordem = self._inteiro(item.get("ordem"), "ordem", 1, n)
            ordens.add(ordem)
            acertos += 1 if alt.correta else 0
            respostas.append(Resposta(
                pergunta_id=p.id, alternativa_id=alt.id, acertou=alt.correta, ordem=ordem, tempo_ms=tempo,
                pergunta_numero=p.numero, pergunta_titulo=p.titulo, grupo_nome=p.grupo.nome, alternativa_letra=alt.letra))
        if len(ordens) != n:
            raise Invalido("A ordem das respostas deve ir de 1 até o número de perguntas, sem repetir.", campo="ordem")

        partida = Partida(id=partida_id, coleta_id=coleta.id, finalizada_em=self.relogio(), total_acertos=acertos, total_perguntas=n)
        partida.respostas = respostas
        self.partidas.adicionar(partida)
        try:
            self.partidas.commit()
        except IntegrityError:        # corrida: o mesmo UUID chegou duas vezes ao mesmo tempo
            self.partidas.rollback()
            igual = self.partidas.por_id(partida_id)
            if igual is not None and igual.coleta_id == coleta.id:
                return PartidaGravada(igual, True)
            raise Conflito("Não foi possível gravar a partida. Tente de novo.")
        return PartidaGravada(partida, False)
