"""API pública do jogo, ponta a ponta pelo cliente HTTP: iniciar a coleta e gravar a partida."""
import json
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from app.extensions import db
from app.models import Alternativa, Campus, Coleta, Curso, Grupo, Partida, Pergunta, Resposta, TentativaFalha, Usuario
from app.repositories.partidas import PartidaRepo
from app.services import gabarito
from app.services.perguntas import DadosAlternativa, DadosPergunta

from conftest import cria_mundo, web  # noqa: F401

AGORA = datetime(2026, 3, 10, 18, 0, tzinfo=timezone.utc)          # 10/03/2026, 15h em Belém
VETOR = ("sal-de-teste", 7, 3, "B", "bb081bac12b82d641a0b581b6a241a80159188fb93a490b9cc80b701c0bc2030")


@pytest.fixture
def jogo(web):
    """Questionário com 3 perguntas (gabaritos C, A e B) e uma coleta aberta."""
    ids = cria_mundo(web)
    with web.app_context():
        c = web.extensions["container"]
        c.coletas.relogio = lambda: AGORA
        raiz = db.session.get(Usuario, ids["raiz"])
        grupos = [Grupo(nome="Segurança Digital"), Grupo(nome="Tecnologia")]
        campus, curso = Campus(nome="Belém"), Curso(nome="Pedagogia")
        db.session.add_all([*grupos, campus, curso])
        db.session.commit()
        q = c.questionarios.criar(raiz, "Letramento Digital")
        q.orientacoes = "# Bem-vindo\n- Boa sorte, {{totalPerguntas}} perguntas."
        gabaritos = [2, 0, 1]
        for i, correta in enumerate(gabaritos):
            c.perguntas.criar(raiz, q.id, DadosPergunta(
                texto=f"Enunciado {i + 1}?", titulo=f"Tema {i + 1}", grupo_id=grupos[i % 2].id, autoajuda="Uma dica." if i == 0 else None,
                alternativas=[DadosAlternativa(f"Alt {'ABCD'[a]}", a == correta, "Certo!" if a == correta else None,
                                               None if a == correta else "Errado.") for a in range(4)]))
        coleta = c.coletas.criar(raiz, __import__("app.services.coletas", fromlist=["DadosColeta"]).DadosColeta(
            q.id, campus.id, curso.id, 2026, 1, date(2026, 3, 1), date(2026, 3, 31)))
        return dict(q=q.id, coleta=coleta.id, codigo=coleta.codigo, sal=c.settings.gabarito_sal)


def post(cliente, rota, corpo, ip="10.0.0.1", **kw):
    return cliente.post(rota, data=json.dumps(corpo), content_type="application/json", environ_overrides={"REMOTE_ADDR": ip}, **kw)


def iniciar(cliente, codigo, **kw):
    return post(cliente, "/api/coleta/iniciar", {"codigo": codigo}, **kw)


def partida_ok(jogo, escolhas="CAB", **extra):
    """Corpo de uma partida completa: `escolhas` = a letra escolhida em cada pergunta, em ordem."""
    return {"uuid": str(uuid.uuid4()), "codigo": jogo["codigo"], "respostas": [
        {"pergunta": i + 1, "alternativa": letra, "tempo_ms": 4000 + i * 100, "ordem": i + 1} for i, letra in enumerate(escolhas)], **extra}


def mudar_coleta(web, jogo, **campos):
    with web.app_context():
        c = db.session.get(Coleta, jogo["coleta"])
        for k, v in campos.items():
            setattr(c, k, v)
        db.session.commit()


# ---- vetor de paridade com o JavaScript ----------------------------------------------------------
def test_token_do_gabarito_tem_o_vetor_conhecido():
    sal, qid, numero, letra, esperado = VETOR
    assert gabarito.token(sal, qid, numero, letra) == esperado             # o jogo (JS) calcula exatamente o mesmo valor


def test_token_muda_com_qualquer_parte():
    base = gabarito.token("s", 1, 1, "A")
    assert len({base, gabarito.token("t", 1, 1, "A"), gabarito.token("s", 2, 1, "A"), gabarito.token("s", 1, 2, "A"), gabarito.token("s", 1, 1, "B")}) == 5


