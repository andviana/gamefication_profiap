"""Regras de usuários e de autenticação, direto nos serviços (sem HTTP)."""
import logging
from datetime import datetime, timedelta, timezone

import pytest

from app import permissoes
from app.errors import CredenciaisInvalidas, Conflito, Invalido, LimiteExcedido, NaoEncontrado, Proibido
from app.extensions import db
from app.models import TentativaFalha, Usuario

SENHA = "senha-boa-123"


@pytest.fixture
def ctx(app):
    with app.app_context():
        db.create_all()
        yield app.extensions["container"]
        db.session.remove()
        db.drop_all()


@pytest.fixture
def svc(ctx):
    return ctx.usuarios


@pytest.fixture
def mundo(svc):
    """Raiz, dois promovidos e dois comuns."""
    raiz = svc.criar_raiz("Raiz", "raiz", SENHA)
    comum1 = svc.criar(raiz, "Comum Um", "comum1", SENHA)
    comum2 = svc.criar(raiz, "Comum Dois", "comum2", SENHA)
    promo1 = svc.promover(raiz, svc.criar(raiz, "Promo Um", "promo1", SENHA).id)
    promo2 = svc.promover(raiz, svc.criar(raiz, "Promo Dois", "promo2", SENHA).id)
    return dict(raiz=raiz, comum1=comum1, comum2=comum2, promo1=promo1, promo2=promo2)


# ---- setup -------------------------------------------------------------------------------------
def test_criar_raiz_so_funciona_com_a_tabela_vazia(svc):
    raiz = svc.criar_raiz("Ana Souza", "Ana", SENHA, SENHA)
    assert raiz.raiz and raiz.eh_superadmin and raiz.login == "ana" and raiz.nome == "Ana Souza"
    assert raiz.senha_hash != SENHA and raiz.senha_hash.startswith(("scrypt:", "pbkdf2:"))
    with pytest.raises(NaoEncontrado):
        svc.criar_raiz("Outra", "outra", SENHA)


def test_criacao_valida_os_campos(svc):
    raiz = svc.criar_raiz("Raiz", "raiz", SENHA)
    casos = [("N", "ok_login", SENHA, "nome"), ("Nome", "ab", SENHA, "login"), ("Nome", "Com Espaço", SENHA, "login"),
             ("Nome", "ok_login", "curta", "senha")]
    for nome, login, senha, campo in casos:
        with pytest.raises(Invalido) as e:
            svc.criar(raiz, nome, login, senha)
        assert e.value.detalhes["campo"] == campo
    with pytest.raises(Invalido) as e:
        svc.criar(raiz, "Nome", "ok_login", SENHA, "outra-coisa")
    assert e.value.detalhes["campo"] == "confirmacao"


def test_login_duplicado_ignora_maiusculas(svc):
    raiz = svc.criar_raiz("Raiz", "raiz", SENHA)
    svc.criar(raiz, "Um", "maria", SENHA)
    with pytest.raises(Conflito):
        svc.criar(raiz, "Dois", "MARIA", SENHA)


def test_criar_cria_sempre_usuario_comum(mundo, svc):
    assert not svc.criar(mundo["raiz"], "Xis", "xis123", SENHA).eh_superadmin
    assert not svc.criar(mundo["promo1"], "Ipsilon", "ipsilon", SENHA).eh_superadmin


def test_comum_nao_cria_usuarios(mundo, svc):
    with pytest.raises(Proibido):
        svc.criar(mundo["comum1"], "Zeta", "zeta123", SENHA)


# ---- matriz de permissões (seção 13 do plano) --------------------------------------------------
# ator -> alvo -> pode editar / redefinir a senha / excluir?
GERENCIA = {
    "raiz":   {"raiz": False, "promo1": True,  "promo2": True,  "comum1": True,  "comum2": True},
    "promo1": {"raiz": False, "promo1": False, "promo2": False, "comum1": True,  "comum2": True},
    "comum1": {"raiz": False, "promo1": False, "promo2": False, "comum1": False, "comum2": False},
}


@pytest.mark.parametrize("ator", GERENCIA)
@pytest.mark.parametrize("alvo", ["raiz", "promo1", "promo2", "comum1", "comum2"])
def test_matriz_de_gerenciamento(mundo, ator, alvo):
    esperado = GERENCIA[ator][alvo]
    a, b = mundo[ator], mundo[alvo]
    assert permissoes.pode_gerenciar(a, b) is esperado
    # os serviços aplicam a mesma regra
    from flask import current_app
    svc = current_app.extensions["container"].usuarios
    for acao in (lambda: svc.editar(a, b.id, "Nome Novo", b.login),
                 lambda: svc.redefinir_senha(a, b.id, "outra-senha-9")):
        if esperado:
            acao()
        else:
            with pytest.raises(Proibido):
                acao()


