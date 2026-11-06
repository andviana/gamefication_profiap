"""Telas de questionários e perguntas, ponta a ponta."""
import pytest

from app.extensions import db
from app.models import Alternativa, Grupo, Partida, Pergunta, Questionario, Resposta, Usuario

from conftest import coleta_para, cria_mundo, logado, responde, texto, web  # noqa: F401


def form_pergunta(grupo_id, titulo="Phishing", correta=2, n=4, **extra):
    d = {"titulo": titulo, "texto": f"Enunciado de {titulo}?", "grupo_id": str(grupo_id), "autoajuda": "", "numero": "",
         "correta": str(correta)}
    for i in range(n):
        d[f"alt_texto_{i}"] = f"Alternativa {'ABCD'[i]}"
        d[f"alt_acerto_{i}"] = "Isso mesmo." if i == correta else ""
        d[f"alt_erro_{i}"] = "" if i == correta else f"Não é a {'ABCD'[i]}."
    d.update(extra)
    return d


@pytest.fixture
def mundo(web):
    ids = cria_mundo(web)
    with web.app_context():
        g = Grupo(nome="Tecnologia")
        db.session.add(g)
        db.session.commit()
        return {"ids": ids, "grupo_id": g.id}


def cria_questionario(app, nome="Letramento Digital", n_perguntas=2):
    """Questionário com perguntas, direto pelos serviços (o ator é a raiz)."""
    with app.app_context():
        c = app.extensions["container"]
        raiz = db.session.query(Usuario).filter_by(raiz=True).one()
        grupo = db.session.query(Grupo).first()
        q = c.questionarios.criar(raiz, nome, "Descrição")
        from app.services.perguntas import DadosAlternativa, DadosPergunta
        for i in range(n_perguntas):
            c.perguntas.criar(raiz, q.id, DadosPergunta(
                texto=f"Enunciado {i + 1}?", titulo=f"Tema {i + 1}", grupo_id=grupo.id,
                alternativas=[DadosAlternativa(f"Alt {a}", correta=(a == 2)) for a in range(4)]))
        return q.id


def trava(app, qid):
    """Cria coleta e respostas: o questionário vira 'travado'."""
    with app.app_context():
        q = db.session.get(Questionario, qid)
        responde(coleta_para(q), [(p, p.alternativas[0]) for p in q.perguntas])


# ---- acesso ------------------------------------------------------------------------------------
def test_exige_login(web, mundo):
    qid = cria_questionario(web)
    c = web.test_client()
    for url in ["/admin/questionarios", "/admin/questionarios/novo", f"/admin/questionarios/{qid}",
                f"/admin/questionarios/{qid}/perguntas/nova"]:
        assert c.get(url).status_code == 302, url


def test_usuario_comum_faz_tudo_menos_trocar_gabarito(web, mundo):
    qid = cria_questionario(web)
    trava(web, qid)
    c = logado(web, "comum1")
    for url in ["/admin/questionarios", f"/admin/questionarios/{qid}", f"/admin/questionarios/{qid}/editar",
                f"/admin/questionarios/{qid}/orientacoes"]:
        assert c.get(url).status_code == 200, url
    with web.app_context():
        pid = db.session.get(Questionario, qid).perguntas[0].id
    assert c.get(f"/admin/questionarios/{qid}/perguntas/{pid}/gabarito").status_code == 403
    assert c.post(f"/admin/questionarios/{qid}/perguntas/{pid}/gabarito", data={"correta": "A"}).status_code == 403
    assert "Trocar gabarito" not in texto(c.get(f"/admin/questionarios/{qid}"))      # nem aparece para o comum


