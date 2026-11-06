"""Dashboard (6b): números conferidos contra contagem manual sobre um conjunto fixo.

Q1 e Q2 são do grupo Segurança, Q3 do grupo Tecnologia; gabaritos A, B e C. Cinco partidas:
  P1 (C1) A B C -> 3 acertos     P2 (C1) B B D -> 1     P3 (C1) B A D -> 0
  P4 (C2) A C C -> 2             P5 (C2) B B A -> 1     => 15 respostas, 7 acertos, 8 erros
C1 = Belém/Pedagogia 2026/1; C2 = Paragominas/Agronomia 2026/2. Tempo: Q1 = 1000..5000 ms (P1..P5), Q2 e Q3 = 2000 ms."""
import csv
import io
from datetime import date, datetime, timezone

import pytest

from app.extensions import db
from app.models import Alternativa, Campus, Coleta, Curso, Grupo, Partida, Resposta, Usuario
from app.services.dashboard import _seguro
from app.services.perguntas import DadosAlternativa, DadosPergunta

from conftest import cria_mundo, logado, web  # noqa: F401

BASE = "/admin/api/dashboard"
GABARITO = "ABC"
UTC = timezone.utc
# (coleta, letras, instante UTC): P3 termina às 23h30 de 09/03 em Belém, que já é 10/03 em UTC
PARTIDAS = [
    ("C1", "ABC", datetime(2026, 3, 2, 18, 0, tzinfo=UTC)),
    ("C1", "BBD", datetime(2026, 3, 4, 18, 0, tzinfo=UTC)),
    ("C1", "BAD", datetime(2026, 3, 10, 2, 30, tzinfo=UTC)),
    ("C2", "ACC", datetime(2026, 3, 10, 18, 0, tzinfo=UTC)),
    ("C2", "BBA", datetime(2026, 3, 23, 18, 0, tzinfo=UTC)),
]


def monta(app, nome="Letramento", partidas=PARTIDAS, codigos=("C1", "C2")):
    c = app.extensions["container"]
    raiz = db.session.query(Usuario).filter_by(raiz=True).one()
    grupos = {n: db.session.query(Grupo).filter_by(nome=n).first() or Grupo(nome=n) for n in ("Segurança", "Tecnologia")}
    campus = {n: db.session.query(Campus).filter_by(nome=n).first() or Campus(nome=n) for n in ("Belém", "Paragominas")}
    cursos = {n: db.session.query(Curso).filter_by(nome=n).first() or Curso(nome=n) for n in ("Pedagogia", "Agronomia")}
    db.session.add_all([*grupos.values(), *campus.values(), *cursos.values()])
    db.session.commit()
    q = c.questionarios.criar(raiz, nome)
    perguntas = []
    for i, grupo in enumerate(("Segurança", "Segurança", "Tecnologia")):
        perguntas.append(c.perguntas.criar(raiz, q.id, DadosPergunta(
            texto=f"Enunciado {i + 1}?", titulo=f"Tema {i + 1}", grupo_id=grupos[grupo].id,
            alternativas=[DadosAlternativa(f"Alt {'ABCD'[a]}", 'ABCD'[a] == GABARITO[i], None, None) for a in range(4)])))
    colecoes = {}
    for chave, codigo, (cam, cur, per) in zip(("C1", "C2"), codigos, (("Belém", "Pedagogia", 1), ("Paragominas", "Agronomia", 2))):
        colecoes[chave] = Coleta(codigo=codigo, questionario_id=q.id, campus=campus[cam], curso=cursos[cur], ano=2026,
                                 periodo=per, data_inicio=date(2026, 3, 1), data_fim=date(2026, 3, 31))
    db.session.add_all(colecoes.values())
    db.session.commit()
    for n, (chave, letras, quando) in enumerate(partidas, 1):
        pt = Partida(coleta=colecoes[chave], finalizada_em=quando, total_perguntas=3,
                     total_acertos=sum(1 for i, l in enumerate(letras) if l == GABARITO[i]))
        db.session.add(pt)
        for i, letra in enumerate(letras):
            alt = db.session.query(Alternativa).filter_by(pergunta_id=perguntas[i].id, letra=letra).one()
            db.session.add(Resposta(partida=pt, pergunta=perguntas[i], alternativa=alt, acertou=alt.correta, ordem=i + 1,
                                    tempo_ms=1000 * n if i == 0 else 2000,
                                    pergunta_numero=perguntas[i].numero, pergunta_titulo=perguntas[i].titulo,
                                    grupo_nome=perguntas[i].grupo.nome, alternativa_letra=letra))
    db.session.commit()
    return q.id, colecoes


