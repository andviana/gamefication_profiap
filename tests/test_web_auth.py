"""Fluxo web de autenticação e do CRUD de usuários, ponta a ponta pelo cliente HTTP."""
import re

import pytest

from app.extensions import db
from app.models import Usuario

from conftest import SENHA, cria_mundo, entra, logado, perfil_de, texto, web  # noqa: F401  (web é fixture)

# ---- setup ------------------------------------------------------------------------------------
def test_sem_usuarios_tudo_leva_ao_setup(web):
    c = web.test_client()
    assert c.get("/entrar").headers["Location"].endswith("/setup")
    r = c.get("/admin/", follow_redirects=True)
    assert r.request.path == "/setup" and "Primeiro acesso" in texto(r)


def test_setup_cria_a_raiz_e_ja_entra(web):
    c = web.test_client()
    r = c.post("/setup", data={"nome": "Ana Souza", "login": "Ana", "senha": SENHA, "confirmacao": SENHA})
    assert r.status_code == 302 and r.headers["Location"].endswith("/admin/")
    assert "Olá, Ana" in texto(c.get("/admin/"))
    with web.app_context():
        u = Usuario.query.one()
        assert u.raiz and u.eh_superadmin and u.login == "ana"


def test_setup_deixa_de_existir_depois_do_primeiro_usuario(web):
    c = web.test_client()
    c.post("/setup", data={"nome": "Ana Souza", "login": "ana", "senha": SENHA, "confirmacao": SENHA})
    outro = web.test_client()
    assert outro.get("/setup").status_code == 404
    r = outro.post("/setup", data={"nome": "Intruso", "login": "intruso", "senha": SENHA, "confirmacao": SENHA})
    assert r.status_code == 404
    with web.app_context():
        assert Usuario.query.count() == 1


def test_setup_mostra_erros_nos_campos(web):
    c = web.test_client()
    r = c.post("/setup", data={"nome": "Ana", "login": "a", "senha": "curta", "confirmacao": "outra"})
    assert r.status_code == 422 and "O login deve ter de 3 a 40 caracteres" in texto(r)
    r = c.post("/setup", data={"nome": "Ana", "login": "ana", "senha": "curta", "confirmacao": "curta"})
    assert "pelo menos 8 caracteres" in texto(r)
    r = c.post("/setup", data={"nome": "Ana", "login": "ana", "senha": SENHA, "confirmacao": "diferente-123"})
    assert "A confirmação não confere" in texto(r)
    r = c.post("/setup", data={"nome": "", "login": "", "senha": "", "confirmacao": ""})
    assert r.status_code == 422 and texto(r).count("Campo obrigatório.") == 4
    with web.app_context():
        assert Usuario.query.count() == 0


# ---- login ------------------------------------------------------------------------------------
def test_login_correto_e_logout(web):
    cria_mundo(web)
    c = web.test_client()
    r = entra(c, "RAIZ")
    assert r.status_code == 302 and r.headers["Location"].endswith("/admin/")
    assert c.get("/admin/").status_code == 200
    assert c.get("/entrar").status_code == 302          # já logado: não mostra o formulário
    assert c.post("/sair").status_code == 302
    assert c.get("/admin/").status_code == 302          # saiu


def test_login_errado_tem_mensagem_unica_e_status_401(web):
    cria_mundo(web)
    for login, senha in [("raiz", "errada"), ("fantasma", SENHA)]:
        r = entra(web.test_client(), login, senha)
        assert r.status_code == 401 and "Login ou senha incorretos." in texto(r)


def test_cinco_erros_bloqueiam_ate_com_a_senha_certa(web):
    cria_mundo(web)
    c = web.test_client()
    for _ in range(5):
        assert entra(c, "comum1", "errada").status_code == 401
    r = entra(c, "comum1", SENHA)
    assert r.status_code == 429 and "Muitas tentativas" in texto(r) and "10 min" in texto(r)
    assert entra(web.test_client(), "comum2").status_code == 302     # outro usuário segue normal


