"""Telas de coletas: lista, criação com avisos, edição com trava, ativar e desativar."""
import re
from datetime import date, datetime, timezone

import pytest

from app.extensions import db
from app.models import Campus, Coleta, Curso, Grupo, Questionario, Usuario
from app.services.perguntas import DadosAlternativa, DadosPergunta

from conftest import cria_mundo, logado, responde, texto, web  # noqa: F401

AGORA = datetime(2026, 3, 10, 18, 0, tzinfo=timezone.utc)      # 10/03/2026, 15h em Belém


@pytest.fixture
def base(web):
    """Usuários, campus, cursos e um questionário com uma pergunta (rascunho)."""
    ids = cria_mundo(web)
    with web.app_context():
        c = web.extensions["container"]
        c.coletas.relogio = lambda: AGORA
        raiz = db.session.get(Usuario, ids["raiz"])
        grupo = Grupo(nome="Tecnologia")
        belem, paragominas, inativo = Campus(nome="Belém"), Campus(nome="Paragominas"), Campus(nome="Campus Desativado", ativo=False)
        pedagogia, letras = Curso(nome="Pedagogia"), Curso(nome="Letras")
        db.session.add_all([grupo, belem, paragominas, inativo, pedagogia, letras])
        db.session.commit()
        q = c.questionarios.criar(raiz, "Letramento Digital")
        c.perguntas.criar(raiz, q.id, DadosPergunta(texto="Enunciado?", titulo="Tema", grupo_id=grupo.id,
                                                    alternativas=[DadosAlternativa("a", True), DadosAlternativa("b")]))
        vazio = c.questionarios.criar(raiz, "Sem Perguntas")
        return dict(q=q.id, vazio=vazio.id, belem=belem.id, parag=paragominas.id, inativo=inativo.id, pedagogia=pedagogia.id, letras=letras.id)


def form_coleta(base, **mudancas):
    d = {"questionario_id": base["q"], "campus_id": base["belem"], "curso_id": base["pedagogia"], "ano": 2026, "periodo": 1,
         "data_inicio": "2026-03-01", "data_fim": "2026-03-31"}
    d.update(mudancas)
    return d


def cria(cliente, base, **mudancas):
    """Cria uma coleta pela tela e devolve (resposta, código)."""
    r = cliente.post("/admin/coletas/nova", data=form_coleta(base, **mudancas))
    return r


def opcao_marcada(html, valor):
    """A <option> com este valor está marcada (o WTForms escreve `selected` antes de `value`)."""
    return re.search(r'<option(?=[^>]*\bselected\b)(?=[^>]*\bvalue="%s")' % valor, html) is not None


def codigo_do_detalhe(cliente, resposta):
    html = texto(cliente.get(resposta.headers["Location"]))
    return re.search(r'class="cod-grande"[^>]*>([A-Z]{5})<', html).group(1), html


def uma_coleta_com_partida(web, base):
    c = logado(web, "raiz")
    r = cria(c, base)
    with web.app_context():
        coleta = db.session.query(Coleta).one()
        q = db.session.get(Questionario, base["q"])
        responde(coleta, [(p, p.alternativas[0]) for p in q.perguntas])
        return c, coleta.id, coleta.codigo


# ---- acesso e navegação ---------------------------------------------------------------------------
def test_exige_login_e_qualquer_usuario_logado_gerencia(web, base):
    assert web.test_client().get("/admin/coletas").status_code == 302
    comum = logado(web, "comum1")
    assert comum.get("/admin/coletas").status_code == 200 and comum.get("/admin/coletas/nova").status_code == 200
    assert cria(comum, base).status_code == 302
    assert "Coletas" in texto(comum.get("/admin/"))                                   # item do menu


def test_lista_vazia(web, base):
    html = texto(logado(web, "raiz").get("/admin/coletas"))
    assert "Nenhuma coleta ainda" in html and "Nova coleta" in html and "Filtrar" not in html


