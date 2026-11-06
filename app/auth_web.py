"""Peças de autenticação ligadas ao Flask: carregador de sessão e decoradores de permissão."""
from __future__ import annotations

import hmac
from functools import wraps

from flask_login import current_user, login_required

from app.errors import Proibido
from app.extensions import db
from app.models import Usuario


def registrar_carregador(login_manager) -> None:
    """A sessão guarda `id:token`. Trocar o token do usuário (senha ou perfil alterados por outra pessoa) derruba a sessão."""
    login_manager.login_view = "auth.entrar"
    login_manager.login_message = "Entre para continuar."
    login_manager.login_message_category = "info"

    @login_manager.user_loader
    def _carrega(valor: str):
        try:
            usuario_id, token = valor.split(":", 1)
            usuario = db.session.get(Usuario, int(usuario_id))
        except (ValueError, AttributeError):
            return None
        if usuario is not None and hmac.compare_digest(usuario.sessao_token, token):
            return usuario
        return None


def superadmin_required(funcao):
    """Rota só para super admins (raiz ou promovido). Não logado vai para o login; comum recebe 403."""
    @wraps(funcao)
    @login_required
    def _protegida(*args, **kwargs):
        if not current_user.eh_superadmin:
            raise Proibido()
        return funcao(*args, **kwargs)
    return _protegida


def proximo_seguro(destino: str | None) -> str | None:
    """Só aceita redirecionamento para um caminho local (evita redirecionar para outro site)."""
    if destino and destino.startswith("/") and not destino.startswith("//") and "\\" not in destino:
        return destino
    return None
