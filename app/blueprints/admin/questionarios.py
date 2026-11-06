"""Questionários: lista, criação, edição, orientações, duplicar e excluir. Qualquer usuário logado (comum inclusive)."""
from __future__ import annotations

from flask import current_app, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from app.blueprints.admin import bp
from app.blueprints.admin.forms import OrientacoesForm, QuestionarioForm
from app.blueprints.formularios import aplica_erro
from app.errors import ErroDominio

DICA_ESTADO = {
    "rascunho": "Rascunho: ainda sem coletas. A estrutura é livre.",
    "em coleta": "Já tem coleta, mas ainda sem respostas. A estrutura trava na primeira resposta recebida.",
    "travado": "Travado: já há respostas. Só é possível corrigir textos; para mudar a estrutura, duplique o questionário.",
}


def _c():
    return current_app.extensions["container"]


def _ator():
    return current_user._get_current_object()


@bp.get("/questionarios")
@login_required
def questionarios_lista():
    return render_template("admin/questionarios/lista.html", itens=_c().questionarios.listar())


@bp.route("/questionarios/novo", methods=["GET", "POST"])
@login_required
def questionarios_novo():
    form = QuestionarioForm()
    if form.validate_on_submit():
        try:
            q = _c().questionarios.criar(_ator(), form.nome.data, form.descricao.data)
        except ErroDominio as erro:
            aplica_erro(form, erro)
        else:
            flash("Questionário criado como rascunho. Agora cadastre as perguntas.", "success")
            return redirect(url_for("admin.questionarios_detalhe", questionario_id=q.id))
    return render_template("admin/questionarios/form.html", form=form, titulo="Novo questionário", q=None), \
        (422 if form.errors else 200)


@bp.get("/questionarios/<int:questionario_id>")
@login_required
def questionarios_detalhe(questionario_id: int):
    svc = _c().questionarios
    q = svc.obter(questionario_id)
    resumo = svc.resumo(q)
    derivado = svc.repo.por_id(q.derivado_de_id) if q.derivado_de_id else None
    return render_template("admin/questionarios/detalhe.html", q=q, resumo=resumo, dica=DICA_ESTADO[resumo.estado],
                           derivado=derivado)


@bp.route("/questionarios/<int:questionario_id>/editar", methods=["GET", "POST"])
@login_required
def questionarios_editar(questionario_id: int):
    svc = _c().questionarios
    q = svc.obter(questionario_id)
    form = QuestionarioForm(obj=q)
    if form.validate_on_submit():
        try:
            svc.editar(_ator(), questionario_id, form.nome.data, form.descricao.data)
        except ErroDominio as erro:
            aplica_erro(form, erro)
        else:
            flash("Questionário atualizado.", "success")
            return redirect(url_for("admin.questionarios_detalhe", questionario_id=questionario_id))
    return render_template("admin/questionarios/form.html", form=form, titulo=f"Editar “{q.nome}”", q=q), \
        (422 if form.errors else 200)


@bp.route("/questionarios/<int:questionario_id>/orientacoes", methods=["GET", "POST"])
@login_required
def questionarios_orientacoes(questionario_id: int):
    svc = _c().questionarios
    q = svc.obter(questionario_id)
    form = OrientacoesForm(obj=q)
    if form.validate_on_submit():
        try:
            svc.atualizar_orientacoes(_ator(), questionario_id, form.orientacoes.data)
        except ErroDominio as erro:
            aplica_erro(form, erro)
        else:
            flash("Orientações atualizadas. Vale também para coletas em andamento.", "success")
            return redirect(url_for("admin.questionarios_detalhe", questionario_id=questionario_id))
    return render_template("admin/questionarios/orientacoes.html", form=form, q=q), (422 if form.errors else 200)


@bp.post("/questionarios/<int:questionario_id>/duplicar")
@login_required
def questionarios_duplicar(questionario_id: int):
    copia = _c().questionarios.duplicar(_ator(), questionario_id)
    flash(f"Criado o rascunho “{copia.nome}”, com as mesmas perguntas e orientações. A estrutura dele é livre.", "success")
    return redirect(url_for("admin.questionarios_detalhe", questionario_id=copia.id))


@bp.post("/questionarios/<int:questionario_id>/excluir")
@login_required
def questionarios_excluir(questionario_id: int):
    svc = _c().questionarios
    nome = svc.obter(questionario_id).nome
    svc.excluir(_ator(), questionario_id)
    flash(f"Questionário “{nome}” excluído.", "success")
    return redirect(url_for("admin.questionarios_lista"))