@pytest.mark.parametrize("ator,alvo,esperado", [
    ("raiz", "promo1", True), ("raiz", "comum1", True), ("promo1", "comum1", True), ("promo1", "promo2", False),
    ("promo1", "raiz", False), ("comum1", "comum2", False), ("raiz", "raiz", False), ("promo1", "promo1", False),
])
def test_matriz_de_exclusao(mundo, svc, ator, alvo, esperado):
    a, b = mundo[ator], mundo[alvo]
    if esperado:
        svc.excluir(a, b.id)
        assert db.session.get(Usuario, b.id) is None
    else:
        with pytest.raises(Proibido):
            svc.excluir(a, b.id)
        assert db.session.get(Usuario, b.id) is not None


@pytest.mark.parametrize("ator,alvo,esperado", [
    ("raiz", "comum1", True), ("raiz", "promo1", False),   # já é super admin
    ("promo1", "comum1", False), ("comum1", "comum2", False), ("raiz", "raiz", False),
])
def test_matriz_de_promocao(mundo, svc, ator, alvo, esperado):
    if esperado:
        assert svc.promover(mundo[ator], mundo[alvo].id).eh_superadmin
    else:
        with pytest.raises(Proibido):
            svc.promover(mundo[ator], mundo[alvo].id)


@pytest.mark.parametrize("ator,alvo,esperado", [
    ("raiz", "promo1", True), ("raiz", "comum1", False), ("raiz", "raiz", False),
    ("promo1", "promo2", False), ("promo1", "promo1", False), ("comum1", "promo1", False),
])
def test_matriz_de_revogacao(mundo, svc, ator, alvo, esperado):
    if esperado:
        revogado = svc.revogar(mundo[ator], mundo[alvo].id)
        assert not revogado.eh_superadmin and revogado.login == mundo[alvo].login  # continua existindo
    else:
        with pytest.raises(Proibido):
            svc.revogar(mundo[ator], mundo[alvo].id)


def test_raiz_continua_intocavel_e_unica(mundo, svc):
    raiz = mundo["raiz"]
    for ator in mundo.values():
        assert not permissoes.pode_gerenciar(ator, raiz) and not permissoes.pode_revogar(ator, raiz)
    assert db.session.query(Usuario).filter_by(raiz=True).count() == 1


def test_alvo_inexistente(mundo, svc):
    with pytest.raises(NaoEncontrado):
        svc.excluir(mundo["raiz"], 99999)
    with pytest.raises(NaoEncontrado):
        svc.promover(mundo["raiz"], 99999)


def test_editar_alvo_com_login_de_outro_e_conflito(mundo, svc):
    with pytest.raises(Conflito):
        svc.editar(mundo["raiz"], mundo["comum1"].id, "Nome", "comum2")


# ---- sessões -----------------------------------------------------------------------------------
def test_redefinir_senha_derruba_as_sessoes_do_alvo(mundo, svc):
    alvo = mundo["comum1"]
    antes = alvo.get_id()
    svc.redefinir_senha(mundo["raiz"], alvo.id, "nova-senha-77")
    assert alvo.get_id() != antes


@pytest.mark.parametrize("acao", ["promover", "revogar"])
def test_mudar_perfil_derruba_as_sessoes(mundo, svc, acao):
    alvo = mundo["comum1"] if acao == "promover" else mundo["promo1"]
    antes = alvo.get_id()
    getattr(svc, acao)(mundo["raiz"], alvo.id)
    assert alvo.get_id() != antes


def test_alterar_propria_senha_exige_a_atual_e_derruba_as_outras_sessoes(mundo, svc):
    u = mundo["comum1"]
    antes = u.get_id()
    with pytest.raises(Invalido) as e:
        svc.alterar_propria_senha(u, "errada", "nova-senha-77")
    assert e.value.detalhes["campo"] == "atual"
    with pytest.raises(Invalido):
        svc.alterar_propria_senha(u, SENHA, "curta")
    svc.alterar_propria_senha(u, SENHA, "nova-senha-77", "nova-senha-77")
    assert u.get_id() != antes


def test_raiz_troca_a_propria_senha(mundo, svc):
    svc.alterar_propria_senha(mundo["raiz"], SENHA, "outra-senha-88")
    from app.services.senha import confere
    assert confere(mundo["raiz"].senha_hash, "outra-senha-88")


def test_redefinir_senha_da_raiz_pelo_cli(mundo, svc):
    antes = mundo["raiz"].get_id()
    svc.redefinir_senha_da_raiz("senha-recuperada-1")
    assert mundo["raiz"].get_id() != antes


def test_redefinir_raiz_sem_raiz(svc):
    with pytest.raises(NaoEncontrado, match="setup"):
        svc.redefinir_senha_da_raiz("qualquer-senha-1")


# ---- login e bloqueio --------------------------------------------------------------------------
class Relogio:
    def __init__(self):
        self.t = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.t

    def avanca(self, **kw):
        self.t += timedelta(**kw)


@pytest.fixture
def relogio(ctx):
    r = Relogio()
    ctx.auth.relogio = r
    return r


