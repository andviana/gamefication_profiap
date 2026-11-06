"""Telas de importação: upload, prévia, confirmação, erros e permissões."""
import io
import re
from pathlib import Path

import pytest

from app.blueprints.admin.importacao import MODELOS
from app.extensions import db
from app.models import Alternativa, Grupo, ImportacaoPrevia, Pergunta, Questionario
from app.services.csv_import import analisar

from conftest import cria_mundo, logado, texto, token_csrf, web  # noqa: F401

DADOS = Path(__file__).resolve().parent.parent / "data"
CAB_P = "Número da pergunta;Pergunta;Título;Grupo;Autoajuda"
CAB_A = "Número da pergunta;Letra;Texto da alternativa;Correta ou incorreta;Texto de acerto;Texto de erro"


def envia(cliente, nome="Letramento Digital 2026.1", perguntas=None, alternativas=None, descricao="", nome_p="perguntas.csv",
          nome_a="alternativas.csv", **kw):
    perguntas = (DADOS / "perguntas.csv").read_bytes() if perguntas is None else perguntas
    alternativas = (DADOS / "alternativas.csv").read_bytes() if alternativas is None else alternativas
    return cliente.post("/admin/importar", content_type="multipart/form-data", data={
        "nome": nome, "descricao": descricao,
        "arquivo_perguntas": (io.BytesIO(perguntas), nome_p), "arquivo_alternativas": (io.BytesIO(alternativas), nome_a)}, **kw)


def token_da_previa(resposta):
    return re.search(r'name="token"[^>]*value="([^"]+)"', texto(resposta)).group(1)


def csv_(cab, *linhas):
    return ("﻿" + "\n".join([cab, *linhas])).encode("utf-8")


@pytest.fixture
def mundo(web):
    return cria_mundo(web)


# ---- permissões ----------------------------------------------------------------------------------
def test_so_super_admin_acessa_a_importacao(web, mundo):
    comum = logado(web, "comum1")
    assert comum.get("/admin/importar").status_code == 403
    assert envia(comum).status_code == 403
    assert comum.post("/admin/importar/confirmar", data={"token": "x"}).status_code == 403
    assert comum.get("/admin/importar/modelo/perguntas.csv").status_code == 403
    assert "Importar" not in texto(comum.get("/admin/"))                       # nem aparece no menu
    for quem in ("promo1", "raiz"):
        c = logado(web, quem)
        assert c.get("/admin/importar").status_code == 200 and "Importar" in texto(c.get("/admin/"))
    anonimo = web.test_client()
    assert anonimo.get("/admin/importar").status_code == 302


# ---- fluxo feliz ----------------------------------------------------------------------------------------
def test_formulario_traz_instrucoes_e_modelos(web, mundo):
    html = texto(logado(web, "raiz").get("/admin/importar"))
    assert "Nada do que já existe é alterado" in html and "De <strong>2 a 4 alternativas</strong>" in html
    assert "modelo-perguntas.csv" in html and 'enctype="multipart/form-data"' in html


def test_fluxo_completo_com_os_csvs_reais(web, mundo):
    c = logado(web, "raiz")
    previa = envia(c)
    html = texto(previa)
    assert previa.status_code == 200 and "Prévia da importação" in html and "Ainda não foi gravado nada" in html
    assert "8 perguntas" in html and "28 alternativas" in html
    assert "Segurança Digital" in html and "Gestão Universitária" in html and "Grupos novos (3)" in html
    with web.app_context():          # a prévia não criou o questionário
        assert db.session.query(Questionario).count() == 0 and db.session.query(Grupo).count() == 0
        assert db.session.query(ImportacaoPrevia).count() == 1

    token = token_da_previa(previa)
    r = c.post("/admin/importar/confirmar", data={"token": token})
    assert r.status_code == 302
    detalhe = texto(c.get(r.headers["Location"]))
    assert "Letramento Digital 2026.1" in detalhe and "rascunho" in detalhe and "Perguntas (8)" in detalhe
    with web.app_context():
        assert db.session.query(Pergunta).count() == 8 and db.session.query(Alternativa).count() == 28
        assert db.session.query(Grupo).count() == 3


def test_confirmar_duas_vezes_nao_cria_dois_questionarios(web, mundo):
    c = logado(web, "raiz")
    token = token_da_previa(envia(c))
    assert c.post("/admin/importar/confirmar", data={"token": token}).status_code == 302
    r = c.post("/admin/importar/confirmar", data={"token": token})                  # duplo clique
    assert r.status_code == 409 and "já foi usada ou expirou" in texto(r)
    with web.app_context():
        assert db.session.query(Questionario).count() == 1


def test_super_admin_nao_confirma_a_previa_de_outro(web, mundo):
    token = token_da_previa(envia(logado(web, "raiz")))
    assert logado(web, "promo1").post("/admin/importar/confirmar", data={"token": token}).status_code == 404
    with web.app_context():
        assert db.session.query(Questionario).count() == 0


def test_confirmar_sem_token(web, mundo):
    r = logado(web, "raiz").post("/admin/importar/confirmar", data={})
    assert r.status_code == 302 and "/admin/importar" in r.headers["Location"]


