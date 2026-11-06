"""Dashboard: endpoints JSON somente leitura. Qualquer usuário logado vê, filtra e exporta (plano, seção 13).

Todos aceitam os mesmos filtros (`questionario` é obrigatório) e passam pelo mesmo construtor em `DashboardService.filtros`."""
from __future__ import annotations

from functools import wraps

from flask import Response, abort, current_app, jsonify, render_template, request
from flask_login import current_user, login_required

from app.blueprints.admin import bp
from app.errors import Invalido
from app.services.dashboard import DIMS_COMPARATIVO

PREFIXO = "/api/dashboard"


@bp.get("/dashboard")
@login_required
def dashboard():
    return render_template("admin/dashboard.html")


def _svc():
    return current_app.extensions["container"].dashboard


def _json(f):
    """Exige login (401 em JSON, sem redirecionar) e proíbe cache: os números mudam a cada partida."""
    @wraps(f)
    def corpo(*a, **kw):
        if not current_user.is_authenticated:
            abort(401)
        resposta = jsonify(f(*a, **kw))
        resposta.headers["Cache-Control"] = "no-store"
        return resposta
    return corpo


def _dim() -> str:
    dim = request.args.get("dim", "")
    if dim not in DIMS_COMPARATIVO:
        raise Invalido(f"Use dim={'|'.join(DIMS_COMPARATIVO)}.", campo="dim")
    return dim


@bp.get(f"{PREFIXO}/questionarios")
@_json
def dash_questionarios():
    return {"itens": _svc().cartoes()}


@bp.get(f"{PREFIXO}/opcoes")
@_json
def dash_opcoes():
    return _svc().opcoes(_svc().filtros(request.args).questionario_id)


@bp.get(f"{PREFIXO}/resumo")
@_json
def dash_resumo():
    return _svc().resumo(_svc().filtros(request.args))


@bp.get(f"{PREFIXO}/questoes")
@_json
def dash_questoes():
    ordem = request.args.get("ordem", "erro")
    if ordem not in ("erro", "acerto"):
        raise Invalido("Use ordem=erro|acerto.", campo="ordem")
    limite = request.args.get("limite", "10")
    if not limite.isdigit() or not 1 <= int(limite) <= 500:
        raise Invalido("O limite deve ser de 1 a 500.", campo="limite")
    return _svc().questoes(_svc().filtros(request.args), menor=ordem == "acerto", limite=int(limite))


@bp.get(f"{PREFIXO}/grupos")
@_json
def dash_grupos():
    return _svc().grupos(_svc().filtros(request.args))


@bp.get(f"{PREFIXO}/comparativo")
@_json
def dash_comparativo():
    return _svc().comparativo(_svc().filtros(request.args), _dim())


@bp.get(f"{PREFIXO}/heatmap")
@_json
def dash_heatmap():
    return _svc().heatmap(_svc().filtros(request.args), _dim())


@bp.get(f"{PREFIXO}/questao/<int:numero>")
@_json
def dash_questao(numero: int):
    return _svc().questao(_svc().filtros(request.args), numero)


@bp.get(f"{PREFIXO}/evolucao")
@_json
def dash_evolucao():
    return _svc().evolucao(_svc().filtros(request.args), request.args.get("passo", "semana"))


@bp.get(f"{PREFIXO}/tabela")
@_json
def dash_tabela():
    return _svc().tabela(_svc().filtros(request.args), request.args.get("aba", "questao"))


@bp.get(f"{PREFIXO}/export.csv")
def dash_export():
    if not current_user.is_authenticated:
        abort(401)
    aba = request.args.get("aba", "questao")
    conteudo = _svc().csv(_svc().filtros(request.args), aba)
    return Response(conteudo, mimetype="text/csv", headers={
        "Content-Disposition": f'attachment; filename="dashboard-{aba}.csv"', "Cache-Control": "no-store"})