# ---- iniciar: sucesso --------------------------------------------------------------------------------
def test_iniciar_devolve_o_questionario_sem_revelar_o_gabarito(web, jogo):
    r = iniciar(web.test_client(), jogo["codigo"])
    assert r.status_code == 200 and r.headers["Cache-Control"] == "no-store" and "Set-Cookie" not in r.headers
    d = r.get_json()
    assert d["coleta"] == {"codigo": jogo["codigo"]}
    q = d["questionario"]
    assert (q["id"], q["nome"], q["sal"]) == (jogo["q"], "Letramento Digital", jogo["sal"]) and "{{totalPerguntas}}" in q["orientacoes"]
    assert [p["numero"] for p in q["perguntas"]] == [1, 2, 3] and [p["titulo"] for p in q["perguntas"]] == ["Tema 1", "Tema 2", "Tema 3"]
    assert q["perguntas"][0]["grupo"] == "Segurança Digital" and q["perguntas"][1]["grupo"] == "Tecnologia"
    assert q["perguntas"][0]["autoajuda"] == "Uma dica." and q["perguntas"][1]["autoajuda"] is None
    assert [a["letra"] for a in q["perguntas"][0]["alternativas"]] == list("ABCD")
    # NENHUM campo "correta" em lugar algum do JSON
    bruto = r.get_data(as_text=True).lower()
    assert '"correta"' not in bruto and '"correct"' not in bruto
    assert set(q["perguntas"][0]["alternativas"][0]) == {"letra", "texto", "texto_acerto", "texto_erro"}


def test_token_correta_aponta_a_alternativa_certa(web, jogo):
    q = iniciar(web.test_client(), jogo["codigo"]).get_json()["questionario"]
    for pergunta, certa in zip(q["perguntas"], "CAB"):
        tokens = {a["letra"]: gabarito.token(q["sal"], q["id"], pergunta["numero"], a["letra"]) for a in pergunta["alternativas"]}
        assert [l for l, t in tokens.items() if t == pergunta["token_correta"]] == [certa]


def test_o_codigo_aceita_minusculas_e_espacos(web, jogo):
    assert iniciar(web.test_client(), f"  {jogo['codigo'].lower()} ").status_code == 200


def test_valido_nao_conta_para_o_limite(web, jogo):
    c = web.test_client()
    for _ in range(25):
        assert iniciar(c, jogo["codigo"]).status_code == 200
    with web.app_context():
        assert db.session.query(TentativaFalha).count() == 0


def test_api_nao_exige_csrf_nem_cookie(web, jogo):
    web.config["WTF_CSRF_ENABLED"] = True
    r = iniciar(web.test_client(), jogo["codigo"])
    assert r.status_code == 200 and "Set-Cookie" not in r.headers


# ---- iniciar: falhas ----------------------------------------------------------------------------------
@pytest.mark.parametrize("codigo", ["ZZZZZ", "abc", "", "ABCDEF", "12345", "AB CD", None, 12345, ["ABCDE"], {"a": 1}])
def test_codigo_inexistente_ou_invalido(web, jogo, codigo):
    r = iniciar(web.test_client(), codigo)
    assert r.status_code == 404 and r.get_json()["erro"]["motivo"] == "inexistente"
    assert "Código não encontrado" in r.get_json()["erro"]["mensagem"]


@pytest.mark.parametrize("mudanca,motivo,trecho", [
    ({"ativo": False}, "inativa", "desativada"),
    ({"data_inicio": date(2026, 4, 1), "data_fim": date(2026, 4, 30)}, "fora_do_prazo", "ainda não começou"),
    ({"data_inicio": date(2026, 2, 1), "data_fim": date(2026, 3, 9)}, "fora_do_prazo", "prazo desta coleta já terminou"),
])
def test_coleta_que_nao_aceita_alunos(web, jogo, mudanca, motivo, trecho):
    mudar_coleta(web, jogo, **mudanca)
    r = iniciar(web.test_client(), jogo["codigo"])
    assert r.status_code == 410 and r.get_json()["erro"]["motivo"] == motivo and trecho in r.get_json()["erro"]["mensagem"]


def test_ultimo_dia_do_prazo_ainda_aceita(web, jogo):
    mudar_coleta(web, jogo, data_inicio=date(2026, 3, 1), data_fim=date(2026, 3, 10))      # hoje é 10/03 em Belém
    assert iniciar(web.test_client(), jogo["codigo"]).status_code == 200


@pytest.mark.parametrize("corpo,tipo", [("nao e json", "application/json"), ('{"codigo": "A"}', "text/plain"), ("[1,2]", "application/json"), ("", "application/json")])
def test_corpo_que_nao_e_um_objeto_json(web, jogo, corpo, tipo):
    r = web.test_client().post("/api/coleta/iniciar", data=corpo, content_type=tipo)
    assert r.status_code == 422 and r.get_json()["erro"]["motivo"] == "invalido"