def test_o_questionario_importado_usa_o_texto_padrao_e_a_estrutura_e_livre(web, mundo):
    c = logado(web, "raiz")
    r = c.post("/admin/importar/confirmar", data={"token": token_da_previa(envia(c))})
    detalhe = texto(c.get(r.headers["Location"]))
    assert "Sobre a sua participação" in detalhe and "Nova pergunta" in detalhe           # estrutura livre (rascunho)


# ---- erros ----------------------------------------------------------------------------------------------
def test_arquivos_com_erros_mostram_a_lista_e_nao_importam(web, mundo):
    c = logado(web, "raiz")
    r = envia(c, perguntas=csv_(CAB_P, "x;Enunciado;T;G;", "2;;T;G;"), alternativas=csv_(CAB_A, "9;A;x;Incorreta;;"))
    html = texto(r)
    assert r.status_code == 422 and "problemas nos arquivos" in html and "nada foi importado" in html
    assert "perguntas.csv" in html and "inválido" in html and "sem o texto do enunciado" in html
    assert "pergunta 9, que não existe" in html
    assert "Prévia da importação" not in html and "Analisar arquivos" in html             # volta ao formulário
    with web.app_context():
        assert db.session.query(ImportacaoPrevia).count() == 0 and db.session.query(Questionario).count() == 0


def test_erro_de_arquivo_e_de_nome(web, mundo):
    c = logado(web, "raiz")
    assert "extensão .csv" in texto(envia(c, nome_p="perguntas.txt"))
    assert "está vazio" in texto(envia(c, alternativas=b""))
    assert "não está em UTF-8" in texto(envia(c, perguntas="Número da pergunta;Pergunta;Título;Grupo;Autoajuda\n1;Ação?;T;G;".encode("latin-1")))
    r = c.post("/admin/importar", data={"nome": "", "descricao": ""}, content_type="multipart/form-data")
    html = texto(r)
    assert r.status_code == 422 and "Campo obrigatório" in html and "Selecione o arquivo de perguntas" in html


def test_nome_repetido(web, mundo):
    c = logado(web, "raiz")
    c.post("/admin/importar/confirmar", data={"token": token_da_previa(envia(c))})
    r = envia(c)
    assert r.status_code == 422 and "Já existe um questionário com este nome" in texto(r)


def test_arquivo_maior_que_o_limite(web, mundo):
    grande = b"x" * (5 * 1024 * 1024)
    r = envia(logado(web, "raiz"), perguntas=grande)
    assert r.status_code == 413 and "grande demais" in texto(r)


def test_grupo_inativo_aparece_como_erro_na_tela(web, mundo):
    with web.app_context():
        db.session.add(Grupo(nome="Tecnologia", ativo=False))
        db.session.commit()
    r = envia(logado(web, "raiz"))
    assert r.status_code == 422 and "“Tecnologia” existe, mas está inativo" in texto(r)


def test_avisos_aparecem_na_previa_sem_impedir(web, mundo):
    p = csv_(CAB_P, "1;Enunciado;T;G;")
    a = csv_(CAB_A, "1;A;x;Incorreta;;", "1;C;y;Correta;;")
    html = texto(envia(logado(web, "raiz"), perguntas=p, alternativas=a))
    assert "Avisos (não impedem a importação)" in html and "não são sequenciais" in html and "Confirmar importação" in html


# ---- modelos e segurança -----------------------------------------------------------------------------
def test_modelos_para_baixar_sao_validos(web, mundo):
    c = logado(web, "raiz")
    p, a = c.get("/admin/importar/modelo/perguntas.csv"), c.get("/admin/importar/modelo/alternativas.csv")
    assert p.status_code == 200 and "text/csv" in p.content_type and "attachment" in p.headers["Content-Disposition"]
    assert p.data.startswith(b"\xef\xbb\xbf") and b"N\xc3\xbamero da pergunta" in p.data
    resultado = analisar(p.data, a.data)
    assert resultado.erros == [] and len(resultado.perguntas) == 1                  # o modelo passa no próprio analisador
    assert c.get("/admin/importar/modelo/outro.csv").status_code == 404


def test_html_nos_csvs_e_escapado(web, mundo):
    c = logado(web, "raiz")
    p = csv_(CAB_P, "1;<script>alert(1)</script>;<img src=x onerror=alert(2)>;<b>Grupo</b>;")
    a = csv_(CAB_A, "1;A;<i>x</i>;Incorreta;;", "1;B;y;Correta;;")
    previa = envia(c, perguntas=p, alternativas=a)
    for html in (texto(previa),):
        assert "<script>alert" not in html and "<img src=x" not in html and "<b>Grupo" not in html
    r = c.post("/admin/importar/confirmar", data={"token": token_da_previa(previa)})
    detalhe = texto(c.get(r.headers["Location"]))
    assert "<script>alert" not in detalhe and "<img src=x" not in detalhe


def test_confirmacao_exige_csrf(web, mundo):
    c = logado(web, "raiz")
    token = token_da_previa(envia(c))
    web.config["WTF_CSRF_ENABLED"] = True
    assert c.post("/admin/importar/confirmar", data={"token": token}).status_code == 400
    csrf = token_csrf(texto(c.get("/admin/importar")))
    assert c.post("/admin/importar/confirmar", data={"token": token, "csrf_token": csrf}).status_code == 302
