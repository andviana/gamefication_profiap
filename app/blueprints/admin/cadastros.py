"""Cadastros de apoio: campus, curso e grupo. Qualquer usuário logado gerencia; nada é apagado, só inativado."""
from __future__ import annotations

from flask import abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.blueprints.admin import bp
from app.blueprints.admin.forms import ReferenciaForm
from app.blueprints.formularios import aplica_erro
from app.errors import ErroDominio

# rótulos no singular e no plural, e o que "em uso" significa em cada tipo
TIPOS = {
    "campus": {"singular": "campus", "plural": "Campus", "uso": "coletas"},
    "curso": {"singular": "curso", "plural": "Cursos", "uso": "coletas"},
    "grupo": {"singular": "grupo", "plural": "Grupos", "uso": "perguntas"},
}


def _servico(tipo: str):
    if tipo not in TIPOS:
        abort(404)
    return current_app.extensions["container"].referencias[tipo]


def _ator():
    return current_user._get_current_object()


@bp.route("/cadastros/<tipo>", methods=["GET", "POST"])
@login_required
def cadastros(tipo: str):
    svc = _servico(tipo)
    form = ReferenciaForm()
    if form.validate_on_submit():
        try:
            registro = svc.criar(_ator(), form.nome.data)
        except ErroDominio as erro:
            aplica_erro(form, erro)
        else:
            flash(f"{TIPOS[tipo]['singular'].capitalize()} “{registro.nome}” cadastrado.", "success")
            return redirect(url_for("admin.cadastros", tipo=tipo))
    return render_template("admin/cadastros/lista.html", tipo=tipo, info=TIPOS[tipo], tipos=TIPOS,
                           itens=svc.listar(), form=form), (422 if form.errors else 200)


@bp.route("/cadastros/<tipo>/<int:ref_id>/editar", methods=["GET", "POST"])
@login_required
def cadastros_editar(tipo: str, ref_id: int):
    svc = _servico(tipo)
    registro = svc.obter(ref_id)
    form = ReferenciaForm(obj=registro)
    if form.validate_on_submit():
        try:
            svc.renomear(_ator(), ref_id, form.nome.data)
        except ErroDominio as erro:
            aplica_erro(form, erro)
        else:
            flash("Nome atualizado.", "success")
            return redirect(url_for("admin.cadastros", tipo=tipo))
    return render_template("admin/cadastros/editar.html", tipo=tipo, info=TIPOS[tipo], registro=registro, form=form), \
        (422 if form.errors else 200)


@bp.post("/cadastros/<tipo>/<int:ref_id>/ativo")
@login_required
def cadastros_ativo(tipo: str, ref_id: int):
    ativo = request.form.get("ativo") == "1"
    registro = _servico(tipo).definir_ativo(_ator(), ref_id, ativo)
    flash(f"“{registro.nome}” {'reativado' if ativo else 'inativado'}.", "success")
    return redirect(url_for("admin.cadastros", tipo=tipo))
