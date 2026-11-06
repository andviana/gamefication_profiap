"""O jogo servido pelo Flask na raiz: a página, os arquivos que ela carrega e a suíte de testes em Node do api.js."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import web  # noqa: F401

RAIZ = Path(__file__).resolve().parent.parent
JOGO = RAIZ / "app" / "static" / "game"


def _html(web):
    r = web.test_client().get("/")
    return r, r.get_data(as_text=True)


def test_a_raiz_serve_o_jogo(web):
    r, html = _html(web)
    assert r.status_code == 200 and "text/html" in r.content_type
    assert '<base href="/static/game/">' in html and 'id="gameCanvas"' in html and "<title>TechQuiz Campus" in html
    assert r.headers["Cache-Control"] == "no-cache"


def test_todos_os_arquivos_da_pagina_existem_e_sao_servidos(web):
    _, html = _html(web)
    caminhos = re.findall(r'<(?:script|link)[^>]*?(?:src|href)="([^"]+)"', html)
    caminhos = [c for c in caminhos if not c.startswith(("http", "/"))]
    assert len(caminhos) >= 9
    cliente = web.test_client()
    for c in caminhos:
        assert (JOGO / c).is_file(), f"{c} não existe em app/static/game"
        assert cliente.get(f"/static/game/{c}").status_code == 200, c


def test_a_ordem_dos_scripts_garante_o_api_antes_do_estado(web):
    _, html = _html(web)
    scripts = re.findall(r'<script src="([^"]+)"', html)
    assert scripts.index("config/config.js") < scripts.index("js/api.js") < scripts.index("js/state.js") < scripts.index("js/screens.js") < scripts.index("js/main.js")


def test_o_jogo_nao_carrega_mais_perguntas_de_arquivo(web):
    _, html = _html(web)
    assert "questions_data" not in html
    for arquivo in (JOGO / "js").glob("*.js"):
        texto = arquivo.read_text(encoding="utf-8")
        assert "QUIZ_DATA" not in texto, f"{arquivo.name} ainda usa window.QUIZ_DATA"


def test_o_jogo_nao_envia_xp_nem_dados_pessoais():
    api = (JOGO / "js" / "api.js").read_text(encoding="utf-8")
    corpo = re.search(r"function montaPayload\(.*?\n  }\n", api, re.S).group(0)
    for proibido in ("score", "xp", "playerName", "selectedAvatar", "nome", "avatar", "isCorrect"):
        assert proibido not in corpo, f"montaPayload menciona {proibido}"


def _sem_comentarios(js: str) -> str:
    js = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$|(?<=[;{}\s])//.*$", "", js)


def test_o_jogo_nao_usa_armazenamento_do_navegador():
    for arquivo in (JOGO / "js").glob("*.js"):
        codigo = _sem_comentarios(arquivo.read_text(encoding="utf-8"))
        assert not re.search(r"localStorage|sessionStorage|document\.cookie|indexedDB", codigo), arquivo.name


def test_a_pagina_de_autoteste_e_servida(web):
    assert web.test_client().get("/static/game/teste.html").status_code == 200


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js não está instalado")
def test_suite_de_testes_do_api_js_em_node():
    r = subprocess.run(["node", "--test", "tests/js/api.test.js"], cwd=RAIZ, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-1500:]
    assert "fail 0" in r.stdout and "pass 20" in r.stdout
