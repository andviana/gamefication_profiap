"""A migração inicial precisa produzir exatamente o schema dos modelos (e poder ser desfeita), em cada banco."""
import pytest
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from flask_migrate import downgrade, upgrade
from sqlalchemy import inspect

from app import create_app, db_schema
from app.config import Settings
from app.extensions import db

from conftest import TEST_DATABASE_URL, usa_postgres, zera_postgres

BANCOS = ["sqlite"] + (["postgres"] if usa_postgres else [])


def _url(banco, tmp_path):
    return f"sqlite:///{tmp_path / 'm.db'}" if banco == "sqlite" else TEST_DATABASE_URL


@pytest.fixture(params=BANCOS)
def app_arquivo(request, tmp_path):
    """App num banco que persiste entre conexões (SQLite em arquivo ou o PostgreSQL de teste)."""
    app = create_app(Settings.from_env({"APP_ENV": "testing", "DATABASE_URL": _url(request.param, tmp_path)}))
    if request.param == "postgres":
        zera_postgres(app)
    yield app
    if request.param == "postgres":
        zera_postgres(app)


def test_migracao_equivale_aos_modelos(app_arquivo):
    with app_arquivo.app_context():
        upgrade()
        with db.engine.connect() as conexao:
            contexto = MigrationContext.configure(conexao, opts={"compare_type": True})
            diferencas = compare_metadata(contexto, db.metadata)
        assert diferencas == [], f"a migração difere dos modelos: {diferencas}"


def test_upgrade_deixa_o_schema_na_revisao_atual(app_arquivo):
    with app_arquivo.app_context():
        assert db_schema.status_schema() == db_schema.AUSENTE
        upgrade()
        assert db_schema.status_schema() == db_schema.OK
        assert db_schema.verificar_schema_atualizado() == db_schema.OK


def test_downgrade_remove_todas_as_tabelas(app_arquivo):
    with app_arquivo.app_context():
        upgrade()
        assert "resposta" in inspect(db.engine).get_table_names()
        downgrade(revision="base")
        assert set(inspect(db.engine).get_table_names()) <= {"alembic_version"}


def test_wsgi_sobe_depois_do_upgrade(app_arquivo):
    with app_arquivo.app_context():
        upgrade()
    settings = Settings.from_env({"APP_ENV": "testing", "DATABASE_URL": app_arquivo.config["SQLALCHEMY_DATABASE_URI"]})
    assert create_app(settings, verificar_schema=True) is not None


def test_saude_reflete_o_schema_migrado(app_arquivo):
    cliente = app_arquivo.test_client()
    assert cliente.get("/saude").status_code == 503 and cliente.get("/saude").get_json()["schema"] == "ausente"
    with app_arquivo.app_context():
        upgrade()
    r = cliente.get("/saude")
    assert r.status_code == 200 and r.get_json()["schema"] == "ok"


def test_migracao_do_token_de_sessao_preenche_usuarios_existentes(app_arquivo):
    """Um banco que já tem usuários (revisão anterior) ganha um token próprio para cada um ao subir de versão."""
    from sqlalchemy import text
    with app_arquivo.app_context():
        upgrade(revision="b1ce84a00cae")
        for i in (1, 2):
            db.session.execute(text(
                "INSERT INTO usuario (nome, login, senha_hash, perfil, raiz, criado_em) "
                "VALUES (:n, :l, 'hash', 'comum', :r, '2026-01-01 00:00:00')"), {"n": f"U{i}", "l": f"u{i}", "r": False})
        db.session.commit()
        upgrade()
        tokens = [t for (t,) in db.session.execute(text("SELECT sessao_token FROM usuario ORDER BY id"))]
        assert len(tokens) == 2 and all(len(t) == 32 for t in tokens) and tokens[0] != tokens[1]
        coluna = {c["name"]: c for c in inspect(db.engine).get_columns("usuario")}["sessao_token"]
        assert coluna["nullable"] is False
