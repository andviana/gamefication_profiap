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
        if arquivo.name == "teste.js":        # o autoteste só LÊ o armazenamento, para provar que o jogo não grava nada
            continue
        codigo = _sem_comentarios(arquivo.read_text(encoding="utf-8"))
        assert not re.search(r"localStorage|sessionStorage|document\.cookie|indexedDB", codigo), arquivo.name


def test_a_pagina_de_autoteste_e_servida(web):
    assert web.test_client().get("/static/game/teste.html").status_code == 200


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js não está instalado")
def test_suite_de_testes_do_api_js_em_node():
    r = subprocess.run(["node", "--test", "tests/js/api.test.js"], cwd=RAIZ, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-1500:]
    assert "fail 0" in r.stdout and "pass 20" in r.stdout


def test_o_campo_do_codigo_sempre_abre_vazio_com_foco_e_borda_neon():
    """Ao abrir, recarregar, errar o código ou jogar de novo, o campo está vazio e focado (borda verde neon, cursor piscando)."""
    js = (RAIZ / "app/static/game/js/screens.js").read_text(encoding="utf-8")
    estado = (RAIZ / "app/static/game/js/state.js").read_text(encoding="utf-8")
    assert "lastCode" not in js and "lastCode" not in estado                      # o último código não é mais lembrado
    abre = js.split("if (state === S.TITLE) {")[1].split("if (state === S.INSTRUCTIONS)")[0]
    assert "nameInput.value = ''" in abre and "nameInput.focus()" in abre and "CODE.autoFocus = true" in abre
    assert js.count("limpaCodigo()") >= 3                                         # erro do servidor, falha de rede e volta pelo histórico
    assert "'pageshow'" in js and "const NEON = '#39ff14'" in js and "stroke: focused ? NEON" in js


def test_tela_de_codigo_rotulo_centralizado_com_dica_e_logos_planas():
    js = (RAIZ / "app/static/game/js/screens.js").read_text(encoding="utf-8")
    renderer = (RAIZ / "app/static/game/js/renderer.js").read_text(encoding="utf-8")
    assert "const rotulo = 'CÓDIGO DA TURMA'" in js and "W / 2 - (tw + GAP + 2 * RI) / 2" in js        # rótulo centralizado
    assert "const AJUDA_CODIGO = 'Peça o código de 5 letras ao seu professor.'" in js and "inRect(mouse, ...box)" in js
    assert "Digite o código e pressione Enter ou clique em Iniciar" not in js                       # sem texto sob o botão Iniciar
    assert "Avaliação formativa gamificada" not in js                                              # sem a linha de subtítulo
    assert "else msg = 'Peça o código" not in js                                                     # a dica fica só no "?"
    logo = renderer.split("function drawLogo")[1].split("\n  }\n")[0]
    assert "ctx.transform" not in logo and "isoBox" not in logo and "poly(" not in logo              # logo plana, sem inclinação
    assert "rr(ctx, cx0, cy0, cw, ch, r)" in logo and "shadowBlur" in logo                          # cantos arredondados e sombra


def test_tela_de_avatar_enxuta_com_ajuda_em_modal():
    js = (RAIZ / "app/static/game/js/screens.js").read_text(encoding="utf-8")
    tela = js.split("function drawAvatarSelect()")[1].split("QUIZ_PLAYING")[0]
    assert "'Crie seu avatar'" in tela and "IDENTIFIQUE" not in js and "'digite um nome'" in tela and "digite seu nome" not in js
    for removido in ("PERFIL", "Escolha um avatar'", "Clique em um avatar ou use as setas", "Letras e números, sem espaços, acentos ou símbolos.",
                     "Tab: ir aos avatares", "Shift+Tab: voltar ao nome", "Digite o nome · Tab leva", "Para confirmar,"):
        assert removido not in tela, removido
    assert "stroke: focused ? NEON" in tela and "AVS.autoFocus" in tela                       # foco inicial: borda verde neon e prompt
    onenter = js.split("if (state === S.AVATAR_SELECT) {")[1].split("if (state === S.QUIZ_PLAYING)")[0]
    assert "AVS.autoFocus = true" in onenter and "nameInput.focus()" in onenter and "coarse" not in onenter
    # o texto de apoio vive no modal de ajuda, aberto pelo "?" ao lado do A+
    assert "function drawHelpModal" in js and "const HELP_AVATAR" in js and "iconButton(a.x - size - 8, a.y, size, 'Ajuda', openHelp" in js
    assert "if (HELP.open) { if (confirm || k === 'Escape') closeHelp()" in js and "HELP.open && GS.current === S.AVATAR_SELECT) drawHelpModal()" in js
