import os
import re

import pytest
from sqlalchemy import text

from app import create_app
from app.config import Settings, reset_settings
from app.extensions import db

# ENV mínimo válido para produção (nos testes, nunca usa o ENV real da máquina)
ENV_PRODUCAO = {
    "APP_ENV": "production",
    "SECRET_KEY": "x" * 40,
    "GABARITO_SAL": "sal-de-teste-0123456789",
    "DATABASE_URL": "postgresql://u:s@localhost:5432/techquiz",
}

# Se definida, a suíte roda também contra este PostgreSQL (descartável: as tabelas são apagadas a cada teste).
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "").strip()
usa_postgres = bool(TEST_DATABASE_URL)


def zera_postgres(app):
    """Apaga tudo no schema public, inclusive a tabela alembic_version."""
    with app.app_context():
        db.session.remove()
        db.engine.dispose()
        with db.engine.begin() as conexao:
            conexao.execute(text("DROP SCHEMA public CASCADE"))
            conexao.execute(text("CREATE SCHEMA public"))


@pytest.fixture(autouse=True)
def _hash_barato(monkeypatch):
    """O hash padrão (scrypt) é lento de propósito; nos testes usamos um barato para a suíte ser rápida."""
    from werkzeug.security import generate_password_hash
    from app.services import senha
    monkeypatch.setattr(senha, "gerar_hash", lambda s: generate_password_hash(s, method="pbkdf2:sha256:1000"))
    senha._hash_falso.cache_clear()


@pytest.fixture(autouse=True)
def _limpa_singleton():
    reset_settings()
    yield
    reset_settings()


@pytest.fixture
def settings():
    env = {"APP_ENV": "testing"}
    if usa_postgres:
        env["DATABASE_URL"] = TEST_DATABASE_URL
    return Settings.from_env(env)


@pytest.fixture
def app(settings):
    app = create_app(settings)
    if usa_postgres:
        zera_postgres(app)
    yield app
    if usa_postgres:
        zera_postgres(app)


@pytest.fixture
def client(app):
    return app.test_client()


# ---- auxiliares do fluxo web (compartilhados pelos testes de telas) -----------------------------
SENHA = "senha-boa-123"


@pytest.fixture
def web(app):
    """App com o schema criado (create_all) e limpo no fim."""
    from app.models import Usuario  # noqa: F401  (garante as tabelas no metadata)
    with app.app_context():
        db.create_all()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


def cria_mundo(app):
    """Raiz, dois promovidos e dois comuns; devolve os ids por login (raiz, comum1, comum2, promo1, promo2)."""
    with app.app_context():
        svc = app.extensions["container"].usuarios
        raiz = svc.criar_raiz("Raiz da Silva", "raiz", SENHA)
        ids = {"raiz": raiz.id}
        for chave, nome, promover in [("comum1", "Comum Um", False), ("comum2", "Comum Dois", False),
                                      ("promo1", "Promo Um", True), ("promo2", "Promo Dois", True)]:
            u = svc.criar(raiz, nome, chave, SENHA)
            if promover:
                svc.promover(raiz, u.id)
            ids[chave] = u.id
        return ids


def entra(client, login, senha=SENHA, **kw):
    return client.post("/entrar", data={"login": login, "senha": senha}, **kw)


def logado(app, login):
    cliente = app.test_client()
    assert entra(cliente, login).status_code == 302
    return cliente


def texto(resposta):
    return resposta.get_data(as_text=True)


def perfil_de(app, usuario_id):
    from app.models import Usuario
    with app.app_context():
        u = db.session.get(Usuario, usuario_id)
        return None if u is None else u.perfil


def token_csrf(html):
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)


def coleta_para(q, codigo="ABCDE"):
    """Cria uma coleta (com campus e curso) para o questionário; exige app context."""
    from datetime import date
    from app.models import Campus, Coleta, Curso
    campus = db.session.query(Campus).first() or Campus(nome="Belém")
    curso = db.session.query(Curso).first() or Curso(nome="Pedagogia")
    c = Coleta(codigo=codigo, questionario=q, campus=campus, curso=curso, ano=2026, periodo=1,
               data_inicio=date(2026, 3, 1), data_fim=date(2026, 3, 31))
    db.session.add(c)
    db.session.commit()
    return c


def responde(coleta, escolhas):
    """Uma partida: escolhas = [(pergunta, alternativa), ...]; `acertou` vem do gabarito atual."""
    from app.models import Partida, Resposta
    partida = Partida(coleta=coleta, total_acertos=sum(1 for _, a in escolhas if a.correta), total_perguntas=len(escolhas))
    db.session.add(partida)
    for ordem, (p, a) in enumerate(escolhas, 1):
        db.session.add(Resposta(partida=partida, pergunta=p, alternativa=a, acertou=a.correta, ordem=ordem, tempo_ms=1000,
                                pergunta_numero=p.numero, pergunta_titulo=p.titulo, grupo_nome=p.grupo.nome,
                                alternativa_letra=a.letra))
    db.session.commit()
    return partida
