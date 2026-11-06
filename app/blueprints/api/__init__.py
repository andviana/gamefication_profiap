"""API pública do jogo (JSON, mesma origem, sem login): validar o código e gravar a partida finalizada."""
from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from app.errors import ErroDominio, Invalido

bp = Blueprint("api", __name__, url_prefix="/api")

MAX_CORPO = 64 * 1024     # uma partida cabe em poucos KB; acima disso é abuso


def _jogo():
    return current_app.extensions["container"].jogo


def _ip() -> str:
    return request.remote_addr or "desconhecido"       # o ProxyFix já trocou pelo IP real quando há proxy confiável


def _corpo() -> dict:
    if request.content_length and request.content_length > MAX_CORPO:
        raise ErroDominio("Requisição grande demais.", motivo="corpo_grande", status=413)
    corpo = request.get_json(silent=True)
    if not isinstance(corpo, dict):
        raise Invalido("Envie os dados em JSON.", campo="corpo")
    return corpo


@bp.after_request
def _sem_cache(resposta):
    resposta.headers["Cache-Control"] = "no-store"     # o questionário e os tokens nunca devem ficar em cache
    return resposta


@bp.post("/coleta/iniciar")
def iniciar():
    return jsonify(_jogo().iniciar(_corpo().get("codigo"), _ip()))


@bp.post("/partidas")
def partidas():
    corpo = _corpo()
    gravada = _jogo().registrar_partida(corpo.get("uuid"), corpo.get("codigo"), corpo.get("respostas"), _ip())
    p = gravada.partida
    resposta = jsonify({"salvo": True, "duplicada": gravada.duplicada, "acertos": p.total_acertos, "total": p.total_perguntas})
    resposta.status_code = 200 if gravada.duplicada else 201
    return resposta
