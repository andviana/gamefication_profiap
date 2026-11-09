"""Revisão de segurança (Fase 7): varre TODAS as rotas, para que uma rota nova esquecida seja pega aqui."""
import logging
import re

from app import create_app
from app.config import Settings, reset_settings

from conftest import SENHA, cria_mundo, logado, texto, web  # noqa: F401

PUBLICAS_SEM_LOGIN = {"static", "saude.saude", "jogo.inicio", "api.iniciar", "api.partidas", "auth.entrar", "auth.setup"}


def _regras(web, metodos):
    """(rota, regra) com URL montada, para as rotas que aceitam algum dos métodos dados."""
    for regra in web.url_map.iter_rules():
        if regra.endpoint == "static" or not (regra.methods & set(metodos)):
            continue
        url = re.sub(r"<(?:int:)?\w+>", "1", regra.rule)
        yield regra, url


def test_toda_rota_de_escrita_exige_token_csrf_exceto_a_api_publica(web):
    cria_mundo(web)
    cli = logado(web, "raiz")           # autenticado: a recusa tem de vir do CSRF, não do login
    web.config["WTF_CSRF_ENABLED"] = True
    sem_token = []
    for regra, url in _regras(web, {"POST", "PUT", "PATCH", "DELETE"}):
        if regra.endpoint.startswith("api."):
            continue
        r = cli.open(url, method=sorted(regra.methods & {"POST", "PUT", "PATCH", "DELETE"})[0])
        if r.status_code != 400:
            sem_token.append((regra.endpoint, r.status_code))
    assert not sem_token, f"rotas de escrita sem proteção CSRF: {sem_token}"


def test_toda_rota_do_painel_exige_login(web):
    cria_mundo(web)
    anonimo = web.test_client()
    abertas = []
    for regra, url in _regras(web, {"GET", "POST"}):
        if regra.endpoint in PUBLICAS_SEM_LOGIN or not regra.endpoint.startswith("admin."):
            continue
        metodo = "GET" if "GET" in regra.methods else "POST"
        r = anonimo.open(url, method=metodo)
        if r.status_code not in (302, 401):
            abertas.append((regra.endpoint, r.status_code))
        if r.status_code == 302:
            assert "/entrar" in r.headers["Location"], regra.endpoint
    assert not abertas, f"rotas do painel acessíveis sem login: {abertas}"


def test_so_as_rotas_esperadas_sao_publicas(web):
    """Falha quando alguém cria uma rota nova fora do painel: ela tem de ser decidida de propósito."""
    cria_mundo(web)
    anonimo = web.test_client()
    publicas = set()
    for regra, url in _regras(web, {"GET"}):
        if anonimo.get(url).status_code not in (302, 401, 403, 404, 405):
            publicas.add(regra.endpoint)
    esperadas = {"saude.saude", "jogo.inicio", "auth.entrar", "auth.setup"}
    assert publicas - esperadas == set(), publicas


# ---- cabeçalhos --------------------------------------------------------------------------------
def _cabecalhos_comuns(h):
    assert "script-src 'self'" in h["Content-Security-Policy"] and "frame-ancestors 'none'" in h["Content-Security-Policy"]
    assert "unsafe-inline" not in h["Content-Security-Policy"].split("script-src")[1].split(";")[0]
    assert h["X-Content-Type-Options"] == "nosniff" and h["X-Frame-Options"] == "DENY"
    assert h["Referrer-Policy"] == "same-origin" and "camera=()" in h["Permissions-Policy"]
    assert h["Cross-Origin-Opener-Policy"] == "same-origin"


def test_cabecalhos_em_paginas_json_e_erros(web):
    cria_mundo(web)
    cli = logado(web, "raiz")
    for url in ("/admin/", "/admin/dashboard", "/admin/api/dashboard/questionarios", "/saude", "/", "/entrar", "/nao-existe",
                "/static/css/painel.css"):
        _cabecalhos_comuns(cli.get(url).headers)
    r = web.test_client().post("/api/coleta/iniciar", json={"codigo": "AAAAA"})
    _cabecalhos_comuns(r.headers)


def test_paginas_do_painel_nao_ficam_em_cache_mas_os_estaticos_sim(web):
    cria_mundo(web)
    cli = logado(web, "raiz")
    assert cli.get("/admin/").headers["Cache-Control"] == "no-store"
    assert cli.get("/nao-existe").headers["Cache-Control"] == "no-store"
    assert cli.get("/static/css/painel.css").headers.get("Cache-Control") != "no-store"


