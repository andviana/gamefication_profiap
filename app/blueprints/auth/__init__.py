"""Entrada no sistema: setup do primeiro acesso, login, logout e troca da própria senha."""
from __future__ import annotations

import math

from flask import Blueprint, abort, current_app, flash, get_flashed_messages, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app.auth_web import proximo_seguro
from app.blueprints.auth.forms import AlterarSenhaForm, LoginForm, SetupForm
from app.blueprints.formularios import aplica_erro
from app.errors import CredenciaisInvalidas, ErroDominio, LimiteExcedido, NaoEncontrado

bp = Blueprint("auth", __name__)


def _c():
    return current_app.extensions["container"]


def _inicia_sessao(usuario) -> None:
    session.clear()           # evita fixação de sessão
    login_user(usuario)
    session.permanent = True  # validade por inatividade (SESSION_HORAS)


@bp.route("/setup", methods=["GET", "POST"])
def setup():
    """Primeiro acesso: cria o super admin raiz. Só existe enquanto não há nenhum usuário (depois, 404)."""
    c = _c()
    if c.usuarios.existe_algum():
        abort(404)
    form = SetupForm()
    if form.validate_on_submit():
        try:
            usuario = c.usuarios.criar_raiz(form.nome.data, form.login.data, form.senha.data, form.confirmacao.data)
        except NaoEncontrado:   # alguém concluiu o setup um instante antes
            abort(404)
        except ErroDominio as erro:
            aplica_erro(form, erro)
        else:
            _inicia_sessao(usuario)
            flash("Super admin criado. Bem-vindo(a)!", "success")
            return redirect(url_for("admin.index"))
    return render_template("auth/setup.html", form=form), (422 if form.errors else 200)


@bp.route("/entrar", methods=["GET", "POST"])
def entrar():
    c = _c()
    if not c.usuarios.existe_algum():
        get_flashed_messages()   # descarta "Entre para continuar", que não faz sentido antes do primeiro usuário
        return redirect(url_for("auth.setup"))
    if current_user.is_authenticated:
        return redirect(url_for("admin.index"))
    form = LoginForm()
    status = 200
    if form.validate_on_submit():
        try:
            usuario = c.auth.autenticar(form.login.data, form.senha.data)
        except LimiteExcedido as erro:
            minutos = max(1, math.ceil(erro.espera_seg / 60))
            flash(f"Muitas tentativas. Tente de novo em cerca de {minutos} min.", "danger")
            status = 429
        except CredenciaisInvalidas as erro:
            flash(erro.mensagem, "danger")
            status = 401
        else:
            destino = proximo_seguro(request.args.get("next"))
            _inicia_sessao(usuario)
            return redirect(destino or url_for("admin.index"))
    elif form.errors:
        status = 422
    return render_template("auth/login.html", form=form), status


@bp.post("/sair")
def sair():
    logout_user()
    session.clear()
    flash("Você saiu do sistema.", "info")
    return redirect(url_for("auth.entrar"))


@bp.route("/conta/senha", methods=["GET", "POST"])
@login_required
def alterar_senha():
    """Qualquer usuário (inclusive a raiz) troca a própria senha informando a atual."""
    form = AlterarSenhaForm()
    if form.validate_on_submit():
        try:
            _c().usuarios.alterar_propria_senha(current_user._get_current_object(), form.atual.data,
                                                form.nova.data, form.confirmacao.data)
        except ErroDominio as erro:
            aplica_erro(form, erro)
        else:
            _inicia_sessao(current_user._get_current_object())   # o token mudou: mantém esta sessão, derruba as outras
            flash("Senha alterada. As outras sessões abertas foram encerradas.", "success")
            return redirect(url_for("admin.index"))
    return render_template("auth/senha.html", form=form), (422 if form.errors else 200)
