from app import create_app
from app.config import Settings
from app.extensions import db
from app.models import Campus, Curso

from conftest import ENV_PRODUCAO


def test_seed_dev_e_idempotente(app):
    runner = app.test_cli_runner()
    with app.app_context():
        db.create_all()
    assert "Campi criados: 4. Cursos criados: 4." in runner.invoke(args=["seed-dev"]).output
    assert "Campi criados: 0. Cursos criados: 0." in runner.invoke(args=["seed-dev"]).output
    with app.app_context():
        assert Campus.query.count() == 4 and Curso.query.count() == 4
        assert {c.nome for c in Campus.query} == {"Belém", "Paragominas", "Tomé-Açu", "Parauapebas"}


def test_seed_dev_recusa_producao():
    app = create_app(Settings.from_env(ENV_PRODUCAO))
    r = app.test_cli_runner().invoke(args=["seed-dev"])
    assert r.exit_code != 0 and "produção" in r.output


# ---- flask redefinir-superadmin ---------------------------------------------------------------
import pytest  # noqa: E402

from app.models import Usuario  # noqa: E402


@pytest.fixture
def banco(app):
    with app.app_context():
        db.create_all()
    yield app


def _entra(client, login, senha):
    return client.post("/entrar", data={"login": login, "senha": senha}).status_code


def test_redefinir_superadmin_troca_a_senha_e_derruba_as_sessoes(banco):
    with banco.app_context():
        banco.extensions["container"].usuarios.criar_raiz("Ana Souza", "ana", "senha-antiga-1")
    sessao_aberta = banco.test_client()
    assert _entra(sessao_aberta, "ana", "senha-antiga-1") == 302 and sessao_aberta.get("/admin/").status_code == 200
    r = banco.test_cli_runner().invoke(args=["redefinir-superadmin"], input="senha-nova-999\nsenha-nova-999\n")
    assert r.exit_code == 0 and "ana" in r.output and "senha-nova" not in r.output
    assert sessao_aberta.get("/admin/").status_code == 302          # sessão antiga caiu
    assert _entra(banco.test_client(), "ana", "senha-antiga-1") == 401
    assert _entra(banco.test_client(), "ana", "senha-nova-999") == 302


def test_redefinir_superadmin_destrava_o_login(banco):
    with banco.app_context():
        banco.extensions["container"].usuarios.criar_raiz("Ana Souza", "ana", "senha-antiga-1")
    for _ in range(5):
        _entra(banco.test_client(), "ana", "errada")
    assert _entra(banco.test_client(), "ana", "senha-antiga-1") == 429
    banco.test_cli_runner().invoke(args=["redefinir-superadmin"], input="senha-nova-999\nsenha-nova-999\n")
    assert _entra(banco.test_client(), "ana", "senha-nova-999") == 302


def test_redefinir_superadmin_recusa_senha_curta(banco):
    with banco.app_context():
        banco.extensions["container"].usuarios.criar_raiz("Ana Souza", "ana", "senha-antiga-1")
    r = banco.test_cli_runner().invoke(args=["redefinir-superadmin"], input="curta\ncurta\n")
    assert r.exit_code != 0 and "pelo menos 8 caracteres" in r.output
    assert _entra(banco.test_client(), "ana", "senha-antiga-1") == 302      # nada mudou


def test_redefinir_superadmin_pede_a_confirmacao_de_novo_ate_conferir(banco):
    with banco.app_context():
        banco.extensions["container"].usuarios.criar_raiz("Ana Souza", "ana", "senha-antiga-1")
    entrada = "senha-nova-999\noutra-coisa-1\nsenha-final-777\nsenha-final-777\n"   # 1ª tentativa não confere
    r = banco.test_cli_runner().invoke(args=["redefinir-superadmin"], input=entrada)
    assert r.exit_code == 0 and "The two entered values do not match" in r.output
    assert _entra(banco.test_client(), "ana", "senha-nova-999") == 401      # a que não conferiu não vale
    assert _entra(banco.test_client(), "ana", "senha-final-777") == 302


def test_redefinir_superadmin_sem_raiz_orienta_o_setup(banco):
    r = banco.test_cli_runner().invoke(args=["redefinir-superadmin"], input="senha-nova-999\nsenha-nova-999\n")
    assert r.exit_code != 0 and "/setup" in r.output


def test_redefinir_superadmin_so_altera_a_raiz(banco):
    with banco.app_context():
        svc = banco.extensions["container"].usuarios
        raiz = svc.criar_raiz("Ana Souza", "ana", "senha-antiga-1")
        svc.promover(raiz, svc.criar(raiz, "Bia Lima", "bia", "senha-da-bia-1").id)
    banco.test_cli_runner().invoke(args=["redefinir-superadmin"], input="senha-nova-999\nsenha-nova-999\n")
    assert _entra(banco.test_client(), "bia", "senha-da-bia-1") == 302     # promovida intacta