@pytest.mark.parametrize("destino,esperado", [
    ("/admin/usuarios", "/admin/usuarios"), ("https://evil.example/x", "/admin/"), ("//evil.example", "/admin/"),
    ("/\\evil.example", "/admin/"), ("javascript:alert(1)", "/admin/")])
def test_redirecionamento_pos_login_so_para_caminho_local(web, destino, esperado):
    cria_mundo(web)
    r = web.test_client().post("/entrar", query_string={"next": destino}, data={"login": "raiz", "senha": SENHA})
    assert r.status_code == 302 and r.headers["Location"].endswith(esperado)


def test_rota_protegida_sem_login_vai_para_o_login_com_next(web):
    cria_mundo(web)
    r = web.test_client().get("/admin/usuarios")
    assert r.status_code == 302 and "/entrar" in r.headers["Location"] and "next=" in r.headers["Location"]


def test_cookie_de_sessao_tem_as_protecoes(web):
    cria_mundo(web)
    cookie = entra(web.test_client(), "raiz").headers["Set-Cookie"]
    assert "HttpOnly" in cookie and "SameSite=Lax" in cookie and "Expires=" in cookie   # Expires = sessão permanente


def test_sessao_com_valor_invalido_vira_anonima(web):
    cria_mundo(web)
    c = web.test_client()
    with c.session_transaction() as s:
        s["_user_id"] = "lixo-sem-dois-pontos"
    assert c.get("/admin/").status_code == 302
    with c.session_transaction() as s:
        s["_user_id"] = "999999:abc"
    assert c.get("/admin/").status_code == 302


# ---- permissões nas rotas ---------------------------------------------------------------------
def test_usuario_comum_nao_acessa_a_gestao_de_usuarios(web):
    ids = cria_mundo(web)
    c = logado(web, "comum1")
    assert c.get("/admin/").status_code == 200
    for url in ["/admin/usuarios", "/admin/usuarios/novo", f"/admin/usuarios/{ids['comum2']}/editar",
                f"/admin/usuarios/{ids['comum2']}/senha"]:
        assert c.get(url).status_code == 403, url
    for acao in ["promover", "revogar", "excluir"]:
        assert c.post(f"/admin/usuarios/{ids['comum2']}/{acao}").status_code == 403
    assert "Usuários" not in texto(c.get("/admin/"))     # nem aparece no menu


def test_lista_mostra_so_as_acoes_permitidas(web):
    ids = cria_mundo(web)
    raiz = texto(logado(web, "raiz").get("/admin/usuarios"))
    assert "Promover a super admin" in raiz and "Revogar super admin" in raiz
    assert f"/admin/usuarios/{ids['raiz']}/editar" not in raiz and f"/admin/usuarios/{ids['raiz']}/excluir" not in raiz
    promo = texto(logado(web, "promo1").get("/admin/usuarios"))
    assert "Promover a super admin" not in promo and "Revogar super admin" not in promo
    assert f"/admin/usuarios/{ids['comum1']}/editar" in promo                   # comum: pode
    assert f"/admin/usuarios/{ids['promo2']}/editar" not in promo               # outro promovido: não
    assert f"/admin/usuarios/{ids['promo1']}/excluir" not in promo              # a si mesmo: não


def test_promovido_nao_mexe_em_super_admins_pelas_rotas(web):
    ids = cria_mundo(web)
    c = logado(web, "promo1")
    for alvo in ("raiz", "promo2", "promo1"):
        assert c.get(f"/admin/usuarios/{ids[alvo]}/editar").status_code == 403
        assert c.post(f"/admin/usuarios/{ids[alvo]}/excluir").status_code == 403
        assert c.post(f"/admin/usuarios/{ids[alvo]}/revogar").status_code == 403
    assert c.post(f"/admin/usuarios/{ids['comum1']}/promover").status_code == 403    # só a raiz promove
    assert perfil_de(web, ids["comum1"]) == "comum" and perfil_de(web, ids["raiz"]) == "superadmin"