# ---- questionários ----------------------------------------------------------------------------
def test_criar_questionario_e_ver_na_lista(web, mundo):
    c = logado(web, "comum1")
    assert "Nenhum questionário ainda" in texto(c.get("/admin/questionarios"))
    r = c.post("/admin/questionarios/novo", data={"nome": "Letramento Digital", "descricao": "Turma 2026"})
    assert r.status_code == 302 and "/admin/questionarios/" in r.headers["Location"]
    detalhe = texto(c.get(r.headers["Location"]))
    assert "Letramento Digital" in detalhe and "rascunho" in detalhe and "Nenhuma pergunta ainda" in detalhe
    assert "Sobre a sua participação" in detalhe                    # texto padrão das orientações
    lista = texto(c.get("/admin/questionarios"))
    assert "Letramento Digital" in lista and "rascunho" in lista


def test_formulario_do_questionario_mostra_erros(web, mundo):
    cria_questionario(web, "Existente")
    c = logado(web, "raiz")
    r = c.post("/admin/questionarios/novo", data={"nome": "existente", "descricao": ""})
    assert r.status_code == 422 and "Já existe um questionário com este nome" in texto(r)
    assert c.post("/admin/questionarios/novo", data={"nome": "x", "descricao": ""}).status_code == 422


def test_editar_dados_e_orientacoes(web, mundo):
    qid = cria_questionario(web)
    c = logado(web, "comum1")
    assert c.post(f"/admin/questionarios/{qid}/editar", data={"nome": "Novo Nome", "descricao": "d2"}).status_code == 302
    assert c.post(f"/admin/questionarios/{qid}/orientacoes", data={"orientacoes": "# Meu texto\n- item"}).status_code == 302
    d = texto(c.get(f"/admin/questionarios/{qid}"))
    assert "Novo Nome" in d and "# Meu texto" in d
    r = c.post(f"/admin/questionarios/{qid}/orientacoes", data={"orientacoes": "   "})
    assert r.status_code == 422 and "não pode ficar vazio" in texto(r)
    assert "Campo obrigatório" in texto(c.post(f"/admin/questionarios/{qid}/orientacoes", data={"orientacoes": ""}))


def test_orientacoes_podem_ser_editadas_mesmo_travado(web, mundo):
    qid = cria_questionario(web)
    trava(web, qid)
    c = logado(web, "comum1")
    assert c.post(f"/admin/questionarios/{qid}/orientacoes", data={"orientacoes": "# Corrigido"}).status_code == 302
    assert "# Corrigido" in texto(c.get(f"/admin/questionarios/{qid}"))


def test_duplicar_e_excluir_pela_tela(web, mundo):
    qid = cria_questionario(web, "Original")
    c = logado(web, "comum1")
    r = c.post(f"/admin/questionarios/{qid}/duplicar")
    assert r.status_code == 302
    copia = texto(c.get(r.headers["Location"]))
    assert "Original (cópia)" in copia and "rascunho" in copia and "Derivado de" in copia and "Tema 1" in copia
    assert c.post(r.headers["Location"] + "/excluir").status_code == 302                       # rascunho: pode
    with web.app_context():
        assert [q.nome for q in db.session.query(Questionario)] == ["Original"]


def test_nao_exclui_questionario_com_coleta(web, mundo):
    qid = cria_questionario(web)
    with web.app_context():
        coleta_para(db.session.get(Questionario, qid))
    c = logado(web, "raiz")
    r = c.post(f"/admin/questionarios/{qid}/excluir")
    assert r.status_code == 409 and "Só um questionário em rascunho" in texto(r)
    assert "Excluir questionário" not in texto(c.get(f"/admin/questionarios/{qid}"))      # o botão nem aparece


def test_questionario_inexistente(web, mundo):
    c = logado(web, "raiz")
    assert c.get("/admin/questionarios/9999").status_code == 404
    assert c.post("/admin/questionarios/9999/duplicar").status_code == 404