# ---- criar ----------------------------------------------------------------------------------------
def test_formulario_novo_traz_sugestoes_e_so_opcoes_validas(web, base):
    html = texto(logado(web, "raiz").get("/admin/coletas/nova"))
    assert 'value="2026-03-10"' in html and 'value="2026-04-09"' in html            # hoje e hoje + 30 dias
    assert opcao_marcada(html, 2026) and "2025" in html and "2027" in html and "2024" not in html
    assert "Belém" in html and "Pedagogia" in html and "Campus Desativado" not in html     # inativo não aparece
    assert "Letramento Digital (rascunho)" in html and "Sem Perguntas" not in html          # sem perguntas não aparece
    assert "a estrutura dele trava na primeira resposta recebida" in html


def test_criar_coleta_mostra_o_codigo_e_avisa_da_trava(web, base):
    c = logado(web, "raiz")
    r = cria(c, base)
    assert r.status_code == 302 and "/admin/coletas/" in r.headers["Location"]
    codigo, html = codigo_do_detalhe(c, r)
    assert len(codigo) == 5 and not set("ILO") & set(codigo)
    assert f"Código de acesso: {codigo}" in html and "passou de “rascunho” para “em coleta”" in html
    assert f'data-copiar="{codigo}"' in html and "Copiar código" in html
    assert "01/03/2026, a partir das 00:00" in html and "31/03/2026, até as 23:59" in html and "America/Belem" in html
    assert "Belém" in html and "Pedagogia" in html and "2026, 1º período" in html and "aberta" in html
    assert "em coleta" in html                                                    # o questionário mudou de estado


def test_segunda_coleta_no_mesmo_questionario_nao_repete_o_aviso_de_trava(web, base):
    c = logado(web, "raiz")
    primeira = cria(c, base)
    assert "passou de “rascunho”" in texto(c.get(primeira.headers["Location"]))        # a 1ª avisa (e consome o aviso)
    segunda = cria(c, base, periodo=2)
    assert "passou de “rascunho”" not in texto(c.get(segunda.headers["Location"]))


def test_lista_mostra_o_codigo_a_turma_o_prazo_e_a_situacao(web, base):
    c = logado(web, "raiz")
    codigo, _ = codigo_do_detalhe(c, cria(c, base))
    html = texto(c.get("/admin/coletas"))
    assert codigo in html and f'data-copiar="{codigo}"' in html
    assert "Belém · Pedagogia" in html and "2026/1" in html and "01/03/2026 a 31/03/2026" in html
    assert "sit-aberta" in html and "Letramento Digital" in html


@pytest.mark.parametrize("mudanca,trecho", [
    ({"ano": 2030}, "O ano deve ser 2025, 2026, 2027"), ({"ano": 2024}, "O ano deve ser"), ({"periodo": 3}, "período deve ser 1 ou 2"),
    ({"data_fim": "2026-02-28"}, "não pode ser anterior"), ({"data_inicio": ""}, "Campo obrigatório"),
    ({"data_fim": "31/03/2026"}, "Informe uma data válida"), ({"data_inicio": "ontem"}, "Informe uma data válida"),
    ({"questionario_id": 0}, "Escolha o questionário"), ({"campus_id": 0}, "Escolha o campus"), ({"curso_id": 0}, "Escolha o curso"),
])
def test_erros_do_formulario(web, base, mudanca, trecho):
    r = cria(logado(web, "raiz"), base, **mudanca)
    assert r.status_code == 422 and trecho in texto(r)
    with web.app_context():
        assert db.session.query(Coleta).count() == 0


def test_questionario_sem_perguntas_e_campus_inativo_sao_recusados(web, base):
    c = logado(web, "raiz")
    assert "ainda não tem perguntas" in texto(cria(c, base, questionario_id=base["vazio"]))
    assert "está inativo" in texto(cria(c, base, campus_id=base["inativo"]))


def test_formulario_com_erro_preserva_o_que_foi_escolhido(web, base):
    html = texto(cria(logado(web, "raiz"), base, ano=2030, campus_id=base["parag"], data_inicio="2026-05-05"))
    assert opcao_marcada(html, base["parag"]) and 'value="2026-05-05"' in html


