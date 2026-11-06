"""Importação de questionários por CSV (só super admin): upload -> prévia -> confirmação. Cria um questionário novo."""
from __future__ import annotations

from flask import Response, abort, current_app, flash, redirect, render_template, url_for
from flask_login import current_user

from app.auth_web import superadmin_required
from app.blueprints.admin import bp
from app.blueprints.admin.forms import ConfirmarImportacaoForm, ImportacaoForm
from app.blueprints.formularios import aplica_erro
from app.errors import ErroDominio

MODELOS = {
    "perguntas.csv": "Número da pergunta;Pergunta;Título;Grupo;Autoajuda\n"
                     "1;Você recebe um e-mail urgente pedindo a sua senha. O que fazer?;Phishing;Segurança Digital;"
                     "Instituições sérias não pedem senhas por e-mail.\n",
    "alternativas.csv": "Número da pergunta;Letra;Texto da alternativa;Correta ou incorreta;Texto de acerto;Texto de erro\n"
                        "1;A;Clicar no link e informar a senha;Incorreta;;Links inesperados podem roubar credenciais.\n"
                        "1;B;Não clicar e reportar à TI;Correta;Correto: desconfie de urgência.;\n",
}
MAX_ERROS_NA_TELA = 100


def _svc():
    return current_app.extensions["container"].importacao


def _ator():
    return current_user._get_current_object()


def _tela_upload(form, erros=None, avisos=None, status=None):
    erros = erros or []
    return render_template("admin/importacao/upload.html", form=form, erros=erros[:MAX_ERROS_NA_TELA],
                           n_erros=len(erros), avisos=avisos or []), status or (422 if (form.errors or erros) else 200)


@bp.route("/importar", methods=["GET", "POST"])
@superadmin_required
def importar():
    form = ImportacaoForm()
    if not form.validate_on_submit():
        return _tela_upload(form)
    p, a = form.arquivo_perguntas.data, form.arquivo_alternativas.data
    try:
        previa = _svc().analisar(_ator(), form.nome.data, form.descricao.data,
                                 (p.filename or "", p.read()), (a.filename or "", a.read()))
    except ErroDominio as erro:
        return _tela_upload(form, status=aplica_erro(form, erro))
    if not previa.ok:
        return _tela_upload(form, erros=previa.analise.erros, avisos=previa.analise.avisos)
    confirmar = ConfirmarImportacaoForm(token=previa.token)
    validade = current_app.extensions["settings"].previa_validade_min
    return render_template("admin/importacao/previa.html", previa=previa, form=confirmar, validade=validade)


@bp.post("/importar/confirmar")
@superadmin_required
def importar_confirmar():
    form = ConfirmarImportacaoForm()
    if not form.validate_on_submit():
        flash("Não foi possível confirmar: envie os arquivos de novo.", "danger")
        return redirect(url_for("admin.importar"))
    questionario = _svc().confirmar(_ator(), form.token.data)
    flash(f"Questionário “{questionario.nome}” importado como rascunho, com {len(questionario.perguntas)} perguntas.", "success")
    return redirect(url_for("admin.questionarios_detalhe", questionario_id=questionario.id))


@bp.get("/importar/modelo/<arquivo>")
@superadmin_required
def importar_modelo(arquivo: str):
    if arquivo not in MODELOS:
        abort(404)
    return Response("﻿" + MODELOS[arquivo], mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="modelo-{arquivo}"'})