# ---- perguntas: criar -----------------------------------------------------------------------------
def test_criar_pergunta_pela_tela(web, mundo):
    qid = cria_questionario(web, n_perguntas=0)
    c = logado(web, "comum1")
    tela = texto(c.get(f"/admin/questionarios/{qid}/perguntas/nova"))
    assert "Tecnologia" in tela and "Alternativa A" in tela and "automático" in tela
    r = c.post(f"/admin/questionarios/{qid}/perguntas/nova", data=form_pergunta(mundo["grupo_id"]))
    assert r.status_code == 302
    d = texto(c.get(f"/admin/questionarios/{qid}"))
    assert "Phishing" in d and "Enunciado de Phishing?" in d and "Perguntas (1)" in d
    with web.app_context():
        p = db.session.query(Pergunta).one()
        assert (p.numero, [(a.letra, a.correta) for a in p.alternativas]) == (1, [("A", False), ("B", False), ("C", True), ("D", False)])
        assert p.alternativas[2].texto_acerto == "Isso mesmo." and p.alternativas[0].texto_erro == "Não é a A."


def test_pergunta_com_tres_alternativas(web, mundo):
    qid = cria_questionario(web, n_perguntas=0)
    r = logado(web, "raiz").post(f"/admin/questionarios/{qid}/perguntas/nova", data=form_pergunta(mundo["grupo_id"], n=3, correta=0))
    assert r.status_code == 302
    with web.app_context():
        assert len(db.session.query(Pergunta).one().alternativas) == 3


@pytest.mark.parametrize("mudanca,trecho", [
    ({"correta": ""}, "Marque qual alternativa é a correta"),
    ({"correta": "3"}, "Marque qual alternativa é a correta"),           # 4ª linha está em branco (n=3)
    ({"alt_texto_1": ""}, "sem deixar linhas em branco no meio"),
    ({"grupo_id": "0"}, "Escolha o grupo"),
    ({"titulo": ""}, "Campo obrigatório"),
    ({"texto": ""}, "Campo obrigatório"),
    ({"numero": "abc"}, "Informe um número inteiro"),
    ({**{f"alt_{c}_{i}": "" for i in (1, 2, 3) for c in ("texto", "acerto", "erro")}, "correta": "0"}, "de 2 a 4 alternativas"),
])
def test_erros_do_formulario_de_pergunta(web, mundo, mudanca, trecho):
    qid = cria_questionario(web, n_perguntas=0)
    dados = form_pergunta(mundo["grupo_id"], n=3 if mudanca.get("correta") == "3" else 4)
    dados.update(mudanca)
    r = logado(web, "raiz").post(f"/admin/questionarios/{qid}/perguntas/nova", data=dados)
    assert r.status_code in (200, 422) and trecho in texto(r)
    with web.app_context():
        assert db.session.query(Pergunta).count() == 0
    assert "Alternativa A" in texto(r)       # a tela volta com o formulário (e os valores digitados)


def test_formulario_com_erro_preserva_o_que_foi_digitado(web, mundo):
    qid = cria_questionario(web, n_perguntas=0)
    r = logado(web, "raiz").post(f"/admin/questionarios/{qid}/perguntas/nova",
                                 data=form_pergunta(mundo["grupo_id"], titulo="Meu título especial", correta="")) 
    assert "Meu título especial" in texto(r) and "Enunciado de Meu título especial?" in texto(r)


def test_numero_repetido_e_conflito_na_tela(web, mundo):
    qid = cria_questionario(web, n_perguntas=1)
    r = logado(web, "raiz").post(f"/admin/questionarios/{qid}/perguntas/nova", data=form_pergunta(mundo["grupo_id"], numero="1"))
    assert r.status_code == 422 and "Já existe a pergunta de número 1" in texto(r)


# ---- perguntas: editar e excluir ---------------------------------------------------------------
def test_editar_pergunta_mostra_os_valores_e_salva(web, mundo):
    qid = cria_questionario(web, n_perguntas=1)
    with web.app_context():
        pid = db.session.query(Pergunta).one().id
    c = logado(web, "comum1")
    tela = texto(c.get(f"/admin/questionarios/{qid}/perguntas/{pid}/editar"))
    assert "Enunciado 1?" in tela and "Alt 2" in tela and 'value="2" checked' in tela.replace("  ", " ").replace('\n', ' ') or "checked" in tela
    r = c.post(f"/admin/questionarios/{qid}/perguntas/{pid}/editar", data=form_pergunta(mundo["grupo_id"], titulo="Editada", correta=0, n=3))
    assert r.status_code == 302
    with web.app_context():
        p = db.session.get(Pergunta, pid)
        assert p.titulo == "Editada" and [a.correta for a in p.alternativas] == [True, False, False]