def test_corpo_grande_demais(web, jogo):
    r = web.test_client().post("/api/partidas", data=json.dumps({"x": "a" * 70000}), content_type="application/json")
    assert r.status_code == 413 and r.get_json()["erro"]["motivo"] == "corpo_grande"


def test_metodo_errado(web, jogo):
    assert web.test_client().get("/api/coleta/iniciar").status_code == 405


# ---- limite por IP ---------------------------------------------------------------------------------------
def test_dez_codigos_errados_bloqueiam_o_ip_ate_para_o_codigo_certo(web, jogo):
    c = web.test_client()
    for _ in range(10):
        assert iniciar(c, "ZZZZZ", ip="10.9.9.9").status_code == 404
    r = iniciar(c, jogo["codigo"], ip="10.9.9.9")                                  # o código certo também é barrado
    assert r.status_code == 429 and r.get_json()["erro"]["motivo"] == "limite_excedido"
    assert 290 <= int(r.headers["Retry-After"]) <= 300 and r.get_json()["erro"]["detalhes"]["espera_seg"] == int(r.headers["Retry-After"])
    assert iniciar(c, jogo["codigo"], ip="10.7.7.7").status_code == 200            # outro IP não é afetado


def test_pedidos_durante_o_bloqueio_nao_o_prolongam(web, jogo):
    c = web.test_client()
    for _ in range(10):
        iniciar(c, "ZZZZZ", ip="10.9.9.9")
    for _ in range(5):
        assert iniciar(c, "ZZZZZ", ip="10.9.9.9").status_code == 429
    with web.app_context():
        assert db.session.query(TentativaFalha).filter_by(tipo="codigo").count() == 10


def test_o_ip_e_liberado_depois_do_bloqueio(web, jogo):
    c = web.test_client()
    for _ in range(10):
        iniciar(c, "ZZZZZ", ip="10.9.9.9")
    with web.app_context():
        lim = web.extensions["container"].jogo.limitador
        lim.relogio = lambda: datetime.now(timezone.utc) + timedelta(seconds=301)
    assert iniciar(c, jogo["codigo"], ip="10.9.9.9").status_code == 200


def test_o_ip_vem_do_proxy_confiavel(web, jogo):
    from app import create_app
    from app.config import Settings
    app = create_app(Settings.from_env({"APP_ENV": "testing", "PROXIES_CONFIAVEIS": "1"}))
    with app.app_context():
        db.create_all()
    for _ in range(10):
        app.test_client().post("/api/coleta/iniciar", data=json.dumps({"codigo": "ZZZZZ"}), content_type="application/json",
                               headers={"X-Forwarded-For": "200.1.1.1"})
    with app.app_context():
        assert [t.chave for t in db.session.query(TentativaFalha)] == ["200.1.1.1"] * 10          # o IP real, não o do proxy


# ---- partidas: sucesso --------------------------------------------------------------------------------------
def test_gravar_partida_completa(web, jogo):
    corpo = partida_ok(jogo, "CBA")                          # acerta a 1ª, erra a 2ª e a 3ª
    r = post(web.test_client(), "/api/partidas", corpo)
    assert r.status_code == 201 and r.get_json() == {"salvo": True, "duplicada": False, "acertos": 1, "total": 3}
    with web.app_context():
        p = db.session.get(Partida, uuid.UUID(corpo["uuid"]))
        assert (p.coleta_id, p.total_acertos, p.total_perguntas) == (jogo["coleta"], 1, 3) and p.finalizada_em.tzinfo is not None
        rs = sorted(p.respostas, key=lambda x: x.ordem)
        assert [(r.pergunta_numero, r.alternativa_letra, r.acertou, r.ordem, r.tempo_ms) for r in rs] == \
               [(1, "C", True, 1, 4000), (2, "B", False, 2, 4100), (3, "A", False, 3, 4200)]
        assert [(r.pergunta_titulo, r.grupo_nome) for r in rs] == [("Tema 1", "Segurança Digital"), ("Tema 2", "Tecnologia"), ("Tema 3", "Segurança Digital")]