def test_ninguem_remove_a_raiz_nem_a_si_mesmo(web):
    ids = cria_mundo(web)
    raiz = logado(web, "raiz")
    assert raiz.post(f"/admin/usuarios/{ids['raiz']}/excluir").status_code == 403
    assert raiz.post(f"/admin/usuarios/{ids['raiz']}/revogar").status_code == 403
    assert raiz.get(f"/admin/usuarios/{ids['raiz']}/senha").status_code == 403    # senha da raiz só em /conta/senha
    assert logado(web, "promo1").post(f"/admin/usuarios/{ids['promo1']}/excluir").status_code == 403
    assert perfil_de(web, ids["raiz"]) == "superadmin" and perfil_de(web, ids["promo1"]) == "superadmin"


def test_alvo_inexistente_da_404(web):
    cria_mundo(web)
    c = logado(web, "raiz")
    assert c.get("/admin/usuarios/99999/editar").status_code == 404
    assert c.post("/admin/usuarios/99999/excluir").status_code == 404


# ---- CRUD -------------------------------------------------------------------------------------
def test_raiz_cria_edita_redefine_promove_revoga_e_exclui(web):
    cria_mundo(web)
    c = logado(web, "raiz")
    r = c.post("/admin/usuarios/novo", data={"nome": "Zeca Lima", "login": "zeca", "senha": SENHA, "confirmacao": SENHA})
    assert r.status_code == 302
    with web.app_context():
        zeca = Usuario.query.filter_by(login="zeca").one()
        zid = zeca.id
        assert zeca.perfil == "comum"
    assert "Zeca Lima" in texto(c.get("/admin/usuarios"))
    assert c.post(f"/admin/usuarios/{zid}/editar", data={"nome": "Zeca Souza", "login": "zeca2"}).status_code == 302
    with web.app_context():
        assert db.session.get(Usuario, zid).login == "zeca2"
    assert c.post(f"/admin/usuarios/{zid}/senha", data={"nova": "outra-senha-1", "confirmacao": "outra-senha-1"}).status_code == 302
    assert entra(web.test_client(), "zeca2", "outra-senha-1").status_code == 302
    assert c.post(f"/admin/usuarios/{zid}/promover").status_code == 302 and perfil_de(web, zid) == "superadmin"
    assert c.post(f"/admin/usuarios/{zid}/revogar").status_code == 302 and perfil_de(web, zid) == "comum"
    assert c.post(f"/admin/usuarios/{zid}/excluir").status_code == 302 and perfil_de(web, zid) is None


def test_formulario_de_usuario_mostra_erros(web):
    cria_mundo(web)
    c = logado(web, "raiz")
    r = c.post("/admin/usuarios/novo", data={"nome": "X", "login": "comum1", "senha": SENHA, "confirmacao": SENHA})
    assert r.status_code == 422 and "O nome deve ter de 2 a 120" in texto(r)
    r = c.post("/admin/usuarios/novo", data={"nome": "Alguém", "login": "COMUM1", "senha": SENHA, "confirmacao": SENHA})
    assert r.status_code == 422 and "Já existe um usuário com este login" in texto(r)
    r = c.post("/admin/usuarios/novo", data={"nome": "Alguém", "login": "alguem", "senha": SENHA, "confirmacao": "x"})
    assert "A confirmação não confere" in texto(r)


def test_nomes_sao_escapados_no_html(web):
    cria_mundo(web)
    c = logado(web, "raiz")
    c.post("/admin/usuarios/novo", data={"nome": "<script>alert(1)</script>", "login": "xss", "senha": SENHA, "confirmacao": SENHA})
    html = texto(c.get("/admin/usuarios"))
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;alert(1)&lt;/script&gt;" in html