@pytest.fixture
def dash(web):
    cria_mundo(web)
    with web.app_context():
        web.extensions["container"].dashboard.relogio = lambda: datetime(2026, 3, 24, 15, 0, tzinfo=UTC)
        qid, colecoes = monta(web, codigos=("AAAAA", "BBBBB"))
        ids = {"q": qid, "campus": {c.campus.nome: c.campus_id for c in colecoes.values()},
               "curso": {c.curso.nome: c.curso_id for c in colecoes.values()}}
    cli = logado(web, "comum1")
    def get(caminho, **params):
        params.setdefault("questionario", ids["q"])
        r = cli.get(f"{BASE}/{caminho}", query_string=params)
        return r
    get.ids, get.app, get.cli = ids, web, cli
    return get


def j(r):
    assert r.status_code == 200, r.get_data(as_text=True)
    return r.get_json()


# ---- números -----------------------------------------------------------------------------------
def test_resumo_confere_com_a_contagem_manual(dash):
    r = j(dash("resumo"))
    assert (r["respondentes"], r["respostas"], r["acertos"], r["erros"]) == (5, 15, 7, 8)
    assert (r["pct_acerto"], r["pct_erro"]) == (46.7, 53.3)
    assert r["tempo_mediano_ms"] == 2000      # 15 tempos: 5 de Q1 (1..5 s) e 10 de 2 s


def test_resumo_com_filtro_traz_o_geral_sem_filtro_para_comparar(dash):
    r = j(dash("resumo", campus=dash.ids["campus"]["Belém"]))
    assert (r["respondentes"], r["respostas"], r["acertos"]) == (3, 9, 4)
    assert r["geral"]["respostas"] == 15 and r["geral"]["pct_erro"] == 53.3


def test_questoes_ordenadas_por_erro_com_desempate(dash):
    itens = j(dash("questoes"))["itens"]
    assert [(i["numero"], i["pct_erro"], i["respostas"]) for i in itens] == [(1, 60.0, 5), (3, 60.0, 5), (2, 40.0, 5)]
    assert itens[0]["grupo"] == "Segurança" and itens[0]["titulo"] == "Tema 1"
    assert itens[0]["tempo_mediano_ms"] == 3000


def test_questoes_menor_erro_e_limite(dash):
    assert [i["numero"] for i in j(dash("questoes", ordem="acerto"))["itens"]] == [2, 3, 1]
    r = j(dash("questoes", limite=1))
    assert r["total"] == 3 and len(r["itens"]) == 1


def test_grupos(dash):
    itens = j(dash("grupos"))["itens"]
    assert [(i["rotulo"], i["respostas"], i["erros"], i["pct_erro"]) for i in itens] == [
        ("Tecnologia", 5, 3, 60.0), ("Segurança", 10, 5, 50.0)]


def test_comparativo_por_campus_e_media_de_referencia(dash):
    r = j(dash("comparativo", dim="campus"))
    assert [(i["rotulo"], i["respostas"], i["pct_erro"]) for i in r["itens"]] == [("Belém", 9, 55.6), ("Paragominas", 6, 50.0)]
    assert r["media_pct_erro"] == 53.3


def test_comparativo_por_periodo_e_ano(dash):
    assert [i["rotulo"] for i in j(dash("comparativo", dim="periodo"))["itens"]] == ["1º período", "2º período"]
    assert [i["rotulo"] for i in j(dash("comparativo", dim="ano"))["itens"]] == ["2026"]


def test_heatmap_grupo_por_curso(dash):
    r = j(dash("heatmap", dim="curso"))
    celulas = {(c["grupo"], c["rotulo"]): (c["respostas"], c["pct_erro"]) for c in r["celulas"]}
    # Segurança em Pedagogia: P1..P3 em Q1,Q2 = 6 respostas, acertos 2+2... P1 2, P2 1, P3 0 = 3 -> erro 50,0
    assert celulas[("Segurança", "Pedagogia")] == (6, 50.0)
    assert celulas[("Tecnologia", "Pedagogia")] == (3, 66.7)
    assert celulas[("Segurança", "Agronomia")] == (4, 50.0)
    assert celulas[("Tecnologia", "Agronomia")] == (2, 50.0)
    assert r["grupos"] == ["Segurança", "Tecnologia"] and [c["rotulo"] for c in r["colunas"]] == ["Agronomia", "Pedagogia"]


