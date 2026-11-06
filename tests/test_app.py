import pytest

from app import create_app
from app.config import Settings
from app.errors import Conflito, ErroDominio, Invalido, LimiteExcedido

from conftest import ENV_PRODUCAO, usa_postgres


@pytest.fixture
def app_com_rotas(app):
    @app.get("/api/_dominio")
    def _dominio():
        raise Invalido("Campo X inválido.", campo="x")

    @app.get("/api/_conflito")
    def _conflito():
        raise Conflito()

    @app.get("/api/_limite")
    def _limite():
        raise LimiteExcedido(espera_seg=120)

    @app.get("/api/_boom")
    def _boom():
        raise RuntimeError("segredo interno do servidor")

    @app.get("/painel/_boom")
    def _boom_html():
        raise RuntimeError("segredo interno do servidor")

    @app.get("/painel/_dominio")
    def _dominio_html():
        raise ErroDominio("Falhou de propósito.")

    return app


def test_saude_ok_com_o_schema_migrado(app):
    from flask_migrate import upgrade
    with app.app_context():
        upgrade()
    r = app.test_client().get("/saude")
    assert r.status_code == 200
    assert r.get_json() == {"status": "ok", "ambiente": "testing", "banco": "ok", "schema": "ok"}


def test_saude_degradada_com_banco_sem_migracao(client):
    r = client.get("/saude")
    assert r.status_code == 503
    assert r.get_json() == {"status": "degradado", "ambiente": "testing", "banco": "ok", "schema": "ausente"}


def test_settings_e_container_ficam_no_app(app, settings):
    assert app.extensions["settings"] is settings
    assert app.extensions["container"].settings is settings


def test_erro_de_dominio_vira_json_na_api(app_com_rotas):
    r = app_com_rotas.test_client().get("/api/_dominio")
    assert r.status_code == 422
    assert r.get_json() == {"erro": {"codigo": 422, "motivo": "invalido", "mensagem": "Campo X inválido.", "detalhes": {"campo": "x"}}}


def test_conflito_tem_status_409(app_com_rotas):
    assert app_com_rotas.test_client().get("/api/_conflito").status_code == 409


def test_limite_envia_retry_after(app_com_rotas):
    r = app_com_rotas.test_client().get("/api/_limite")
    assert r.status_code == 429 and r.headers["Retry-After"] == "120"
    assert r.get_json()["erro"]["detalhes"]["espera_seg"] == 120


def test_erro_inesperado_nao_vaza_detalhes(app_com_rotas):
    app_com_rotas.config["PROPAGATE_EXCEPTIONS"] = False
    c = app_com_rotas.test_client()
    j = c.get("/api/_boom")
    assert j.status_code == 500 and "segredo" not in j.get_data(as_text=True)
    assert j.get_json()["erro"]["motivo"] == "erro_interno"
    h = c.get("/painel/_boom")
    assert h.status_code == 500 and "segredo" not in h.get_data(as_text=True) and "text/html" in h.content_type


def test_painel_recebe_pagina_html(app_com_rotas):
    r = app_com_rotas.test_client().get("/painel/_dominio")
    assert r.status_code == 400 and "text/html" in r.content_type and "Falhou de propósito." in r.get_data(as_text=True)


def test_404_html_e_json(client):
    html = client.get("/nao-existe")
    assert html.status_code == 404 and "text/html" in html.content_type
    api = client.get("/api/nao-existe")
    assert api.status_code == 404 and api.get_json()["erro"]["motivo"] == "nao_encontrado"


def test_405_na_api(client):
    r = client.post("/saude")
    assert r.status_code == 405


def test_cabecalhos_de_seguranca(client):
    h = client.get("/saude").headers
    assert h["X-Content-Type-Options"] == "nosniff" and h["X-Frame-Options"] == "DENY" and h["Referrer-Policy"] == "same-origin"


def test_upload_acima_do_limite_e_recusado(app):
    @app.post("/api/_upload")
    def _up():
        from flask import request
        request.files  # força a leitura do corpo
        return "ok"

    grande = b"x" * (app.config["MAX_CONTENT_LENGTH"] + 10)
    r = app.test_client().post("/api/_upload", data={"f": (__import__("io").BytesIO(grande), "a.csv")})
    assert r.status_code == 413 and r.get_json()["erro"]["motivo"] == "arquivo_grande_demais"


def test_producao_liga_cookie_seguro_e_csrf():
    app = create_app(Settings.from_env(ENV_PRODUCAO))
    assert app.config["SESSION_COOKIE_SECURE"] and app.config["SESSION_COOKIE_HTTPONLY"]
    assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax" and app.config["WTF_CSRF_ENABLED"]
    assert app.config["PERMANENT_SESSION_LIFETIME"].total_seconds() == 8 * 3600


def test_teste_desliga_csrf_e_cookie_seguro(app):
    assert not app.config["WTF_CSRF_ENABLED"] and not app.config["SESSION_COOKIE_SECURE"]


def test_proxy_confiavel_usa_ip_do_x_forwarded_for():
    app = create_app(Settings.from_env({"APP_ENV": "testing", "PROXIES_CONFIAVEIS": "1"}))

    @app.get("/api/_ip")
    def _ip():
        from flask import request
        return request.remote_addr

    r = app.test_client().get("/api/_ip", headers={"X-Forwarded-For": "200.1.2.3"})
    assert r.get_data(as_text=True) == "200.1.2.3"
    sem_proxy = create_app(Settings.from_env({"APP_ENV": "testing"}))
    sem_proxy.get("/api/_ip", endpoint="ip2")(lambda: __import__("flask").request.remote_addr)
    assert sem_proxy.test_client().get("/api/_ip", headers={"X-Forwarded-For": "200.1.2.3"}).get_data(as_text=True) != "200.1.2.3"


@pytest.mark.skipif(usa_postgres, reason="específico do SQLite")
def test_sqlite_aplica_chaves_estrangeiras(app):
    from sqlalchemy import text
    from app.extensions import db
    with app.app_context():
        assert db.session.execute(text("PRAGMA foreign_keys")).scalar() == 1