def test_hsts_so_em_producao(web):
    assert "Strict-Transport-Security" not in web.test_client().get("/saude").headers
    env = {"APP_ENV": "production", "SECRET_KEY": "x" * 40, "GABARITO_SAL": "y" * 20,
           "DATABASE_URL": "postgresql://u:s@localhost/db"}
    reset_settings()
    prod = create_app(Settings.from_env(env))
    h = prod.test_client().get("/nao-existe").headers
    assert h["Strict-Transport-Security"].startswith("max-age=") and prod.config["SESSION_COOKIE_SECURE"]


def test_os_templates_nao_tem_javascript_inline():
    """A CSP bloqueia script inline; handlers como onclick quebrariam em silêncio no navegador."""
    from pathlib import Path
    raiz = Path(__file__).resolve().parent.parent / "app"
    achados = []
    for arq in list((raiz / "templates").rglob("*.html")) + [raiz / "static/game/index.html", raiz / "static/game/teste.html"]:
        html = arq.read_text(encoding="utf-8")
        for m in re.finditer(r"<script(?![^>]*\bsrc=)[^>]*>|\son[a-z]+\s*=|javascript:", html, flags=re.I):
            achados.append((arq.name, m.group(0)[:30]))
    assert not achados, achados


# ---- erros e logs ------------------------------------------------------------------------------
def test_erro_interno_nao_vaza_detalhes(web, caplog):
    web.testing = False                      # em teste o Flask repassaria a exceção em vez de responder
    web.config["PROPAGATE_EXCEPTIONS"] = False

    @web.get("/_boom")
    def _boom():
        raise RuntimeError("segredo-interno-do-servidor /opt/techquiz/senha")
    with caplog.at_level(logging.ERROR):
        r = web.test_client().get("/_boom")
    corpo = texto(r)
    assert r.status_code == 500 and "segredo-interno" not in corpo and "Traceback" not in corpo and "/opt/" not in corpo
    assert "segredo-interno" in caplog.text           # o detalhe vai só para o log


def test_erro_na_api_e_json_generico(web):
    web.testing = False
    web.config["PROPAGATE_EXCEPTIONS"] = False

    @web.get("/api/_boom")
    def _boom_api():
        raise RuntimeError("detalhe-interno")
    r = web.test_client().get("/api/_boom")
    assert r.status_code == 500 and r.get_json()["erro"]["motivo"] == "erro_interno" and "detalhe-interno" not in texto(r)


def test_senha_nunca_vai_para_o_log(web, caplog):
    cria_mundo(web)
    with caplog.at_level(logging.DEBUG):
        web.test_client().post("/entrar", data={"login": "raiz", "senha": "senha-errada-xyz"})
        web.test_client().post("/entrar", data={"login": "raiz", "senha": SENHA})
    assert "senha-errada-xyz" not in caplog.text and SENHA not in caplog.text


def test_login_nao_revela_se_o_usuario_existe(web):
    cria_mundo(web)
    a = texto(web.test_client().post("/entrar", data={"login": "raiz", "senha": "errada-123"}))
    b = texto(web.test_client().post("/entrar", data={"login": "ninguem", "senha": "errada-123"}))
    msg = lambda h: re.search(r'role="alert"[^>]*>.*?</div>', h, flags=re.S).group(0)   # noqa: E731
    assert re.sub(r"\s+", " ", msg(a)) == re.sub(r"\s+", " ", msg(b))


def test_redirecionamento_apos_login_so_para_o_proprio_site(web):
    cria_mundo(web)
    for destino in ("https://evil.example/", "//evil.example/", "/\\evil.example", "javascript:alert(1)"):
        r = web.test_client().post(f"/entrar?next={destino}", data={"login": "raiz", "senha": SENHA})
        assert r.status_code == 302 and "evil" not in r.headers["Location"] and "javascript" not in r.headers["Location"], destino


def test_cookie_de_sessao_tem_os_atributos_de_seguranca():
    env = {"APP_ENV": "production", "SECRET_KEY": "x" * 40, "GABARITO_SAL": "y" * 20, "DATABASE_URL": "postgresql://u:s@localhost/db"}
    reset_settings()
    prod = create_app(Settings.from_env(env))
    assert prod.config["SESSION_COOKIE_SECURE"] and prod.config["SESSION_COOKIE_HTTPONLY"] and prod.config["SESSION_COOKIE_SAMESITE"] == "Lax"
    assert prod.config["REMEMBER_COOKIE_SECURE"] and prod.config["REMEMBER_COOKIE_HTTPONLY"]


def test_saude_nao_expoe_segredos(web):
    corpo = texto(web.test_client().get("/saude"))
    assert "SECRET" not in corpo and "postgresql" not in corpo and "sqlite" not in corpo and "sal" not in corpo.lower().split()