def test_detalhe_da_questao_distribui_as_alternativas(dash):
    r = j(dash("questao/1"))
    assert (r["respostas"], r["pct_erro"], r["enunciado"], r["grupo"]) == (5, 60.0, "Enunciado 1?", "Segurança")
    alts = {a["letra"]: a for a in r["alternativas"]}
    assert [alts[l]["escolhas"] for l in "ABCD"] == [2, 3, 0, 0]
    assert alts["A"]["correta"] and not alts["B"]["correta"] and alts["B"]["pct"] == 60.0 and alts["C"]["pct"] == 0.0


def test_detalhe_respeita_os_demais_filtros(dash):
    r = j(dash("questao/1", campus=dash.ids["campus"]["Paragominas"]))
    assert r["respostas"] == 2 and [a["escolhas"] for a in r["alternativas"]] == [1, 1, 0, 0]


def test_evolucao_por_semana_usa_o_dia_local_e_preenche_lacunas(dash):
    r = j(dash("evolucao"))
    assert r["total"] == 5
    assert [(p["inicio"], p["partidas"]) for p in r["pontos"]] == [
        ("2026-03-02", 2), ("2026-03-09", 2), ("2026-03-16", 0), ("2026-03-23", 1)]


def test_evolucao_por_dia(dash):
    pontos = j(dash("evolucao", passo="dia"))["pontos"]
    por_dia = {p["inicio"]: p["partidas"] for p in pontos}
    assert len(pontos) == 22 and por_dia["2026-03-09"] == 1 and por_dia["2026-03-10"] == 1 and por_dia["2026-03-11"] == 0


# ---- filtros -----------------------------------------------------------------------------------
def test_intervalo_de_datas_e_inclusivo_no_fuso_local(dash):
    assert j(dash("resumo", ate="2026-03-09"))["respondentes"] == 3     # P1, P2 e P3 (23h30 de Belém)
    assert j(dash("resumo", de="2026-03-09"))["respondentes"] == 3      # P3, P4 e P5
    assert j(dash("resumo", de="2026-03-04", ate="2026-03-09"))["respondentes"] == 2


def test_ultimos_dias_conta_o_dia_de_hoje(dash):
    # hoje = 24/03: 7 dias = de 18/03 a 24/03 -> só P5 (23/03)
    assert j(dash("resumo", dias=7))["respondentes"] == 1
    assert j(dash("resumo", dias=30))["respondentes"] == 5


def test_filtros_combinam_e_aceitam_lista(dash):
    ids = dash.ids
    assert j(dash("resumo", campus=f"{ids['campus']['Belém']},{ids['campus']['Paragominas']}"))["respostas"] == 15
    assert j(dash("resumo", campus=ids["campus"]["Belém"], periodo=2))["respostas"] == 0
    assert j(dash("resumo", coleta="aaaaa"))["respondentes"] == 3       # o código não diferencia maiúsculas
    assert j(dash("resumo", grupo="Tecnologia"))["respostas"] == 5
    assert j(dash("resumo", questao="1,2"))["respostas"] == 10
    assert j(dash("resumo", ano=2025))["respostas"] == 0


def test_filtro_cruzado_o_grafico_nao_ignora_o_proprio_item(dash):
    # com a questão 1 selecionada, o ranking de questões continua mostrando as três...
    assert [i["numero"] for i in j(dash("questoes", questao=1))["itens"]] == [1, 3, 2]
    # ...mas os grupos, os KPIs e a tabela já refletem só a questão 1
    assert [(i["rotulo"], i["respostas"]) for i in j(dash("grupos", questao=1))["itens"]] == [("Segurança", 5)]
    assert j(dash("resumo", questao=1))["respostas"] == 5
    # o comparativo por campus ignora o filtro de campus, mas respeita os demais
    r = j(dash("comparativo", dim="campus", campus=dash.ids["campus"]["Belém"], ano=2026))
    assert [i["rotulo"] for i in r["itens"]] == ["Belém", "Paragominas"]
    assert j(dash("comparativo", dim="campus", periodo=1))["itens"][0]["respostas"] == 9
    assert len(j(dash("comparativo", dim="campus", periodo=1))["itens"]) == 1


def test_o_heatmap_ignora_o_filtro_de_grupo_e_o_da_dimensao(dash):
    r = j(dash("heatmap", dim="campus", grupo="Tecnologia", campus=dash.ids["campus"]["Belém"]))
    assert len(r["celulas"]) == 4


