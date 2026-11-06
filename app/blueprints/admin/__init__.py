"""Painel administrativo (rotas protegidas por login)."""
from __future__ import annotations

from flask import Blueprint, render_template
from flask_login import login_required

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.get("/")
@login_required
def index():
    return render_template("admin/index.html")


from app.blueprints.admin import cadastros, coletas, dashboard, importacao, perguntas, questionarios, usuarios  # noqa: E402,F401  (registram suas rotas neste blueprint)
