"""Fábrica da aplicação Flask."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Optional

from flask import Flask, request
from sqlalchemy.pool import NullPool
from werkzeug.middleware.proxy_fix import ProxyFix

from app import config
from app.config import Settings, get_settings
from app.auth_web import registrar_carregador
from app.container import montar_container
from app.extensions import csrf, db, login_manager, migrate
from app.http_errors import registrar_handlers


def _configura_log(settings: Settings) -> None:
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger().setLevel(settings.log_level)


CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self'; "
       "connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")


def _cabecalhos_seguranca(settings: Settings):
    """Cabeçalhos de toda resposta. A CSP não admite script inline nem de outra origem (o painel e o jogo só usam
    arquivos próprios); estilo inline continua permitido porque os componentes do gov.br DS e o ECharts o usam."""
    def depois(resposta):
        h = resposta.headers
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Referrer-Policy", "same-origin")
        h.setdefault("Content-Security-Policy", CSP)
        h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=(), usb=()")
        h.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        if settings.eh_producao:
            h.setdefault("Strict-Transport-Security", "max-age=31536000")
        # páginas e JSON do painel nunca ficam em cache (o botão Voltar após sair não pode mostrar dados)
        if request.endpoint != "static":
            h.setdefault("Cache-Control", "no-store")
        return resposta
    return depois


def create_app(settings: Optional[Settings] = None, *, verificar_schema: bool = False) -> Flask:
    """Cria o app. `verificar_schema=True` (usado pelo wsgi.py) falha cedo se o banco estiver desatualizado."""
    settings = settings or get_settings()
    _configura_log(settings)

    app = Flask(__name__, instance_path=str(config.INSTANCE_DIR))
    opcoes_engine = {"pool_pre_ping": True}
    if settings.eh_teste and not settings.usa_sqlite:
        # cada teste cria um app novo; sem pool, as conexões do Postgres não se acumulam até o limite do servidor
        # (no SQLite em memória o pool padrão precisa ficar, senão cada conexão seria um banco vazio)
        opcoes_engine["poolclass"] = NullPool
    app.config.update(
        SECRET_KEY=settings.secret_key,
        SQLALCHEMY_DATABASE_URI=settings.database_url,
        SQLALCHEMY_ENGINE_OPTIONS=opcoes_engine,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        PERMANENT_SESSION_LIFETIME=timedelta(hours=settings.session_horas),
        SESSION_REFRESH_EACH_REQUEST=True,          # a sessão expira por inatividade, não por tempo absoluto
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=settings.cookie_seguro,
        REMEMBER_COOKIE_SECURE=settings.cookie_seguro,
        REMEMBER_COOKIE_HTTPONLY=True,
        # 2 CSVs por importação + folga para os campos do formulário
        MAX_CONTENT_LENGTH=settings.upload_max_bytes * 2 + 64 * 1024,
        WTF_CSRF_ENABLED=not settings.eh_teste,
        JSON_AS_ASCII=False,
    )
    app.extensions["settings"] = settings
    app.extensions["container"] = montar_container(settings)

    if settings.usa_sqlite and ":memory:" not in settings.database_url:
        config.INSTANCE_DIR.mkdir(parents=True, exist_ok=True)

    if settings.proxies_confiaveis:
        n = settings.proxies_confiaveis
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=n, x_proto=n, x_host=n)   # IP real para o rate limit

    db.init_app(app)
    from app import models  # noqa: F401 - registra as tabelas no metadata (migrações e testes)
    from app.models.tipos import render_item
    migrate.init_app(app, db, directory=str(config.MIGRATIONS_DIR), render_as_batch=True, render_item=render_item)
    login_manager.init_app(app)
    registrar_carregador(login_manager)
    csrf.init_app(app)

    from app.blueprints.admin import bp as admin_bp
    from app.blueprints.api import bp as api_bp
    from app.blueprints.auth import bp as auth_bp
    from app.blueprints.jogo import bp as jogo_bp
    from app.blueprints.saude import bp as saude_bp
    app.register_blueprint(saude_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(jogo_bp)
    csrf.exempt(api_bp)       # API pública em JSON, sem sessão nem cookie: não há o que um CSRF forjar
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)

    from app.web_contexto import registrar_contexto
    registrar_contexto(app)

    registrar_handlers(app)
    from app.cli import registrar_comandos
    registrar_comandos(app)
    app.after_request(_cabecalhos_seguranca(settings))

    if verificar_schema:
        from app.db_schema import verificar_schema_atualizado
        with app.app_context():
            verificar_schema_atualizado()

    return app