# ---- duplicidade -----------------------------------------------------------------------------------
def test_duplicidade_avisa_e_so_cria_com_confirmacao(web, base):
    c = logado(web, "raiz")
    primeiro, _ = codigo_do_detalhe(c, cria(c, base))
    r = cria(c, base, data_inicio="2026-05-01", data_fim="2026-05-31")
    html = texto(r)
    assert r.status_code == 200 and "Já existe 1 coleta para esta mesma turma" in html and primeiro in html
    assert "Criar mesmo assim" in html and 'value="2026-05-31"' in html              # mantém o que foi digitado
    with web.app_context():
        assert db.session.query(Coleta).count() == 1
    r = c.post("/admin/coletas/nova", data={**form_coleta(base, data_inicio="2026-05-01", data_fim="2026-05-31"), "confirmar_duplicidade": "1"})
    assert r.status_code == 302
    with web.app_context():
        assert db.session.query(Coleta).count() == 2


def test_turma_diferente_nao_gera_aviso(web, base):
    c = logado(web, "raiz")
    cria(c, base)
    for mudanca in ({"periodo": 2}, {"campus_id": base["parag"]}, {"curso_id": base["letras"]}, {"ano": 2027}):
        assert cria(c, base, **mudanca).status_code == 302, mudanca


# ---- detalhe --------------------------------------------------------------------------------------
def test_coleta_inexistente(web, base):
    c = logado(web, "raiz")
    assert c.get("/admin/coletas/9999").status_code == 404 and c.get("/admin/coletas/9999/editar").status_code == 404
    assert c.post("/admin/coletas/9999/ativo", data={"ativo": "0"}).status_code == 404


# ---- editar ---------------------------------------------------------------------------------------
def test_editar_antes_da_primeira_partida_muda_a_turma_mas_nao_o_codigo(web, base):
    c = logado(web, "raiz")
    r = cria(c, base)
    codigo, _ = codigo_do_detalhe(c, r)
    coleta_id = int(re.search(r"/coletas/(\d+)", r.headers["Location"]).group(1))
    tela = texto(c.get(f"/admin/coletas/{coleta_id}/editar"))
    assert "já tem partidas" not in tela and not re.search(r'<select[^>]*\bdisabled\b', tela)     # nada travado ainda
    r = c.post(f"/admin/coletas/{coleta_id}/editar", data=form_coleta(base, campus_id=base["parag"], periodo=2, ano=2027,
                                                                     data_inicio="2026-08-01", data_fim="2026-08-31"))
    assert r.status_code == 302
    with web.app_context():
        e = db.session.get(Coleta, coleta_id)
        assert (e.campus_id, e.periodo, e.ano, e.codigo) == (base["parag"], 2, 2027, codigo)


def test_depois_da_primeira_partida_a_identidade_fica_travada_na_tela(web, base):
    c, coleta_id, codigo = uma_coleta_com_partida(web, base)
    tela = texto(c.get(f"/admin/coletas/{coleta_id}/editar"))
    assert "já tem partidas" in tela and "não mudam mais" in tela
    for campo in ("questionario_id", "campus_id", "curso_id", "ano", "periodo"):
        assert re.search(r'<select[^>]*id="%s"[^>]*disabled' % campo, tela) or re.search(r'<select[^>]*disabled[^>]*id="%s"' % campo, tela), campo
    assert not re.search(r'<input[^>]*id="data_inicio"[^>]*disabled', tela)         # o prazo segue editável
    # mandando de propósito outra identidade: é ignorada; o prazo muda
    r = c.post(f"/admin/coletas/{coleta_id}/editar", data=form_coleta(base, campus_id=base["parag"], periodo=2, ano=2027, data_fim="2026-06-30"))
    assert r.status_code == 302
    with web.app_context():
        e = db.session.get(Coleta, coleta_id)
        assert (e.campus_id, e.periodo, e.ano, e.data_fim, e.codigo) == (base["belem"], 1, 2026, date(2026, 6, 30), codigo)


