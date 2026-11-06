"""Coletas: cada uma é uma turma com um código de acesso. Qualquer usuário logado gerencia."""
from __future__ import annotations

from datetime import timedelta
from typing import Optional

from flask import current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.blueprints.admin import bp
from app.blueprints.admin.forms import ColetaForm
from app.blueprints.formularios import aplica_erro
from app.errors import Duplicidade, ErroDominio
from app.models import Coleta
from app.services.coletas import ABERTA, AGENDADA, DESATIVADA, ENCERRADA, DadosColeta
from app.services.questionarios import RASCUNHO

SITUACOES = {ABERTA: "Abertas", AGENDADA: "Agendadas", ENCERRADA: "Encerradas", DESATIVADA: "Desativadas"}
EXPLICA_SITUACAO = {
    ABERTA: "Dentro do prazo e ativa: os alunos conseguem entrar com o código.",
    AGENDADA: "Ainda não começou: o código só vale a partir da data de início.",
    ENCERRADA: "O prazo acabou: o código não aceita mais alunos. Prorrogue a data de fim para reabrir.",
    DESATIVADA: "Desativada manualmente: o código não funciona, mesmo dentro do prazo.",
}


def _c():
    return current_app.extensions["container"]


def _ator():
    return current_user._get_current_object()


def _opcoes(form: ColetaForm, atual: Optional[Coleta] = None) -> None:
    """Preenche as listas de escolha. Só entram registros ativos (e o valor atual da coleta, mesmo se inativo/antigo)."""
    c = _c()
    esc = [(0, "Escolha…")]
    form.questionario_id.choices = esc + [
        (q.id, f"{q.nome} ({r.estado})") for q, r in c.questionarios.listar() if r.n_perguntas or (atual and q.id == atual.questionario_id)]
    for campo, tipo, atual_id in (("campus_id", "campus", atual.campus_id if atual else None),
                                  ("curso_id", "curso", atual.curso_id if atual else None)):
        getattr(form, campo).choices = esc + [(r.id, r.nome + ("" if r.ativo else " (inativo)"))
                                              for r in c.referencias[tipo].repo.listar() if r.ativo or r.id == atual_id]
    anos = set(c.coletas.anos_validos()) | ({atual.ano} if atual else set())
    form.ano.choices = [(a, str(a)) for a in sorted(anos)]
    form.periodo.choices = [(1, "1º período"), (2, "2º período")]


def _dados(form: ColetaForm) -> DadosColeta:
    return DadosColeta(questionario_id=form.questionario_id.data or 0, campus_id=form.campus_id.data or 0,
                       curso_id=form.curso_id.data or 0, ano=form.ano.data or 0, periodo=form.periodo.data or 0,
                       data_inicio=form.data_inicio.data, data_fim=form.data_fim.data)


def _formulario_novo() -> ColetaForm:
    """Valores sugeridos para uma coleta nova: hoje, ano e semestre correntes, 30 dias de prazo."""
    hoje = _c().coletas.hoje()
    return ColetaForm(data={"ano": hoje.year, "periodo": 1 if hoje.month <= 6 else 2, "data_inicio": hoje,
                            "data_fim": hoje + timedelta(days=30)})


@bp.get("/coletas")
@login_required
def coletas_lista():
    svc = _c().coletas
    try:
        questionario_id = int(request.args.get("questionario", "") or 0) or None
    except ValueError:
        questionario_id = None
    situacao = request.args.get("situacao") if request.args.get("situacao") in SITUACOES else None
    return render_template("admin/coletas/lista.html", itens=svc.listar(questionario_id, situacao), situacoes=SITUACOES,
                           questionarios=[q for q, _ in _c().questionarios.listar()], filtro_q=questionario_id,
                           filtro_s=situacao, total=len(svc.listar()))


@bp.route("/coletas/nova", methods=["GET", "POST"])
@login_required
def coletas_nova():
    svc = _c().coletas
    form = ColetaForm() if request.method == "POST" else _formulario_novo()
    _opcoes(form)
    status, duplicadas = None, []
    if request.method == "POST" and form.validate_on_submit():
        dados = _dados(form)
        antes = _c().questionarios.repo.por_id(dados.questionario_id)
        era_rascunho = antes is not None and _c().questionarios.resumo(antes).estado == RASCUNHO
        try:
            coleta = svc.criar(_ator(), dados, duplicidade_confirmada=request.form.get("confirmar_duplicidade") == "1")
        except Duplicidade as aviso:
            duplicadas = aviso.existentes
        except ErroDominio as erro:
            status = aplica_erro(form, erro)
        else:
            flash(f"Coleta criada. Código de acesso: {coleta.codigo}", "success")
            if era_rascunho:
                flash("O questionário passou de “rascunho” para “em coleta”: a estrutura dele trava na primeira resposta recebida. "
                      "Corrija as perguntas antes de divulgar o código.", "warning")
            return redirect(url_for("admin.coletas_detalhe", coleta_id=coleta.id))
    return render_template("admin/coletas/form.html", form=form, titulo="Nova coleta", coleta=None, travada=False,
                           duplicadas=duplicadas, fuso=_c().settings.timezone), status or (422 if form.errors else 200)


@bp.get("/coletas/<int:coleta_id>")
@login_required
def coletas_detalhe(coleta_id: int):
    svc = _c().coletas
    coleta = svc.obter(coleta_id)
    sit = svc.situacao(coleta)
    return render_template("admin/coletas/detalhe.html", coleta=coleta, situacao=sit, explica=EXPLICA_SITUACAO[sit],
                           n_partidas=svc.n_partidas(coleta), fuso=_c().settings.timezone,
                           estado_questionario=_c().questionarios.resumo(coleta.questionario).estado)


@bp.route("/coletas/<int:coleta_id>/editar", methods=["GET", "POST"])
@login_required
def coletas_editar(coleta_id: int):
    svc = _c().coletas
    coleta = svc.obter(coleta_id)
    travada = svc.n_partidas(coleta) > 0
    form = ColetaForm() if request.method == "POST" else ColetaForm(obj=coleta)
    _opcoes(form, coleta)
    status, duplicadas = None, []
    if request.method == "POST" and form.validate_on_submit():
        dados = _dados(form)
        if travada:   # a identidade da turma não vem do formulário: fica como está (os campos nem são enviados)
            for campo in svc.IDENTIDADE:
                setattr(dados, campo, getattr(coleta, campo))
        try:
            svc.editar(_ator(), coleta_id, dados, duplicidade_confirmada=request.form.get("confirmar_duplicidade") == "1")
        except Duplicidade as aviso:
            duplicadas = aviso.existentes
        except ErroDominio as erro:
            status = aplica_erro(form, erro)
        else:
            flash("Coleta atualizada.", "success")
            return redirect(url_for("admin.coletas_detalhe", coleta_id=coleta_id))
    return render_template("admin/coletas/form.html", form=form, titulo=f"Editar a coleta {coleta.codigo}", coleta=coleta,
                           travada=travada, duplicadas=duplicadas, fuso=_c().settings.timezone), status or (422 if form.errors else 200)


@bp.post("/coletas/<int:coleta_id>/ativo")
@login_required
def coletas_ativo(coleta_id: int):
    ativo = request.form.get("ativo") == "1"
    coleta = _c().coletas.definir_ativo(_ator(), coleta_id, ativo)
    flash(f"Coleta {coleta.codigo} {'ativada' if ativo else 'desativada'}.", "success")
    return redirect(url_for("admin.coletas_detalhe", coleta_id=coleta_id))
