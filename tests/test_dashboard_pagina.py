"""Página do dashboard (6c): acesso, arquivos servidos e regras de segurança do JavaScript."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import cria_mundo, logado, texto, web  # noqa: F401

RAIZ = Path(__file__).resolve().parent.parent
JS = RAIZ / "app/static/js/dashboard.js"


@pytest.fixture
def cliente(web):
    cria_mundo(web)
    return logado(web, "comum1")


def test_a_pagina_exige_login(web):
    r = web.test_client().get("/admin/dashboard")
    assert r.status_code == 302 and "/entrar" in r.headers["Location"]


def test_a_pagina_abre_para_qualquer_usuario_logado(web):
    cria_mundo(web)
    for login in ("comum1", "promo1", "raiz"):
        r = logado(web, login).get("/admin/dashboard")
        assert r.status_code == 200
    html = texto(r)
    assert 'id="f-questionario"' in html and "obrigatório" in html
    assert 'data-api="/admin/api/dashboard"' in html
    assert 'aria-current="page"' in html and "Dashboard" in html


def test_a_pagina_traz_os_blocos_da_especificacao(cliente):
    html = texto(cliente.get("/admin/dashboard"))
    for trecho in ("g-questoes", "g-grupos", "g-comp", "g-heat", "g-det", "g-evo", "exportar", "tabs", "busca", "decal", "k-acerto",
                   "k-tempo", "Respondente = partida finalizada"):
        assert trecho in html, trecho
    assert html.count("data-png") == 6 and html.count("data-tabela") == 6      # imagem e tabela gêmea de cada gráfico


def test_os_arquivos_da_pagina_sao_servidos(cliente):
    html = texto(cliente.get("/admin/dashboard"))
    for url in re.findall(r'(?:src|href)="(/static/[^"]+)"', html):
        assert cliente.get(url).status_code == 200, url
    assert "/static/vendor/echarts/echarts.min.js" in html and "/static/js/dashboard.js" in html and "/static/css/dashboard.css" in html


def test_o_inicio_aponta_para_o_dashboard(cliente):
    html = texto(cliente.get("/admin/"))
    assert "/admin/dashboard" in html and "Em construção" not in html


def _sem_comentarios(codigo: str) -> str:
    codigo = re.sub(r"/\*.*?\*/", "", codigo, flags=re.S)
    return re.sub(r"^\s*//.*$|(?<=\s)//\s.*$", "", codigo, flags=re.M)


def test_o_js_nao_injeta_html_no_dom():
    """Rótulos vindos do banco (campus, curso, enunciado...) só entram com textContent."""
    codigo = _sem_comentarios(JS.read_text(encoding="utf-8"))
    assert ".innerHTML" not in codigo and "insertAdjacentHTML" not in codigo and "document.write" not in codigo


def test_todo_texto_de_tooltip_com_dado_do_banco_passa_por_esc():
    codigo = _sem_comentarios(JS.read_text(encoding="utf-8"))
    for trecho in ("esc(i.nome)", "esc(i.o.grupo)", "esc(i.g)", "esc(i.rot)", "esc(i.texto)", "esc(rot)"):
        assert trecho in codigo, trecho


def test_o_js_nao_guarda_nada_no_navegador():
    codigo = _sem_comentarios(JS.read_text(encoding="utf-8"))
    assert not re.search(r"localStorage|sessionStorage|document\.cookie|indexedDB", codigo)


@pytest.mark.skipif(shutil.which("node") is None, reason="node não está instalado")
def test_o_js_tem_sintaxe_valida():
    r = subprocess.run(["node", "--check", str(JS)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_o_js_so_chama_endpoints_que_existem(web):
    """Cada caminho de `api('...')` no JS precisa ser uma rota real do blueprint."""
    codigo = JS.read_text(encoding="utf-8")
    chamados = set(re.findall(r"api\('([a-z/]+?)'", codigo)) | {"export.csv"}
    rotas = {r.rule for r in web.url_map.iter_rules()}
    for nome in chamados:
        alvo = "/admin/api/dashboard/" + ("questao/<int:numero>" if nome == "questao/" else nome)
        assert alvo in rotas, nome