def test_nada_vaza_entre_questionarios(dash):
    with dash.app.app_context():
        outro, _ = monta(dash.app, nome="Outro", partidas=PARTIDAS[:1], codigos=("DDDDD", "EEEEE"))
    assert j(dash("resumo"))["respostas"] == 15
    assert j(dash("resumo", questionario=outro))["respostas"] == 3
    cartoes = {c["nome"]: c for c in j(dash("questionarios"))["itens"]}
    assert cartoes["Letramento"]["n_partidas"] == 5 and cartoes["Outro"]["n_partidas"] == 1
    assert cartoes["Letramento"]["estado"] == "travado"


def test_questionario_sem_respostas_devolve_zeros_e_nulos(dash):
    with dash.app.app_context():
        c = dash.app.extensions["container"]
        raiz = db.session.query(Usuario).filter_by(raiz=True).one()
        vazio = c.questionarios.criar(raiz, "Vazio").id
    r = j(dash("resumo", questionario=vazio))
    assert (r["respondentes"], r["respostas"], r["pct_erro"], r["tempo_mediano_ms"]) == (0, 0, None, None)
    assert j(dash("questoes", questionario=vazio)) == {"total": 0, "itens": []}
    assert j(dash("evolucao", questionario=vazio))["pontos"] == []
    assert j(dash("heatmap", dim="campus", questionario=vazio))["celulas"] == []


def test_opcoes_listam_so_o_que_existe_no_questionario(dash):
    o = j(dash("opcoes"))
    assert o["ano"] == [2026] and [x["nome"] for x in o["campus"]] == ["Belém", "Paragominas"]
    assert [x["codigo"] for x in o["coletas"]] == ["AAAAA", "BBBBB"] and o["grupo"] == ["Segurança", "Tecnologia"]
    assert [q["numero"] for q in o["questao"]] == [1, 2, 3] and o["questionario"]["estado"] == "travado"


# ---- tabela e CSV ------------------------------------------------------------------------------
def test_tabela_por_questao_com_totais(dash):
    t = j(dash("tabela", aba="questao"))
    assert [(i["numero"], i["respostas"], i["acertos"], i["erros"]) for i in t["itens"]] == [(1, 5, 2, 3), (2, 5, 3, 2), (3, 5, 2, 3)]
    assert (t["totais"]["respondentes"], t["totais"]["respostas"], t["totais"]["acertos"], t["totais"]["erros"]) == (5, 15, 7, 8)


@pytest.mark.parametrize("aba,rotulos", [
    ("grupo", ["Segurança", "Tecnologia"]), ("campus", ["Belém", "Paragominas"]), ("curso", ["Agronomia", "Pedagogia"]),
    ("ano", ["2026"]), ("periodo", ["1º período", "2º período"]), ("coleta", ["AAAAA", "BBBBB"])])
def test_tabela_em_todas_as_abas_fecha_com_o_total(dash, aba, rotulos):
    t = j(dash("tabela", aba=aba))
    assert [i["rotulo"] for i in t["itens"]] == rotulos
    assert sum(i["respostas"] for i in t["itens"]) == t["totais"]["respostas"] == 15
    assert sum(i["acertos"] for i in t["itens"]) == t["totais"]["acertos"] == 7


def test_a_tabela_aplica_o_filtro_por_inteiro(dash):
    t = j(dash("tabela", aba="questao", questao=1))
    assert [i["numero"] for i in t["itens"]] == [1] and t["totais"]["respostas"] == 5


def test_csv_do_recorte(dash):
    r = dash("export.csv", aba="questao", campus=dash.ids["campus"]["Belém"])
    assert r.status_code == 200 and r.mimetype == "text/csv" and "attachment" in r.headers["Content-Disposition"]
    bruto = r.get_data(as_text=True)
    assert bruto.startswith("﻿")
    linhas = list(csv.reader(io.StringIO(bruto.lstrip("﻿")), delimiter=";"))
    assert linhas[0] == ["Questão", "Grupo", "Respondentes", "Respostas", "Acertos", "Erros", "% acerto", "% erro", "Tempo mediano (s)"]
    assert linhas[1][:2] == ["Q1 · Tema 1", "Segurança"] and linhas[1][3:6] == ["3", "1", "2"] and linhas[1][7] == "66,7"
    assert linhas[-1][0] == "Total" and linhas[-1][2:6] == ["3", "9", "4", "5"] and len(linhas) == 5


