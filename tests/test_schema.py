import pytest
from sqlalchemy import text

from app import create_app, db_schema
from app.config import Settings
from app.db_schema import SchemaDesatualizado
from app.extensions import db

REVISAO = "abc123def456"


@pytest.fixture
def migracoes(tmp_path):
    """Diretório de migrações mínimo, com uma única revisão."""
    (tmp_path / "versions").mkdir()
    (tmp_path / "env.py").write_text("")
    (tmp_path / "versions" / f"{REVISAO}_inicial.py").write_text(
        f"revision = '{REVISAO}'\ndown_revision = None\nbranch_labels = None\ndepends_on = None\n\n"
        "def upgrade():\n    pass\n\ndef downgrade():\n    pass\n"
    )
    return tmp_path


def _grava_revisao(versao):
    db.session.execute(text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)"))
    db.session.execute(text("DELETE FROM alembic_version"))
    if versao:
        db.session.execute(text("INSERT INTO alembic_version VALUES (:v)"), {"v": versao})
    db.session.commit()


def test_sem_migracoes_quando_a_pasta_nao_existe(app, tmp_path):
    with app.app_context():
        assert db_schema.status_schema(tmp_path / "inexistente") == db_schema.SEM_MIGRACOES
        assert db_schema.verificar_schema_atualizado(tmp_path / "inexistente") == db_schema.SEM_MIGRACOES


def test_sem_migracoes_quando_nao_ha_revisoes(app, tmp_path):
    (tmp_path / "versions").mkdir()
    (tmp_path / "env.py").write_text("")
    with app.app_context():
        assert db_schema.status_schema(tmp_path) == db_schema.SEM_MIGRACOES


def test_banco_nunca_migrado_esta_ausente(app, migracoes):
    with app.app_context():
        assert db_schema.status_schema(migracoes) == db_schema.AUSENTE
        with pytest.raises(SchemaDesatualizado, match="não foi criado.*flask --app app:create_app db upgrade"):
            db_schema.verificar_schema_atualizado(migracoes)


def test_banco_em_revisao_antiga_esta_desatualizado(app, migracoes):
    with app.app_context():
        _grava_revisao("revisao_antiga")
        assert db_schema.status_schema(migracoes) == db_schema.DESATUALIZADO
        with pytest.raises(SchemaDesatualizado, match="desatualizado"):
            db_schema.verificar_schema_atualizado(migracoes)


def test_banco_na_revisao_atual_esta_ok(app, migracoes):
    with app.app_context():
        _grava_revisao(REVISAO)
        assert db_schema.status_schema(migracoes) == db_schema.OK
        assert db_schema.verificar_schema_atualizado(migracoes) == db_schema.OK


def test_saude_fica_degradada_quando_o_schema_esta_ausente(app, migracoes, monkeypatch):
    monkeypatch.setattr("app.config.MIGRATIONS_DIR", migracoes)
    r = app.test_client().get("/saude")
    assert r.status_code == 503
    assert r.get_json()["status"] == "degradado" and r.get_json()["schema"] == "ausente"


def test_wsgi_falha_cedo_com_schema_ausente(migracoes, monkeypatch):
    monkeypatch.setattr("app.config.MIGRATIONS_DIR", migracoes)
    with pytest.raises(SchemaDesatualizado):
        create_app(Settings.from_env({"APP_ENV": "testing"}), verificar_schema=True)


def test_create_app_sem_verificacao_nao_falha(migracoes, monkeypatch):
    monkeypatch.setattr("app.config.MIGRATIONS_DIR", migracoes)
    assert create_app(Settings.from_env({"APP_ENV": "testing"})) is not None