# ---- sessões ----------------------------------------------------------------------------------
@pytest.mark.parametrize("acao", ["senha", "promover", "editar-login"])
def test_alteracao_por_terceiros_derruba_a_sessao_do_afetado(web, acao):
    ids = cria_mundo(web)
    afetado = logado(web, "comum1")
    assert afetado.get("/admin/").status_code == 200
    raiz = logado(web, "raiz")
    alvo = ids["comum1"]
    if acao == "senha":
        raiz.post(f"/admin/usuarios/{alvo}/senha", data={"nova": "nova-senha-77", "confirmacao": "nova-senha-77"})
    elif acao == "promover":
        raiz.post(f"/admin/usuarios/{alvo}/promover")
    else:
        raiz.post(f"/admin/usuarios/{alvo}/editar", data={"nome": "Comum Um", "login": "comum1-novo"})
    assert afetado.get("/admin/").status_code == 302       # sessão antiga não vale mais
    assert raiz.get("/admin/").status_code == 200          # quem fez a alteração segue logado


def test_exclusao_derruba_a_sessao_do_excluido(web):
    ids = cria_mundo(web)
    afetado = logado(web, "comum1")
    logado(web, "raiz").post(f"/admin/usuarios/{ids['comum1']}/excluir")
    assert afetado.get("/admin/").status_code == 302


def test_alterar_propria_senha(web):
    cria_mundo(web)
    principal, outra_aba = logado(web, "comum1"), logado(web, "comum1")
    r = principal.post("/conta/senha", data={"atual": "errada", "nova": "nova-senha-77", "confirmacao": "nova-senha-77"})
    assert r.status_code == 422 and "A senha atual está incorreta" in texto(r)
    r = principal.post("/conta/senha", data={"atual": SENHA, "nova": "curta", "confirmacao": "curta"})
    assert "pelo menos 8 caracteres" in texto(r)
    r = principal.post("/conta/senha", data={"atual": SENHA, "nova": "nova-senha-77", "confirmacao": "nova-senha-77"})
    assert r.status_code == 302
    assert principal.get("/admin/").status_code == 200       # esta sessão continua
    assert outra_aba.get("/admin/").status_code == 302       # as outras caem
    assert entra(web.test_client(), "comum1", SENHA).status_code == 401
    assert entra(web.test_client(), "comum1", "nova-senha-77").status_code == 302


def test_raiz_troca_a_propria_senha_por_conta_senha(web):
    cria_mundo(web)
    raiz = logado(web, "raiz")
    assert raiz.post("/conta/senha", data={"atual": SENHA, "nova": "senha-da-raiz-9", "confirmacao": "senha-da-raiz-9"}).status_code == 302
    assert entra(web.test_client(), "raiz", "senha-da-raiz-9").status_code == 302


# ---- CSRF -------------------------------------------------------------------------------------
def _token(html):
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)


def test_csrf_protege_todos_os_formularios(web):
    cria_mundo(web)
    web.config["WTF_CSRF_ENABLED"] = True
    c = web.test_client()
    r = c.post("/entrar", data={"login": "raiz", "senha": SENHA})
    assert r.status_code == 400 and r.get_json() is None
    token = _token(texto(c.get("/entrar")))
    assert c.post("/entrar", data={"login": "raiz", "senha": SENHA, "csrf_token": token}).status_code == 302
    # logout e ações da lista também exigem token
    assert c.post("/sair").status_code == 400
    ids_html = texto(c.get("/admin/usuarios"))
    assert 'name="csrf_token"' in ids_html and ids_html.count('name="csrf_token"') >= 5
    assert c.post("/admin/usuarios/2/excluir").status_code == 400


def test_pagina_de_erro_de_csrf_e_html_amigavel(web):
    web.config["WTF_CSRF_ENABLED"] = True
    cria_mundo(web)
    r = web.test_client().post("/entrar", data={"login": "raiz", "senha": SENHA})
    assert r.status_code == 400 and "text/html" in r.content_type


def test_setup_nao_mostra_o_aviso_de_entrar(web):
    c = web.test_client()
    r = c.get("/admin/", follow_redirects=True)
    assert r.request.path == "/setup" and "Entre para continuar" not in texto(r)