def test_login_correto(mundo, ctx):
    assert ctx.auth.autenticar(" RAIZ ", SENHA).id == mundo["raiz"].id


@pytest.mark.parametrize("login,senha", [("raiz", "errada"), ("fantasma", SENHA), ("", SENHA), ("raiz", "")])
def test_credenciais_invalidas_tem_sempre_a_mesma_mensagem(mundo, ctx, login, senha):
    with pytest.raises(CredenciaisInvalidas) as e:
        ctx.auth.autenticar(login, senha)
    assert e.value.mensagem == "Login ou senha incorretos."


def test_cinco_erros_seguidos_bloqueiam_por_dez_minutos(mundo, ctx, relogio):
    for _ in range(5):
        with pytest.raises(CredenciaisInvalidas):
            ctx.auth.autenticar("raiz", "errada")
        relogio.avanca(seconds=1)
    # mesmo com a senha certa, está bloqueado
    with pytest.raises(LimiteExcedido) as e:
        ctx.auth.autenticar("raiz", SENHA)
    assert 590 <= e.value.espera_seg <= 600
    relogio.avanca(minutes=9)
    with pytest.raises(LimiteExcedido):
        ctx.auth.autenticar("raiz", SENHA)
    relogio.avanca(minutes=2)
    assert ctx.auth.autenticar("raiz", SENHA).login == "raiz"


def test_quatro_erros_nao_bloqueiam(mundo, ctx, relogio):
    for _ in range(4):
        with pytest.raises(CredenciaisInvalidas):
            ctx.auth.autenticar("raiz", "errada")
    assert ctx.auth.autenticar("raiz", SENHA)


def test_login_correto_zera_o_contador(mundo, ctx, relogio):
    for _ in range(4):
        with pytest.raises(CredenciaisInvalidas):
            ctx.auth.autenticar("raiz", "errada")
    ctx.auth.autenticar("raiz", SENHA)
    for _ in range(4):   # recomeça do zero: mais 4 erros ainda não bloqueiam
        with pytest.raises(CredenciaisInvalidas):
            ctx.auth.autenticar("raiz", "errada")
    assert ctx.auth.autenticar("raiz", SENHA)


def test_tentativas_durante_o_bloqueio_nao_o_prolongam(mundo, ctx, relogio):
    for _ in range(5):
        with pytest.raises(CredenciaisInvalidas):
            ctx.auth.autenticar("raiz", "errada")
    n = db.session.query(TentativaFalha).count()
    for _ in range(3):
        with pytest.raises(LimiteExcedido):
            ctx.auth.autenticar("raiz", "errada")
    assert db.session.query(TentativaFalha).count() == n


def test_bloqueio_vale_para_login_inexistente_sem_revelar_nada(mundo, ctx, relogio):
    for _ in range(5):
        with pytest.raises(CredenciaisInvalidas):
            ctx.auth.autenticar("fantasma", "x")
    with pytest.raises(LimiteExcedido):
        ctx.auth.autenticar("fantasma", "x")


def test_bloqueio_e_por_usuario(mundo, ctx, relogio):
    for _ in range(5):
        with pytest.raises(CredenciaisInvalidas):
            ctx.auth.autenticar("comum1", "errada")
    assert ctx.auth.autenticar("comum2", SENHA)   # outro usuário não é afetado


def test_redefinir_senha_destrava_o_usuario(mundo, ctx, svc, relogio):
    for _ in range(5):
        with pytest.raises(CredenciaisInvalidas):
            ctx.auth.autenticar("comum1", "errada")
    svc.redefinir_senha(mundo["raiz"], mundo["comum1"].id, "senha-nova-55")
    assert ctx.auth.autenticar("comum1", "senha-nova-55")


def test_tentativas_antigas_sao_purgadas(mundo, ctx, relogio):
    with pytest.raises(CredenciaisInvalidas):
        ctx.auth.autenticar("raiz", "errada")
    relogio.avanca(days=2)
    with pytest.raises(CredenciaisInvalidas):
        ctx.auth.autenticar("raiz", "errada")
    assert db.session.query(TentativaFalha).count() == 1


# ---- auditoria ---------------------------------------------------------------------------------
def test_eventos_sensiveis_vao_para_a_auditoria(mundo, svc, caplog):
    caplog.set_level(logging.INFO, logger="techquiz.auditoria")
    svc.promover(mundo["raiz"], mundo["comum1"].id)
    svc.revogar(mundo["raiz"], mundo["comum1"].id)
    svc.redefinir_senha(mundo["raiz"], mundo["comum2"].id, "outra-senha-99")
    svc.excluir(mundo["raiz"], mundo["comum2"].id)
    texto = "\n".join(r.getMessage() for r in caplog.records)
    for evento in ("promovido_a_superadmin", "superadmin_revogado", "senha_redefinida", "usuario_excluido"):
        assert f"evento={evento}" in texto
    assert "ator=raiz#" in texto and "senha-" not in texto   # nunca registra senhas