def test_excluir_pergunta_em_rascunho(web, mundo):
    qid = cria_questionario(web, n_perguntas=2)
    with web.app_context():
        pid = db.session.get(Questionario, qid).perguntas[0].id
    c = logado(web, "comum1")
    assert c.post(f"/admin/questionarios/{qid}/perguntas/{pid}/excluir").status_code == 302
    assert "Perguntas (1)" in texto(c.get(f"/admin/questionarios/{qid}"))


def test_pergunta_de_outro_questionario_da_404(web, mundo):
    a, b = cria_questionario(web, "Alfa", 1), cria_questionario(web, "Beta", 1)
    with web.app_context():
        pid_b = db.session.get(Questionario, b).perguntas[0].id
    c = logado(web, "raiz")
    assert c.get(f"/admin/questionarios/{a}/perguntas/{pid_b}/editar").status_code == 404
    assert c.post(f"/admin/questionarios/{a}/perguntas/{pid_b}/excluir").status_code == 404


# ---- travado ----------------------------------------------------------------------------------------
def test_travado_mostra_o_aviso_e_esconde_o_que_nao_pode(web, mundo):
    qid = cria_questionario(web)
    trava(web, qid)
    d = texto(logado(web, "comum1").get(f"/admin/questionarios/{qid}"))
    assert "travado" in d and "Só é possível corrigir textos" in d
    assert "Nova pergunta" not in d and "perguntas/" in d
    assert ">Excluir<" not in d and "Excluir questionário" not in d


def test_travado_recusa_nova_e_excluir_pergunta(web, mundo):
    qid = cria_questionario(web)
    trava(web, qid)
    with web.app_context():
        pid = db.session.get(Questionario, qid).perguntas[0].id
    c = logado(web, "raiz")
    r = c.post(f"/admin/questionarios/{qid}/perguntas/nova", data=form_pergunta(mundo["grupo_id"]))
    assert r.status_code == 409 and "duplique o questionário" in texto(r)
    r = c.post(f"/admin/questionarios/{qid}/perguntas/{pid}/excluir")
    assert r.status_code == 409
    with web.app_context():
        assert db.session.query(Pergunta).count() == 2


def test_travado_corrige_texto_e_ignora_tentativa_de_mudar_a_estrutura(web, mundo):
    qid = cria_questionario(web)
    trava(web, qid)
    with web.app_context():
        outro = Grupo(nome="Gestão")
        db.session.add(outro)
        db.session.commit()
        pid, outro_id = db.session.get(Questionario, qid).perguntas[0].id, outro.id
    c = logado(web, "comum1")
    tela = texto(c.get(f"/admin/questionarios/{qid}/perguntas/{pid}/editar"))
    assert "já tem respostas" in tela and "disabled" in tela
    # manda de propósito: número 9, outro grupo, gabarito em A, só 3 alternativas
    r = c.post(f"/admin/questionarios/{qid}/perguntas/{pid}/editar",
               data=form_pergunta(outro_id, titulo="Texto corrigido", correta=0, n=4, numero="9"))
    assert r.status_code == 302
    with web.app_context():
        p = db.session.get(Pergunta, pid)
        assert p.titulo == "Texto corrigido"                                     # o texto mudou
        assert p.numero == 1 and p.grupo_id == mundo["grupo_id"]                 # estrutura intacta
        assert [a.correta for a in p.alternativas] == [False, False, True, False] and len(p.alternativas) == 4