def test_csv_neutraliza_formulas():
    assert _seguro("=1+1") == "'=1+1" and _seguro("@x") == "'@x" and _seguro("-2") == "'-2" and _seguro("Belém") == "Belém"
    assert _seguro(None) == ""


# ---- erros e acesso ----------------------------------------------------------------------------
def test_sem_login_e_401_em_json(web):
    cli = web.test_client()
    for caminho in ("resumo", "questionarios", "export.csv", "questao/1"):
        r = cli.get(f"{BASE}/{caminho}?questionario=1")
        assert r.status_code == 401 and r.get_json()["erro"]["motivo"] == "nao_autenticado"


def test_qualquer_usuario_logado_acessa(dash, web):
    for login in ("comum2", "promo1", "raiz"):
        assert logado(web, login).get(f"{BASE}/resumo", query_string={"questionario": dash.ids["q"]}).status_code == 200


@pytest.mark.parametrize("caminho,params,campo", [
    ("resumo", {"questionario": ""}, "questionario"), ("resumo", {"questionario": "abc"}, "questionario"),
    ("resumo", {"campus": "x"}, "campus"), ("resumo", {"de": "09/03/2026"}, "de"),
    ("resumo", {"de": "2026-03-10", "ate": "2026-03-01"}, "de"), ("resumo", {"dias": "0"}, "dias"),
    ("comparativo", {}, "dim"), ("comparativo", {"dim": "grupo"}, "dim"), ("heatmap", {"dim": "x"}, "dim"),
    ("questoes", {"ordem": "x"}, "ordem"), ("questoes", {"limite": "0"}, "limite"),
    ("evolucao", {"passo": "mes"}, "passo"), ("tabela", {"aba": "x"}, "aba"), ("resumo", {"campus": ",".join(map(str, range(300)))}, "campus")])
def test_parametros_invalidos_sao_422(dash, caminho, params, campo):
    r = dash(caminho, **({"questionario": dash.ids["q"]} | params))
    assert r.status_code == 422 and r.get_json()["erro"]["detalhes"]["campo"] == campo


def test_questionario_ou_questao_inexistente_e_404(dash):
    assert dash("resumo", questionario=99999).status_code == 404
    assert dash("questao/99").status_code == 404


def test_respostas_nao_sao_armazenadas_em_cache(dash):
    assert dash("resumo").headers["Cache-Control"] == "no-store"
    assert dash("export.csv").headers["Cache-Control"] == "no-store"


def test_apos_trocar_o_gabarito_os_acertos_do_dashboard_acompanham(dash):
    """O dashboard lê `acertou`, que o servidor recalcula na troca de gabarito (Fase 3)."""
    with dash.app.app_context():
        c = dash.app.extensions["container"]
        raiz = db.session.query(Usuario).filter_by(raiz=True).one()
        p1 = [p for p in c.questionarios.obter(dash.ids["q"]).perguntas if p.numero == 1][0]
        c.perguntas.trocar_gabarito(raiz, dash.ids["q"], p1.id, "B")
    q1 = [i for i in j(dash("questoes"))["itens"] if i["numero"] == 1][0]
    assert (q1["acertos"], q1["pct_erro"]) == (3, 40.0)


# ---- limites de data no fuso local (Belém = UTC−3) -----------------------------------------------
def test_o_limite_da_meia_noite_local_entra_no_dia_certo(web):
    cria_mundo(web)
    with web.app_context():
        web.extensions["container"].dashboard.relogio = lambda: datetime(2026, 3, 24, 15, 0, tzinfo=UTC)
        qid, _ = monta(web, partidas=[
            ("C1", "ABC", datetime(2026, 3, 9, 2, 59, 59, tzinfo=UTC)),     # 23h59min59s de 08/03 em Belém
            ("C1", "ABC", datetime(2026, 3, 9, 3, 0, 0, tzinfo=UTC)),       # 00h00 de 09/03 em Belém
            ("C1", "ABC", datetime(2026, 3, 22, 20, 0, tzinfo=UTC))],       # 22/03
            codigos=("AAAAA", "BBBBB"))
    cli = logado(web, "comum1")
    n = lambda **p: cli.get(f"{BASE}/resumo", query_string={"questionario": qid, **p}).get_json()["respondentes"]  # noqa: E731
    assert n(de="2026-03-09", ate="2026-03-09") == 1 and n(ate="2026-03-08") == 1 and n(de="2026-03-09") == 2
    assert n(dias=2) == 0 and n(dias=3) == 1       # hoje (24/03) conta: 2 dias = 23 e 24/03
