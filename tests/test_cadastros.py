"""Campus, curso e grupo: criar, renomear, inativar e reativar (nunca apagar)."""
import pytest

from app.errors import Conflito, Invalido, NaoEncontrado
from app.extensions import db
from app.models import Campus, Coleta, Curso, Grupo, Pergunta, Questionario

from conftest import cria_mundo, logado, texto, web  # noqa: F401

TIPOS = {"campus": Campus, "curso": Curso, "grupo": Grupo}


@pytest.fixture
def servicos(web):
    ids = cria_mundo(web)
    with web.app_context():
        yield web.extensions["container"].referencias, db.session.get(__import__("app.models", fromlist=["Usuario"]).Usuario, ids["raiz"])


@pytest.mark.parametrize("tipo", TIPOS)
def test_criar_listar_renomear_e_inativar(servicos, tipo):
    refs, ator = servicos
    svc = refs[tipo]
    a = svc.criar(ator, "  Belém   Centro ")
    assert a.nome == "Belém Centro" and a.ativo is True        # espaços normalizados
    svc.criar(ator, "Altamira")
    assert [r.nome for r, _ in svc.listar()] == ["Altamira", "Belém Centro"]   # ordem alfabética
    svc.renomear(ator, a.id, "Belém")
    assert svc.obter(a.id).nome == "Belém"
    svc.definir_ativo(ator, a.id, False)
    assert not svc.obter(a.id).ativo and [r.nome for r in svc.ativos()] == ["Altamira"]
    svc.definir_ativo(ator, a.id, True)
    assert svc.obter(a.id).ativo


@pytest.mark.parametrize("tipo", TIPOS)
def test_nome_unico_sem_diferenciar_maiusculas(servicos, tipo):
    refs, ator = servicos
    svc = refs[tipo]
    a = svc.criar(ator, "Pedagogia")
    for repetido in ("pedagogia", "PEDAGOGIA", " Pedagogia  "):
        with pytest.raises(Conflito) as e:
            svc.criar(ator, repetido)
        assert e.value.detalhes["campo"] == "nome"
    outro = svc.criar(ator, "Letras")
    with pytest.raises(Conflito):
        svc.renomear(ator, outro.id, "pedagogia")
    svc.renomear(ator, a.id, "PEDAGOGIA")      # renomear para o mesmo nome (só muda a caixa) é permitido


@pytest.mark.parametrize("nome", ["", " ", "A", "x" * 121])
def test_nome_invalido(servicos, nome):
    refs, ator = servicos
    with pytest.raises(Invalido):
        refs["campus"].criar(ator, nome)


def test_registro_inexistente(servicos):
    refs, ator = servicos
    with pytest.raises(NaoEncontrado):
        refs["curso"].renomear(ator, 9999, "Qualquer")
    with pytest.raises(NaoEncontrado):
        refs["grupo"].definir_ativo(ator, 9999, False)


def test_conta_o_uso_de_cada_registro(servicos):
    refs, ator = servicos
    campus, curso, grupo = refs["campus"].criar(ator, "Belém"), refs["curso"].criar(ator, "Letras"), refs["grupo"].criar(ator, "Tecnologia")
    q = Questionario(nome="Q")
    q.perguntas.append(Pergunta(numero=1, texto="t", titulo="t", grupo_id=grupo.id))
    from datetime import date
    db.session.add_all([q, Coleta(codigo="ABCDE", questionario=q, campus_id=campus.id, curso_id=curso.id, ano=2026, periodo=1,
                                  data_inicio=date(2026, 3, 1), data_fim=date(2026, 3, 2))])
    db.session.commit()
    assert [(r.nome, n) for r, n in refs["campus"].listar()] == [("Belém", 1)]
    assert [(r.nome, n) for r, n in refs["curso"].listar()] == [("Letras", 1)]
    assert [(r.nome, n) for r, n in refs["grupo"].listar()] == [("Tecnologia", 1)]


# ---- telas ------------------------------------------------------------------------------------
@pytest.mark.parametrize("tipo", TIPOS)
def test_qualquer_usuario_logado_gerencia_os_cadastros(web, tipo):
    cria_mundo(web)
    c = logado(web, "comum1")                           # usuário comum também pode
    assert c.get(f"/admin/cadastros/{tipo}").status_code == 200
    r = c.post(f"/admin/cadastros/{tipo}", data={"nome": "Novo Registro"})
    assert r.status_code == 302
    html = texto(c.get(f"/admin/cadastros/{tipo}"))
    assert "Novo Registro" in html and "ativo" in html
    with web.app_context():
        rid = db.session.query(TIPOS[tipo]).one().id
    assert c.post(f"/admin/cadastros/{tipo}/{rid}/editar", data={"nome": "Registro Renomeado"}).status_code == 302
    assert c.post(f"/admin/cadastros/{tipo}/{rid}/ativo", data={"ativo": "0"}).status_code == 302
    html = texto(c.get(f"/admin/cadastros/{tipo}"))
    assert "Registro Renomeado" in html and "inativo" in html and "Reativar" in html
    c.post(f"/admin/cadastros/{tipo}/{rid}/ativo", data={"ativo": "1"})
    assert "Inativar" in texto(c.get(f"/admin/cadastros/{tipo}"))


def test_nao_existe_rota_para_apagar(web):
    cria_mundo(web)
    c = logado(web, "raiz")
    c.post("/admin/cadastros/campus", data={"nome": "Belém"})
    with web.app_context():
        rid = db.session.query(Campus).one().id
    assert c.post(f"/admin/cadastros/campus/{rid}/excluir").status_code == 404
    assert c.delete(f"/admin/cadastros/campus/{rid}").status_code in (404, 405)   # nenhuma rota aceita apagar


def test_cadastros_exigem_login_e_tipo_valido(web):
    cria_mundo(web)
    assert web.test_client().get("/admin/cadastros/campus").status_code == 302
    assert logado(web, "raiz").get("/admin/cadastros/turma").status_code == 404


def test_formulario_mostra_erros(web):
    cria_mundo(web)
    c = logado(web, "raiz")
    c.post("/admin/cadastros/curso", data={"nome": "Letras"})
    r = c.post("/admin/cadastros/curso", data={"nome": "letras"})
    assert r.status_code == 422 and "Já existe um registro de curso com este nome" in texto(r)
    r = c.post("/admin/cadastros/curso", data={"nome": "x"})
    assert r.status_code == 422 and "de 2 a 120 caracteres" in texto(r)
    r = c.post("/admin/cadastros/curso", data={"nome": ""})
    assert "Campo obrigatório" in texto(r)


def test_nomes_sao_escapados(web):
    cria_mundo(web)
    c = logado(web, "raiz")
    c.post("/admin/cadastros/grupo", data={"nome": "<img src=x onerror=alert(1)>"})
    html = texto(c.get("/admin/cadastros/grupo"))
    assert "<img src=x" not in html and "&lt;img src=x" in html
