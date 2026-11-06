"""Tradução única de exceções em resposta HTTP: JSON para a API, página HTML para o painel."""
from __future__ import annotations

import logging

from flask import Flask, jsonify, make_response, render_template, request
from werkzeug.exceptions import HTTPException

from app.errors import ErroDominio, LimiteExcedido

log = logging.getLogger(__name__)

_MOTIVOS_HTTP = {
    400: "requisicao_invalida", 401: "nao_autenticado", 403: "proibido", 404: "nao_encontrado",
    405: "metodo_nao_permitido", 413: "arquivo_grande_demais", 429: "limite_excedido",
}
_MENSAGENS_HTTP = {
    400: "Requisição inválida.", 401: "É preciso entrar para continuar.", 403: "Você não tem permissão para esta ação.",
    404: "Página ou recurso não encontrado.", 405: "Método não permitido.", 413: "O arquivo enviado é grande demais.",
    429: "Muitas tentativas. Aguarde um pouco e tente de novo.",
}


def _quer_json() -> bool:
    if request.path.startswith("/api/") or request.path.startswith("/admin/api/"):
        return True
    melhor = request.accept_mimetypes.best_match(["application/json", "text/html"])
    return melhor == "application/json" and request.accept_mimetypes[melhor] > request.accept_mimetypes["text/html"]


def _responde(status: int, motivo: str, mensagem: str, detalhes: dict | None = None, cabecalhos: dict | None = None):
    if _quer_json():
        corpo = {"erro": {"codigo": status, "motivo": motivo, "mensagem": mensagem}}
        if detalhes:
            corpo["erro"]["detalhes"] = detalhes
        resposta = jsonify(corpo)
    else:
        resposta = _pagina(status, mensagem)
    resposta.status_code = status
    for chave, valor in (cabecalhos or {}).items():
        resposta.headers[chave] = valor
    return resposta


def _pagina(status: int, mensagem: str):
    try:
        return make_response(render_template("erro.html", status=status, mensagem=mensagem), status)
    except Exception:  # noqa: BLE001 - o tratamento de erro nunca pode falhar por conta própria
        log.exception("Falha ao renderizar a página de erro")
        return make_response(f"Erro {status}: {mensagem}", status, {"Content-Type": "text/plain; charset=utf-8"})


def registrar_handlers(app: Flask) -> None:
    @app.errorhandler(ErroDominio)
    def _dominio(erro: ErroDominio):
        cabecalhos = {}
        if isinstance(erro, LimiteExcedido) and erro.espera_seg:
            cabecalhos["Retry-After"] = str(erro.espera_seg)
        return _responde(erro.status, erro.motivo, erro.mensagem, erro.detalhes, cabecalhos)

    @app.errorhandler(HTTPException)
    def _http(erro: HTTPException):
        status = erro.code or 500
        motivo = _MOTIVOS_HTTP.get(status, "erro_http")
        return _responde(status, motivo, _MENSAGENS_HTTP.get(status, erro.name))

    @app.errorhandler(Exception)
    def _inesperado(erro: Exception):
        # nunca devolve detalhes internos ao cliente; o stack vai só para o log
        log.exception("Erro inesperado em %s %s", request.method, request.path)
        return _responde(500, "erro_interno", "Ocorreu um erro inesperado. Tente novamente em instantes.")
