"""Deploy em Docker (VPS com Traefik): o compose, a imagem e os scripts não podem se afastar do código nem do guia."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
COMPOSE = (RAIZ / "docker-compose.prod.yml").read_text(encoding="utf-8")
DOCKERFILE = (RAIZ / "Dockerfile").read_text(encoding="utf-8")
ENV_EXEMPLO = (RAIZ / ".env.producao.example").read_text(encoding="utf-8")
GUIA = (RAIZ / "docs/DEPLOY_VPS_HOSTINGER.md").read_text(encoding="utf-8")
SCRIPTS = ["docker/entrypoint.sh", "docker/backup.sh", "docker/restaurar-teste.sh"]


def _sem_comentarios(texto):
    return re.sub(r"^\s*#.*$", "", texto, flags=re.M)


def test_o_env_de_exemplo_cobre_todas_as_variaveis_do_compose():
    usadas = set(re.findall(r"\$\{([A-Z_]+)[:}-]", _sem_comentarios(COMPOSE)))
    declaradas = set(re.findall(r"^#?\s*([A-Z_]+)=", ENV_EXEMPLO, flags=re.M))
    assert not usadas - declaradas, sorted(usadas - declaradas)


def test_o_guia_documenta_todas_as_variaveis_do_compose():
    usadas = set(re.findall(r"\$\{([A-Z_]+)[:}-]", _sem_comentarios(COMPOSE)))
    faltam = {v for v in usadas if f"`{v}`" not in GUIA and v not in GUIA}
    assert not faltam, sorted(faltam)


def test_o_compose_exige_os_segredos_e_a_rede_do_traefik():
    for var in ("SECRET_KEY", "GABARITO_SAL", "POSTGRES_PASSWORD", "TRAEFIK_NETWORK", "APP_DOMAIN"):
        assert f"${{{var}:?" in COMPOSE, f"{var} deveria ser obrigatória"


def test_o_compose_nao_publica_portas_e_isola_o_banco():
    sem_comentarios = _sem_comentarios(COMPOSE)
    assert not re.search(r"^\s*ports:", sem_comentarios, flags=re.M), "nenhuma porta pode ser publicada na VPS"
    db = sem_comentarios.split("\n  db:\n    image")[1].split("\nnetworks:")[0]
    assert "- interna" in db and "- traefik" not in db                       # o banco só fala na rede interna


def test_o_compose_configura_o_app_para_producao_atras_do_traefik():
    assert 'APP_ENV: production' in COMPOSE and 'PROXIES_CONFIAVEIS: "1"' in COMPOSE
    assert "DATABASE_URL: postgresql://" in COMPOSE and "GUNICORN_BIND: 0.0.0.0:8000" in COMPOSE
    for rotulo in ("traefik.enable", "traefik.docker.network", "routers.techquiz.rule", "routers.techquiz.tls.certresolver",
                   "loadbalancer.server.port: \"8000\""):
        assert rotulo in COMPOSE, rotulo
    assert "volumes:\n  pg-dados:" in COMPOSE and "condition: service_healthy" in COMPOSE


def test_o_env_de_exemplo_nao_traz_segredos_prontos():
    assert "gere-" in ENV_EXEMPLO and "POSTGRES_PASSWORD=gere" in ENV_EXEMPLO
    assert not re.search(r"^[A-Z_]*(SECRET|KEY|SENHA|PASSWORD)[A-Z_]*=[A-Za-z0-9+/]{24,}$", ENV_EXEMPLO, flags=re.M)


def test_a_imagem_roda_sem_privilegios_e_tem_saude_e_entrypoint():
    assert re.search(r"^USER app$", DOCKERFILE, flags=re.M) and "--uid 10001" in DOCKERFILE
    assert "HEALTHCHECK" in DOCKERFILE and "docker/saude.py" in DOCKERFILE
    assert 'ENTRYPOINT ["/app/docker/entrypoint.sh"]' in DOCKERFILE and "wsgi:app" in DOCKERFILE
    assert "FROM python:" in DOCKERFILE


def test_o_dockerignore_deixa_segredos_e_testes_fora_da_imagem():
    ignorados = (RAIZ / ".dockerignore").read_text(encoding="utf-8").split()
    for item in (".env", ".venv", "tests", "instance", ".git", "backups"):
        assert item in ignorados, item
    assert "deploy" not in ignorados and "docker" not in ignorados           # a imagem precisa de ambos
    assert (RAIZ / "deploy/gunicorn.conf.py").exists()


def test_o_entrypoint_espera_o_banco_antes_de_migrar_e_so_entao_inicia():
    codigo = _sem_comentarios((RAIZ / "docker/entrypoint.sh").read_text(encoding="utf-8"))
    assert codigo.index("aguardar_servicos.py") < codigo.index("flask db upgrade") < codigo.index('exec "$@"')
    assert "set -e" in codigo


@pytest.mark.skipif(shutil.which("sh") is None, reason="sh ausente")
@pytest.mark.parametrize("nome", SCRIPTS)
def test_os_scripts_tem_sintaxe_valida_e_sao_executaveis(nome):
    caminho = RAIZ / nome
    assert caminho.stat().st_mode & 0o111, f"{nome} sem permissão de execução"
    assert subprocess.run(["sh", "-n", str(caminho)], capture_output=True).returncode == 0
    assert caminho.read_text(encoding="utf-8").startswith("#!/bin/sh")


def test_o_backup_em_docker_e_semanal_com_retencao_de_8_semanas_e_confere_o_arquivo():
    script = (RAIZ / "docker/backup.sh").read_text(encoding="utf-8")
    assert "BACKUP_RETENCAO_DIAS:-56}" in script and "pg_restore --list" in script and "sha256sum" in script
    assert script.index('mv "$parcial"') < script.index("-mtime")           # só apaga os antigos depois do novo pronto
    assert "0 3 * * 0" in GUIA and "restaurar-teste.sh" in GUIA


def test_o_gunicorn_nao_depende_do_diretorio_do_usuario():
    assert "control_socket_disable = True" in (RAIZ / "deploy/gunicorn.conf.py").read_text(encoding="utf-8")


@pytest.mark.skipif(shutil.which("docker") is None, reason="docker ausente")
def test_o_compose_valida_com_o_proprio_docker():
    env = {"PATH": "/usr/bin:/bin:/usr/local/bin", "APP_DOMAIN": "x.exemplo.br", "TRAEFIK_NETWORK": "traefik", "SECRET_KEY": "s" * 40,
           "GABARITO_SAL": "g" * 20, "POSTGRES_PASSWORD": "p" * 12}
    r = subprocess.run(["docker", "compose", "--env-file", "/dev/null", "-f", str(RAIZ / "docker-compose.prod.yml"), "config", "-q"],
                       capture_output=True, text=True, env=env)
    if "docker: 'compose' is not a docker command" in r.stderr or "permission denied" in r.stderr.lower():
        pytest.skip("docker compose indisponível")
    assert r.returncode == 0, r.stderr
    sem = subprocess.run(["docker", "compose", "--env-file", "/dev/null", "-f", str(RAIZ / "docker-compose.prod.yml"), "config", "-q"],
                         capture_output=True, text=True, env={"PATH": env["PATH"]})
    assert sem.returncode != 0 and "required variable" in sem.stderr        # sem os segredos, o compose se recusa
