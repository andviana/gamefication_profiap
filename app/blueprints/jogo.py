"""Serve o jogo (arquivos estáticos em app/static/game) na raiz do site."""
from __future__ import annotations

from pathlib import Path

from flask import Blueprint, send_from_directory

bp = Blueprint("jogo", __name__)
PASTA = Path(__file__).resolve().parent.parent / "static" / "game"


@bp.get("/")
def inicio():
    resposta = send_from_directory(PASTA, "index.html", max_age=0)
    resposta.headers["Cache-Control"] = "no-cache"      # a página do jogo é sempre revalidada
    return resposta
