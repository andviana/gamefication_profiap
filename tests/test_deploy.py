"""Os modelos de deploy/ não podem se afastar do código: variáveis de ambiente, backup e unidades do systemd."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from app.config import Settings

RAIZ = Path(__file__).resolve().parent.parent
DEPLOY = RAIZ / "deploy"
SCRIPTS = ["techquiz-backup.sh", "techquiz-restore-check.sh", "smoke-test.sh"]


def _ler(nome):
    return (DEPLOY / nome).read_text(encoding="utf-8")


def test_o_env_de_exemplo_cobre_todas_as_variaveis_que_o_app_le():
    lidas = set(re.findall(r'(?:texto|inteiro)\("([A-Z_]+)"', (RAIZ / "app/config.py").read_text(encoding="utf-8")))
    lidas |= {"DATABASE_URL", "SECRET_KEY", "GABARITO_SAL", "APP_ENV"}
    exemplo = _ler("techquiz.env.example")
    faltam = {v for v in lidas if not re.search(rf"^#?\s*{v}=", exemplo, flags=re.M)}
    assert not faltam, f"variáveis lidas pelo app e ausentes de deploy/techquiz.env.example: {sorted(faltam)}"


def test_o_env_de_exemplo_vira_uma_configuracao_de_producao_valida_depois_de_preenchido():
    env = {}
    for linha in _ler("techquiz.env.example").splitlines():
        if linha and not linha.startswith("#") and "=" in linha:
            k, v = linha.split("=", 1)
            env[k] = v
    env.update(SECRET_KEY="s" * 48, GABARITO_SAL="g" * 24)
    s = Settings.from_env(env)
    assert s.eh_producao and s.cookie_seguro and s.proxies_confiaveis == 1 and s.database_url.startswith("postgresql+psycopg://")


def test_o_env_de_exemplo_nao_traz_segredos_prontos():
    exemplo = _ler("techquiz.env.example")
    assert re.search(r"^SECRET_KEY=$", exemplo, flags=re.M) and re.search(r"^GABARITO_SAL=$", exemplo, flags=re.M)


@pytest.mark.parametrize("nome", SCRIPTS)
def test_os_scripts_nao_executam_o_arquivo_de_ambiente(nome):
    """Um `source` do .env executaria texto do arquivo e quebraria com valores com espaço (INSTITUICAO_NOME)."""
    codigo = re.sub(r"^\s*#.*$", "", _ler(nome), flags=re.M)
    assert not re.search(r'^\s*(\.|source)\s+"?\$', codigo, flags=re.M)
    assert "set -" in codigo


@pytest.mark.skipif(shutil.which("sh") is None, reason="sh ausente")
@pytest.mark.parametrize("nome", SCRIPTS)
def test_os_scripts_tem_sintaxe_sh_valida_e_sao_executaveis(nome):
    assert (DEPLOY / nome).stat().st_mode & 0o111, f"{nome} sem permissão de execução"
    assert subprocess.run(["sh", "-n", str(DEPLOY / nome)], capture_output=True).returncode == 0
    assert _ler(nome).startswith("#!/bin/sh")


def test_o_backup_e_semanal_com_retencao_de_8_semanas():
    timer, script = _ler("techquiz-backup.timer"), _ler("techquiz-backup.sh")
    assert "OnCalendar=Sun" in timer and "Persistent=true" in timer
    assert "BACKUP_RETENCAO_DIAS:-56}" in script                       # 8 × 7 dias
    assert "pg_restore --list" in script                               # confere o arquivo antes de aceitá-lo
    assert script.index('mv "$parcial"') < script.index("-mtime")      # só apaga os antigos depois do novo pronto


def test_a_unidade_do_servico_aponta_para_arquivos_que_existem():
    unit = _ler("techquiz.service")
    assert "deploy/gunicorn.conf.py" in unit and (DEPLOY / "gunicorn.conf.py").exists()
    assert "wsgi:app" in unit and (RAIZ / "wsgi.py").exists()
    assert "EnvironmentFile=/etc/techquiz/techquiz.env" in unit and "NoNewPrivileges=true" in unit
    servico_backup = _ler("techquiz-backup.service")
    assert "deploy/techquiz-backup.sh" in servico_backup and "EnvironmentFile=/etc/techquiz/techquiz.env" in servico_backup


def test_o_gunicorn_so_ouve_em_localhost_por_padrao():
    assert '"GUNICORN_BIND", "127.0.0.1:8000"' in _ler("gunicorn.conf.py")


def test_o_nginx_redireciona_http_esconde_versao_e_sobrescreve_o_ip():
    conf, proxy = _ler("nginx-techquiz.conf"), _ler("nginx-techquiz-proxy.inc")
    assert "return 301 https://" in conf and "server_tokens off" in conf and "TLSv1.2 TLSv1.3" in conf and "limit_req_zone" in conf
    # sobrescreve o cabeçalho: um cliente não pode forjar o IP para escapar do rate limit
    assert "proxy_set_header X-Forwarded-For $remote_addr;" in proxy and "$proxy_add_x_forwarded_for" not in proxy
    assert "X-Forwarded-Proto $scheme" in proxy
