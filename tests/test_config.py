import dataclasses

import pytest

from app import config
from app.config import ConfiguracaoInvalida, Settings, get_settings, reset_settings

from conftest import ENV_PRODUCAO


def test_padroes_aprovados_no_plano():
    s = Settings.from_env({})
    assert s.app_env == "development"
    assert s.timezone == "America/Belem" and s.locale == "pt-BR"
    assert (s.rate_limit_falhas, s.rate_limit_janela_seg, s.rate_limit_bloqueio_seg) == (10, 60, 300)
    assert (s.login_max_falhas, s.login_bloqueio_seg) == (5, 600)
    assert s.session_horas == 8
    assert s.previa_validade_min == 15
    assert s.upload_max_bytes == 2 * 1024 * 1024
    assert s.proxies_confiaveis == 0


def test_desenvolvimento_usa_sqlite_em_instance():
    s = Settings.from_env({})
    assert s.usa_sqlite and s.database_url.endswith("instance/dev.db")


def test_teste_usa_sqlite_em_memoria():
    assert Settings.from_env({"APP_ENV": "testing"}).database_url == "sqlite:///:memory:"


def test_producao_valida_exige_postgres_e_segredos():
    s = Settings.from_env(ENV_PRODUCAO)
    assert s.eh_producao and s.cookie_seguro and not s.usa_sqlite
    assert s.database_url.startswith("postgresql+psycopg://")  # normalizado para o driver psycopg 3


def test_producao_sem_nada_lista_todos_os_problemas():
    with pytest.raises(ConfiguracaoInvalida) as e:
        Settings.from_env({"APP_ENV": "production"})
    texto = str(e.value)
    assert "DATABASE_URL" in texto and "SECRET_KEY" in texto and "GABARITO_SAL" in texto
    assert len(e.value.problemas) == 3


def test_producao_recusa_sqlite_e_segredos_fracos():
    env = {**ENV_PRODUCAO, "DATABASE_URL": "sqlite:///x.db", "SECRET_KEY": "curta", "GABARITO_SAL": config.SAL_PADRAO}
    with pytest.raises(ConfiguracaoInvalida) as e:
        Settings.from_env(env)
    assert len(e.value.problemas) == 3


def test_ambiente_invalido():
    with pytest.raises(ConfiguracaoInvalida, match="APP_ENV"):
        Settings.from_env({"APP_ENV": "homologacao"})


@pytest.mark.parametrize("env,trecho", [
    ({"RATE_LIMIT_FALHAS": "abc"}, "RATE_LIMIT_FALHAS"),
    ({"SESSION_HORAS": "0"}, "SESSION_HORAS"),
    ({"TIMEZONE": "Marte/Olimpo"}, "TIMEZONE"),
    ({"LOG_LEVEL": "FALAR"}, "LOG_LEVEL"),
    ({"PROXIES_CONFIAVEIS": "-1"}, "PROXIES_CONFIAVEIS"),
])
def test_valores_invalidos_sao_recusados(env, trecho):
    with pytest.raises(ConfiguracaoInvalida, match=trecho):
        Settings.from_env(env)


def test_sobrescreve_valores_pelo_env():
    s = Settings.from_env({"RATE_LIMIT_FALHAS": "3", "SESSION_HORAS": "2", "PROXIES_CONFIAVEIS": "1", "INSTITUICAO_NOME": " UFRA "})
    assert (s.rate_limit_falhas, s.session_horas, s.proxies_confiaveis, s.instituicao_nome) == (3, 2, 1, "UFRA")


def test_settings_e_imutavel():
    s = Settings.from_env({})
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.app_env = "production"


def test_singleton_carrega_uma_vez(monkeypatch):
    monkeypatch.setenv("APP_ENV", "testing")
    a = get_settings()
    monkeypatch.setenv("APP_ENV", "development")  # mudar o ENV depois não altera a instância
    assert get_settings() is a and a.app_env == "testing"
    reset_settings()
    assert get_settings().app_env == "development"