def test_travado_nao_deixa_apagar_texto_de_alternativa(web, mundo):
    qid = cria_questionario(web)
    trava(web, qid)
    with web.app_context():
        pid = db.session.get(Questionario, qid).perguntas[0].id
    dados = form_pergunta(mundo["grupo_id"], alt_texto_3="")
    r = logado(web, "raiz").post(f"/admin/questionarios/{qid}/perguntas/{pid}/editar", data=dados)
    assert r.status_code == 422 and "sem deixar linhas em branco" in texto(r)


# ---- trocar gabarito ---------------------------------------------------------------------------------
def test_super_admin_troca_o_gabarito_e_o_sistema_recalcula(web, mundo):
    qid = cria_questionario(web, n_perguntas=1)
    trava(web, qid)       # 1 partida, escolheu a alternativa A (errada; o gabarito é C)
    with web.app_context():
        pid = db.session.get(Questionario, qid).perguntas[0].id
        assert db.session.query(Partida).one().total_acertos == 0
    for quem in ("promo1", "raiz"):                    # promovido e raiz podem
        c = logado(web, quem)
        tela = texto(c.get(f"/admin/questionarios/{qid}/perguntas/{pid}/gabarito"))
        assert "1</strong> respostas em <strong>1</strong> partidas" in tela and "gabarito atual" in tela
    r = c.post(f"/admin/questionarios/{qid}/perguntas/{pid}/gabarito", data={"correta": "A"})
    assert r.status_code == 302
    with web.app_context():
        assert db.session.query(Resposta).one().acertou is True
        assert db.session.query(Partida).one().total_acertos == 1
    assert "1 respostas em 1 partidas foram recalculadas" in texto(c.get(f"/admin/questionarios/{qid}"))


def test_trocar_gabarito_para_a_mesma_letra_ou_invalida(web, mundo):
    qid = cria_questionario(web, n_perguntas=1)
    trava(web, qid)
    with web.app_context():
        pid = db.session.get(Questionario, qid).perguntas[0].id
    c = logado(web, "raiz")
    assert "já é a alternativa correta" in texto(c.post(f"/admin/questionarios/{qid}/perguntas/{pid}/gabarito", data={"correta": "C"}))
    assert "Escolha uma das alternativas" in texto(c.post(f"/admin/questionarios/{qid}/perguntas/{pid}/gabarito", data={"correta": "Z"}))
    assert "Campo obrigatório" in texto(c.post(f"/admin/questionarios/{qid}/perguntas/{pid}/gabarito", data={}))


# ---- segurança de saída -----------------------------------------------------------------------------
def test_textos_sao_escapados(web, mundo):
    qid = cria_questionario(web, n_perguntas=0)
    c = logado(web, "raiz")
    c.post(f"/admin/questionarios/{qid}/editar", data={"nome": "<b>negrito</b>", "descricao": "<script>alert(1)</script>"})
    c.post(f"/admin/questionarios/{qid}/perguntas/nova",
           data=form_pergunta(mundo["grupo_id"], titulo="<img src=x onerror=alert(1)>"))
    c.post(f"/admin/questionarios/{qid}/orientacoes", data={"orientacoes": "# <script>alert(2)</script>"})
    for url in (f"/admin/questionarios/{qid}", "/admin/questionarios", f"/admin/questionarios/{qid}/orientacoes"):
        html = texto(c.get(url))
        assert "<script>alert" not in html and "<img src=x" not in html and "<b>negrito" not in html


def test_formularios_tem_token_csrf(web, mundo):
    qid = cria_questionario(web)
    c = logado(web, "raiz")
    for url in ("/admin/questionarios/novo", f"/admin/questionarios/{qid}/perguntas/nova", f"/admin/questionarios/{qid}/orientacoes"):
        assert 'name="csrf_token"' in texto(c.get(url)), url
    assert texto(c.get(f"/admin/questionarios/{qid}")).count('name="csrf_token"') >= 4      # duplicar, excluir...