def test_o_servidor_ignora_o_acerto_que_o_cliente_diz(web, jogo):
    corpo = partida_ok(jogo, "AAA")                            # só a 2ª está certa de verdade
    for r in corpo["respostas"]:
        r["acertou"] = True                                    # o cliente "mente"
    corpo["xp_final"], corpo["total_acertos"] = 9999, 3
    r = post(web.test_client(), "/api/partidas", corpo)
    assert r.status_code == 201 and r.get_json()["acertos"] == 1
    with web.app_context():
        assert [x.acertou for x in sorted(db.session.query(Resposta), key=lambda x: x.ordem)] == [False, True, False]


def test_letra_em_minuscula_e_ordem_embaralhada_sao_aceitas(web, jogo):
    corpo = partida_ok(jogo, "cab")
    corpo["respostas"].reverse()
    assert post(web.test_client(), "/api/partidas", corpo).get_json()["acertos"] == 3


def test_reenviar_a_mesma_partida_e_idempotente(web, jogo):
    corpo = partida_ok(jogo)
    c = web.test_client()
    assert post(c, "/api/partidas", corpo).status_code == 201
    r = post(c, "/api/partidas", corpo)                                   # a rede falhou e o jogo reenviou
    assert r.status_code == 200 and r.get_json()["duplicada"] is True
    with web.app_context():
        assert db.session.query(Partida).count() == 1 and db.session.query(Resposta).count() == 3


def test_mesmo_uuid_em_outra_coleta_e_conflito(web, jogo):
    corpo = partida_ok(jogo)
    post(web.test_client(), "/api/partidas", corpo)
    with web.app_context():
        c = web.extensions["container"]
        raiz = db.session.query(Usuario).filter_by(raiz=True).one()
        from app.services.coletas import DadosColeta
        outra = c.coletas.criar(raiz, DadosColeta(jogo["q"], db.session.query(Campus).first().id, db.session.query(Curso).first().id,
                                                  2026, 2, date(2026, 3, 1), date(2026, 3, 31)))
        codigo = outra.codigo
    r = post(web.test_client(), "/api/partidas", {**corpo, "codigo": codigo})
    assert r.status_code == 409 and r.get_json()["erro"]["motivo"] == "uuid_em_uso"


def test_corrida_com_o_mesmo_uuid_vira_sucesso_idempotente(web, jogo, monkeypatch):
    corpo = partida_ok(jogo)
    post(web.test_client(), "/api/partidas", corpo)
    chamadas = {"n": 0}
    original = PartidaRepo.por_id

    def por_id_cego_na_primeira(self, partida_id):          # a checagem prévia não enxerga a partida (a outra ainda não tinha gravado)
        chamadas["n"] += 1
        return None if chamadas["n"] == 1 else original(self, partida_id)

    monkeypatch.setattr(PartidaRepo, "por_id", por_id_cego_na_primeira)
    r = post(web.test_client(), "/api/partidas", corpo)      # o banco recusa o UUID repetido; o serviço trata como reenvio
    assert r.status_code == 200 and r.get_json()["duplicada"] is True
    with web.app_context():
        assert db.session.query(Partida).count() == 1


def test_gravar_a_partida_trava_o_questionario(web, jogo):
    with web.app_context():
        c = web.extensions["container"]
        assert c.questionarios.resumo(c.questionarios.obter(jogo["q"])).estado == "em coleta"
    post(web.test_client(), "/api/partidas", partida_ok(jogo))
    with web.app_context():
        assert c.questionarios.resumo(c.questionarios.obter(jogo["q"])).estado == "travado"


# ---- partidas: validação --------------------------------------------------------------------------------------
@pytest.mark.parametrize("mudanca,motivo", [
    ({"uuid": "isso-nao-e-uuid"}, "invalido"), ({"uuid": None}, "invalido"), ({"uuid": 12345}, "invalido"),
    ({"respostas": []}, "invalido"), ({"respostas": "x"}, "invalido"), ({"respostas": None}, "invalido"), ({"respostas": ["a", "b", "c"]}, "invalido"),
])
def test_corpo_invalido(web, jogo, mudanca, motivo):
    r = post(web.test_client(), "/api/partidas", {**partida_ok(jogo), **mudanca})
    assert r.status_code == 422 and r.get_json()["erro"]["motivo"] == motivo
    with web.app_context():
        assert db.session.query(Partida).count() == 0


def alterado(jogo, i, **campos):
    corpo = partida_ok(jogo)
    corpo["respostas"][i].update(campos)
    return corpo