def test_editar_para_a_identidade_de_outra_coleta_avisa(web, base):
    c = logado(web, "raiz")
    cria(c, base)
    r = cria(c, base, periodo=2)
    outra = int(re.search(r"/coletas/(\d+)", r.headers["Location"]).group(1))
    r = c.post(f"/admin/coletas/{outra}/editar", data=form_coleta(base, periodo=1))
    assert r.status_code == 200 and "Já existe 1 coleta para esta mesma turma" in texto(r) and "Salvar mesmo assim" in texto(r)


# ---- ativar e desativar ----------------------------------------------------------------------------
def test_desativar_e_reativar(web, base):
    c = logado(web, "raiz")
    r = cria(c, base)
    coleta_id = int(re.search(r"/coletas/(\d+)", r.headers["Location"]).group(1))
    assert c.post(f"/admin/coletas/{coleta_id}/ativo", data={"ativo": "0"}).status_code == 302
    html = texto(c.get(f"/admin/coletas/{coleta_id}"))
    assert "desativada" in html and "Desativada manualmente" in html and ">Ativar<" in html
    assert "sit-desativada" in texto(c.get("/admin/coletas"))
    assert c.post(f"/admin/coletas/{coleta_id}/ativo", data={"ativo": "1"}).status_code == 302
    html = texto(c.get(f"/admin/coletas/{coleta_id}"))
    assert "sit-aberta" in html and "Dentro do prazo e ativa" in html


def test_situacoes_por_prazo(web, base):
    c = logado(web, "raiz")
    cria(c, base, periodo=1, data_inicio="2026-03-01", data_fim="2026-03-31")      # aberta
    cria(c, base, periodo=2, data_inicio="2026-08-01", data_fim="2026-08-31")      # agendada
    cria(c, base, ano=2025, data_inicio="2025-03-01", data_fim="2025-03-31")       # encerrada
    html = texto(c.get("/admin/coletas"))
    assert html.count("sit-aberta") == 1 and html.count("sit-agendada") == 1 and html.count("sit-encerrada") == 1


# ---- filtros ---------------------------------------------------------------------------------------
def test_filtros_da_lista(web, base):
    c = logado(web, "raiz")
    cria(c, base, periodo=1)
    cria(c, base, periodo=2, data_inicio="2026-08-01", data_fim="2026-08-31")
    assert texto(c.get("/admin/coletas?situacao=agendada")).count('class="codigo"') == 1
    assert texto(c.get(f"/admin/coletas?questionario={base['q']}")).count('class="codigo"') == 2
    assert "Nenhuma coleta com estes filtros" in texto(c.get("/admin/coletas?situacao=encerrada"))
    assert texto(c.get("/admin/coletas?situacao=bobagem&questionario=abc")).count('class="codigo"') == 2    # valor inválido é ignorado
    assert "Limpar filtros" in texto(c.get("/admin/coletas?situacao=aberta"))


# ---- segurança --------------------------------------------------------------------------------------
def test_nomes_sao_escapados(web, base):
    with web.app_context():
        db.session.add(Campus(nome="<script>alert(1)</script>"))
        db.session.commit()
    c = logado(web, "raiz")
    html = texto(c.get("/admin/coletas/nova"))
    assert "<script>alert(1)" not in html and "&lt;script&gt;alert(1)" in html


def test_formularios_e_acoes_exigem_csrf(web, base):
    c = logado(web, "raiz")
    r = cria(c, base)
    coleta_id = int(re.search(r"/coletas/(\d+)", r.headers["Location"]).group(1))
    assert 'name="csrf_token"' in texto(c.get("/admin/coletas/nova")) and 'name="csrf_token"' in texto(c.get(f"/admin/coletas/{coleta_id}"))
    web.config["WTF_CSRF_ENABLED"] = True
    assert c.post(f"/admin/coletas/{coleta_id}/ativo", data={"ativo": "0"}).status_code == 400
    assert c.post("/admin/coletas/nova", data=form_coleta(base)).status_code == 400
