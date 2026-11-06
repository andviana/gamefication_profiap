"""CRUD de usuários (só super admin). As regras de quem pode fazer o quê ficam em app.permissoes e no service."""
from __future__ import annotations

from flask import current_app, flash, redirect, render_template, url_for
from flask_login import current_user

from app.auth_web import superadmin_required
from app.blueprints.admin import bp
from app.blueprints.admin.forms import EditarUsuarioForm, NovoUsuarioForm, RedefinirSenhaForm
from app.blueprints.formularios import aplica_erro
from app.errors import ErroDominio


def _svc():
    return current_app.extensions["container"].usuarios


def _ator():
    return current_user._get_current_object()


@bp.get("/usuarios")
@superadmin_required
def usuarios_lista():
    return render_template("admin/usuarios/lista.html", usuarios=_svc().listar())


@bp.route("/usuarios/novo", methods=["GET", "POST"])
@superadmin_required
def usuarios_novo():
    form = NovoUsuarioForm()
    if form.validate_on_submit():
        try:
            usuario = _svc().criar(_ator(), form.nome.data, form.login.data, form.senha.data, form.confirmacao.data)
        except ErroDominio as erro:
            aplica_erro(form, erro)
        else:
            flash(f"Usuário {usuario.login} criado.", "success")
            return redirect(url_for("admin.usuarios_lista"))
    return render_template("admin/usuarios/form.html", form=form, titulo="Novo usuário", alvo=None), \
        (422 if form.errors else 200)


@bp.route("/usuarios/<int:usuario_id>/editar", methods=["GET", "POST"])
@superadmin_required
def usuarios_editar(usuario_id: int):
    alvo = _svc().obter_gerenciavel(_ator(), usuario_id)       # 404 se não existe, 403 se não pode
    form = EditarUsuarioForm(obj=alvo)
    if form.validate_on_submit():
        try:
            _svc().editar(_ator(), usuario_id, form.nome.data, form.login.data)
        except ErroDominio as erro:
            aplica_erro(form, erro)
        else:
            flash("Usuário atualizado.", "success")
            return redirect(url_for("admin.usuarios_lista"))
    return render_template("admin/usuarios/form.html", form=form, titulo=f"Editar {alvo.login}", alvo=alvo), \
        (422 if form.errors else 200)


@bp.route("/usuarios/<int:usuario_id>/senha", methods=["GET", "POST"])
@superadmin_required
def usuarios_senha(usuario_id: int):
    alvo = _svc().obter_gerenciavel(_ator(), usuario_id)
    form = RedefinirSenhaForm()
    if form.validate_on_submit():
        try:
            _svc().redefinir_senha(_ator(), usuario_id, form.nova.data, form.confirmacao.data)
        except ErroDominio as erro:
            aplica_erro(form, erro)
        else:
            flash(f"Senha de {alvo.login} redefinida. As sessões abertas dele(a) foram encerradas.", "success")
            return redirect(url_for("admin.usuarios_lista"))
    return render_template("admin/usuarios/senha.html", form=form, alvo=alvo), (422 if form.errors else 200)


def _acao_post(usuario_id: int, metodo: str, mensagem: str):
    try:
        alvo = getattr(_svc(), metodo)(_ator(), usuario_id)
    except ErroDominio:
        raise   # 403 / 404 / 409 pelo handler único
    flash(mensagem.format(login=getattr(alvo, "login", "")), "success")
    return redirect(url_for("admin.usuarios_lista"))


@bp.post("/usuarios/<int:usuario_id>/promover")
@superadmin_required
def usuarios_promover(usuario_id: int):
    return _acao_post(usuario_id, "promover", "{login} agora é super admin.")


@bp.post("/usuarios/<int:usuario_id>/revogar")
@superadmin_required
def usuarios_revogar(usuario_id: int):
    return _acao_post(usuario_id, "revogar", "{login} voltou a ser usuário comum.")


@bp.post("/usuarios/<int:usuario_id>/excluir")
@superadmin_required
def usuarios_excluir(usuario_id: int):
    alvo = _svc().obter(usuario_id)
    login = alvo.login
    _svc().excluir(_ator(), usuario_id)
    flash(f"Usuário {login} excluído.", "success")
    return redirect(url_for("admin.usuarios_lista"))