@pytest.mark.parametrize("campos", [
    {"alternativa": "E"}, {"alternativa": ""}, {"alternativa": None}, {"alternativa": 1},
    {"tempo_ms": -1}, {"tempo_ms": 3_600_001}, {"tempo_ms": "rápido"}, {"tempo_ms": 1.5}, {"tempo_ms": True}, {"tempo_ms": None},
    {"ordem": 0}, {"ordem": 4}, {"ordem": "1"}, {"ordem": 2},                    # 2 repete a ordem da 2ª pergunta
])
def test_resposta_invalida_nao_grava_nada(web, jogo, campos):
    r = post(web.test_client(), "/api/partidas", alterado(jogo, 0, **campos))
    assert r.status_code == 422, (campos, r.get_json())
    with web.app_context():
        assert db.session.query(Partida).count() == 0 and db.session.query(Resposta).count() == 0


def test_pergunta_repetida_ou_desconhecida(web, jogo):
    r = post(web.test_client(), "/api/partidas", alterado(jogo, 1, pergunta=1))
    assert r.status_code == 422 and "mais de uma vez" in r.get_json()["erro"]["mensagem"]
    r = post(web.test_client(), "/api/partidas", alterado(jogo, 1, pergunta=99))
    assert r.status_code == 409 and r.get_json()["erro"]["motivo"] == "questionario_alterado"


def test_partida_incompleta_e_conflito(web, jogo):
    corpo = partida_ok(jogo)
    corpo["respostas"].pop()
    r = post(web.test_client(), "/api/partidas", corpo)
    assert r.status_code == 409 and r.get_json()["erro"]["motivo"] == "questionario_alterado"


def test_questionario_alterado_durante_a_partida(web, jogo):
    corpo = partida_ok(jogo)                       # o aluno começou com 3 perguntas...
    with web.app_context():                        # ...e o professor (em coleta, sem respostas) acrescentou uma 4ª
        c = web.extensions["container"]
        raiz = db.session.query(Usuario).filter_by(raiz=True).one()
        c.perguntas.criar(raiz, jogo["q"], DadosPergunta(texto="Nova?", titulo="Nova", grupo_id=db.session.query(Grupo).first().id,
                                                         alternativas=[DadosAlternativa("a", True), DadosAlternativa("b")]))
    r = post(web.test_client(), "/api/partidas", corpo)
    assert r.status_code == 409 and "mudou durante a partida" in r.get_json()["erro"]["mensagem"]


@pytest.mark.parametrize("mudanca", [{"ativo": False}, {"data_fim": date(2026, 3, 9)}, {"data_inicio": date(2026, 4, 1), "data_fim": date(2026, 4, 2)}])
def test_coleta_encerrada_ao_salvar(web, jogo, mudanca):
    mudar_coleta(web, jogo, **mudanca)
    r = post(web.test_client(), "/api/partidas", partida_ok(jogo))
    assert r.status_code == 410 and r.get_json()["erro"]["motivo"] == "coleta_encerrada"
    assert "suas respostas não foram salvas" in r.get_json()["erro"]["mensagem"]
    with web.app_context():
        assert db.session.query(Partida).count() == 0


def test_codigo_errado_ao_salvar_conta_para_o_limite(web, jogo):
    c = web.test_client()
    for _ in range(10):
        r = post(c, "/api/partidas", {**partida_ok(jogo), "codigo": "ZZZZZ"}, ip="10.8.8.8")
        assert r.status_code == 404 and r.get_json()["erro"]["motivo"] == "inexistente"
    assert post(c, "/api/partidas", partida_ok(jogo), ip="10.8.8.8").status_code == 429


def test_gabarito_trocado_muda_o_token_do_proximo_aluno(web, jogo):
    c = web.test_client()
    antes = iniciar(c, jogo["codigo"]).get_json()["questionario"]["perguntas"][0]["token_correta"]
    with web.app_context():
        ct = web.extensions["container"]
        raiz = db.session.query(Usuario).filter_by(raiz=True).one()
        p1 = db.session.query(Pergunta).filter_by(numero=1).one()
        ct.perguntas.trocar_gabarito(raiz, jogo["q"], p1.id, "D")
    depois = iniciar(c, jogo["codigo"]).get_json()["questionario"]["perguntas"][0]["token_correta"]
    assert antes != depois and depois == gabarito.token(jogo["sal"], jogo["q"], 1, "D")
    assert post(c, "/api/partidas", partida_ok(jogo, "DAB")).get_json()["acertos"] == 3      # e o servidor já usa o novo gabarito
