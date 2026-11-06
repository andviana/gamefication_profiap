"""Coletas: código, prazo no fuso, ano, duplicidade e travas de edição, direto no serviço."""
import logging
from datetime import date, datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.errors import Conflito, Duplicidade, Invalido, NaoEncontrado
from app.extensions import db
from app.models import Campus, Coleta, Curso, Grupo, Questionario, Usuario
from app.services.coletas import ALFABETO, DadosColeta, gera_codigo, situacao
from app.services.perguntas import DadosAlternativa, DadosPergunta

from conftest import cria_mundo, responde, web  # noqa: F401

# 15h de 10/03/2026 em Belém (UTC-3) = 18h UTC
AGORA = datetime(2026, 3, 10, 18, 0, tzinfo=timezone.utc)


@pytest.fixture
def ctx(web):
    ids = cria_mundo(web)
    with web.app_context():
        c = web.extensions["container"]
        c.coletas.relogio = lambda: AGORA
        raiz = db.session.get(Usuario, ids["raiz"])
        grupo = Grupo(nome="Tecnologia")
        campus, outro_campus, curso = Campus(nome="Belém"), Campus(nome="Paragominas"), Curso(nome="Pedagogia")
        db.session.add_all([grupo, campus, outro_campus, curso])
        db.session.commit()
        q = c.questionarios.criar(raiz, "Letramento Digital")
        c.perguntas.criar(raiz, q.id, DadosPergunta(texto="Enunciado?", titulo="Tema", grupo_id=grupo.id,
                                                    alternativas=[DadosAlternativa("a", True), DadosAlternativa("b")]))
        yield type("Ctx", (), dict(svc=c.coletas, q=c.questionarios, ator=raiz, qid=q.id, campus=campus.id, outro_campus=outro_campus.id,
                                   curso=curso.id, container=c, grupo=grupo.id))


def dados(ctx, **mudancas):
    base = dict(questionario_id=ctx.qid, campus_id=ctx.campus, curso_id=ctx.curso, ano=2026, periodo=1,
                data_inicio=date(2026, 3, 1), data_fim=date(2026, 3, 31))
    return DadosColeta(**{**base, **mudancas})


# ---- código ------------------------------------------------------------------------------------
def test_alfabeto_nao_tem_letras_ambiguas():
    assert len(ALFABETO) == 23 and not set("ILO") & set(ALFABETO) and ALFABETO.isalpha() and ALFABETO.isupper()


def test_gera_codigos_de_cinco_letras_validas():
    codigos = {gera_codigo() for _ in range(500)}
    assert len(codigos) > 490 and all(len(c) == 5 and set(c) <= set(ALFABETO) for c in codigos)


def test_criar_gera_o_codigo_e_a_coleta_nasce_ativa(ctx):
    c = ctx.svc.criar(ctx.ator, dados(ctx))
    assert len(c.codigo) == 5 and set(c.codigo) <= set(ALFABETO) and c.ativo is True
    assert ctx.svc.obter(c.id).codigo == c.codigo and ctx.svc.repo.por_codigo(c.codigo).id == c.id


def test_codigo_ja_existente_e_regerado(ctx):
    sequencia = iter(["AAAAA", "AAAAA", "AAAAA", "BBBBB"])
    ctx.svc.gerador = lambda: next(sequencia)
    primeira = ctx.svc.criar(ctx.ator, dados(ctx, periodo=1))
    segunda = ctx.svc.criar(ctx.ator, dados(ctx, periodo=2))         # AAAAA já existe: tenta de novo até BBBBB
    assert (primeira.codigo, segunda.codigo) == ("AAAAA", "BBBBB")


def test_corrida_na_geracao_do_codigo_o_banco_recusa_e_tenta_outro(ctx):
    ctx.svc.gerador = iter(["AAAAA", "AAAAA", "CCCCC"]).__next__
    ctx.svc.criar(ctx.ator, dados(ctx, periodo=1))
    ctx.svc.repo.codigo_existe = lambda codigo: False                 # a checagem prévia não vê o código (corrida)
    segunda = ctx.svc.criar(ctx.ator, dados(ctx, periodo=2))
    assert segunda.codigo == "CCCCC"                                  # o IntegrityError virou nova tentativa


def test_falha_se_nao_consegue_codigo_unico(ctx):
    ctx.svc.gerador = lambda: "AAAAA"
    ctx.svc.criar(ctx.ator, dados(ctx, periodo=1))
    with pytest.raises(Conflito, match="código único"):
        ctx.svc.criar(ctx.ator, dados(ctx, periodo=2))


# ---- tempo: prazo e ano no fuso configurado ----------------------------------------------------
def coleta_solta(inicio, fim, ativo=True):
    return Coleta(data_inicio=inicio, data_fim=fim, ativo=ativo)


@pytest.mark.parametrize("hoje,esperado", [
    (date(2026, 2, 28), "agendada"), (date(2026, 3, 1), "aberta"), (date(2026, 3, 15), "aberta"),
    (date(2026, 3, 31), "aberta"), (date(2026, 4, 1), "encerrada"),
])
def test_situacao_pelas_datas_inclusivas(hoje, esperado):
    assert situacao(coleta_solta(date(2026, 3, 1), date(2026, 3, 31)), hoje) == esperado


def test_desativada_vence_qualquer_prazo():
    assert situacao(coleta_solta(date(2026, 3, 1), date(2026, 3, 31), ativo=False), date(2026, 3, 15)) == "desativada"


def test_o_dia_e_o_do_fuso_e_nao_o_de_utc(ctx):
    # 31/03 02:30 UTC = 30/03 23:30 em Belém: a coleta que termina em 30/03 ainda está aberta
    ctx.svc.relogio = lambda: datetime(2026, 3, 31, 2, 30, tzinfo=timezone.utc)
    c = Coleta(data_inicio=date(2026, 3, 1), data_fim=date(2026, 3, 30), ativo=True)
    assert ctx.svc.hoje() == date(2026, 3, 30) and ctx.svc.situacao(c) == "aberta"
    # 31/03 03:00 UTC = 31/03 00:00 em Belém: acabou
    ctx.svc.relogio = lambda: datetime(2026, 3, 31, 3, 0, tzinfo=timezone.utc)
    assert ctx.svc.hoje() == date(2026, 3, 31) and ctx.svc.situacao(c) == "encerrada"


def test_anos_validos_acompanham_o_ano_no_fuso(ctx):
    assert ctx.svc.anos_validos() == [2025, 2026, 2027]
    ctx.svc.relogio = lambda: datetime(2027, 1, 1, 1, 0, tzinfo=timezone.utc)      # ainda 31/12/2026 em Belém
    assert ctx.svc.anos_validos() == [2025, 2026, 2027]
    ctx.svc.relogio = lambda: datetime(2027, 1, 1, 3, 0, tzinfo=timezone.utc)      # já 01/01/2027 em Belém
    assert ctx.svc.anos_validos() == [2026, 2027, 2028]


# ---- criar: validação -----------------------------------------------------------------------------
@pytest.mark.parametrize("mudanca,campo", [
    ({"ano": 2024}, "ano"), ({"ano": 2028}, "ano"), ({"periodo": 3}, "periodo"), ({"periodo": 0}, "periodo"),
    ({"data_inicio": None}, "data_inicio"), ({"data_fim": None}, "data_fim"),
    ({"data_inicio": date(2026, 4, 2), "data_fim": date(2026, 4, 1)}, "data_fim"),
    ({"questionario_id": 9999}, "questionario_id"), ({"questionario_id": 0}, "questionario_id"),
    ({"campus_id": 9999}, "campus_id"), ({"curso_id": 0}, "curso_id"),
])
def test_validacao_da_coleta(ctx, mudanca, campo):
    with pytest.raises(Invalido) as e:
        ctx.svc.criar(ctx.ator, dados(ctx, **mudanca))
    assert e.value.detalhes["campo"] == campo
    assert db.session.query(Coleta).count() == 0


def test_prazo_de_um_so_dia_e_valido(ctx):
    assert ctx.svc.criar(ctx.ator, dados(ctx, data_inicio=date(2026, 3, 10), data_fim=date(2026, 3, 10)))


def test_aceita_os_tres_anos(ctx):
    for i, ano in enumerate((2025, 2026, 2027)):
        assert ctx.svc.criar(ctx.ator, dados(ctx, ano=ano, periodo=1 + (i % 2), campus_id=ctx.campus if i < 2 else ctx.outro_campus))


def test_questionario_sem_perguntas_nao_abre_coleta(ctx):
    vazio = ctx.q.criar(ctx.ator, "Vazio")
    with pytest.raises(Invalido, match="ainda não tem perguntas") as e:
        ctx.svc.criar(ctx.ator, dados(ctx, questionario_id=vazio.id))
    assert e.value.detalhes["campo"] == "questionario_id"


def test_campus_ou_curso_inativo_nao_serve_para_coleta_nova(ctx):
    db.session.get(Campus, ctx.campus).ativo = False
    db.session.get(Curso, ctx.curso).ativo = False
    db.session.commit()
    for campo in ("campus_id", "curso_id"):
        with pytest.raises(Invalido, match="inativo") as e:
            ctx.svc.criar(ctx.ator, dados(ctx))
        assert e.value.detalhes["campo"] in ("campus_id", "curso_id")
        break


def test_criar_vincula_o_questionario_e_ele_passa_a_em_coleta(ctx):
    assert ctx.q.resumo(ctx.q.obter(ctx.qid)).estado == "rascunho"
    ctx.svc.criar(ctx.ator, dados(ctx))
    assert ctx.q.resumo(ctx.q.obter(ctx.qid)).estado == "em coleta"


# ---- duplicidade -----------------------------------------------------------------------------------
def test_duplicidade_avisa_mas_deixa_confirmar(ctx):
    primeira = ctx.svc.criar(ctx.ator, dados(ctx))
    with pytest.raises(Duplicidade) as e:
        ctx.svc.criar(ctx.ator, dados(ctx, data_inicio=date(2026, 5, 1), data_fim=date(2026, 5, 9)))
    assert [c.codigo for c in e.value.existentes] == [primeira.codigo]
    assert db.session.query(Coleta).count() == 1                                  # nada foi criado
    segunda = ctx.svc.criar(ctx.ator, dados(ctx), duplicidade_confirmada=True)
    assert segunda.codigo != primeira.codigo and db.session.query(Coleta).count() == 2


@pytest.mark.parametrize("mudanca", [{"periodo": 2}, {"ano": 2025}, {"campus_id": "outro"}])
def test_identidade_diferente_nao_e_duplicidade(ctx, mudanca):
    ctx.svc.criar(ctx.ator, dados(ctx))
    if mudanca.get("campus_id") == "outro":
        mudanca = {"campus_id": ctx.outro_campus}
    assert ctx.svc.criar(ctx.ator, dados(ctx, **mudanca))


def test_outro_questionario_nao_e_duplicidade(ctx):
    ctx.svc.criar(ctx.ator, dados(ctx))
    q2 = ctx.q.criar(ctx.ator, "Outro")
    ctx.container.perguntas.criar(ctx.ator, q2.id, DadosPergunta(texto="E?", titulo="T", grupo_id=ctx.grupo,
                                                                 alternativas=[DadosAlternativa("a", True), DadosAlternativa("b")]))
    assert ctx.svc.criar(ctx.ator, dados(ctx, questionario_id=q2.id))


# ---- editar ---------------------------------------------------------------------------------------
def test_antes_da_primeira_partida_tudo_pode_mudar_menos_o_codigo(ctx):
    c = ctx.svc.criar(ctx.ator, dados(ctx))
    codigo = c.codigo
    ctx.svc.editar(ctx.ator, c.id, dados(ctx, campus_id=ctx.outro_campus, periodo=2, ano=2027,
                                         data_inicio=date(2026, 8, 1), data_fim=date(2026, 8, 31)))
    c = ctx.svc.obter(c.id)
    assert (c.campus_id, c.periodo, c.ano, c.data_inicio, c.codigo) == (ctx.outro_campus, 2, 2027, date(2026, 8, 1), codigo)


def partida_em(ctx, coleta):
    q = db.session.get(Questionario, coleta.questionario_id)
    responde(coleta, [(p, p.alternativas[0]) for p in q.perguntas])


def test_depois_da_primeira_partida_a_identidade_trava_e_o_prazo_continua_livre(ctx):
    c = ctx.svc.criar(ctx.ator, dados(ctx))
    partida_em(ctx, c)
    for mudanca in ({"campus_id": ctx.outro_campus}, {"periodo": 2}, {"ano": 2025}):
        with pytest.raises(Conflito, match="já tem partidas"):
            ctx.svc.editar(ctx.ator, c.id, dados(ctx, **mudanca))
    q2 = ctx.q.criar(ctx.ator, "Outro")
    with pytest.raises(Conflito, match="já tem partidas"):
        ctx.svc.editar(ctx.ator, c.id, dados(ctx, questionario_id=q2.id))
    ctx.svc.editar(ctx.ator, c.id, dados(ctx, data_inicio=date(2026, 2, 1), data_fim=date(2026, 6, 30)))     # prorrogar
    c = ctx.svc.obter(c.id)
    assert (c.campus_id, c.periodo, c.data_fim) == (ctx.campus, 1, date(2026, 6, 30))


def test_editar_nao_conta_a_propria_coleta_como_duplicada(ctx):
    c = ctx.svc.criar(ctx.ator, dados(ctx))
    ctx.svc.editar(ctx.ator, c.id, dados(ctx, data_fim=date(2026, 4, 30)))       # mesma identidade, só o prazo
    outra = ctx.svc.criar(ctx.ator, dados(ctx, periodo=2))
    with pytest.raises(Duplicidade):                                              # agora mudar para a identidade da primeira
        ctx.svc.editar(ctx.ator, outra.id, dados(ctx, periodo=1))
    ctx.svc.editar(ctx.ator, outra.id, dados(ctx, periodo=1), duplicidade_confirmada=True)


def test_ano_fora_da_lista_so_vale_se_nao_mudou(ctx):
    c = ctx.svc.criar(ctx.ator, dados(ctx, ano=2025))
    ctx.svc.relogio = lambda: datetime(2029, 6, 1, 15, 0, tzinfo=timezone.utc)    # 2025 já saiu da janela de anos
    ctx.svc.editar(ctx.ator, c.id, dados(ctx, ano=2025, data_fim=date(2026, 4, 30)))
    with pytest.raises(Invalido):
        ctx.svc.editar(ctx.ator, c.id, dados(ctx, ano=2026))


def test_campus_inativado_depois_nao_impede_editar_a_coleta_existente(ctx):
    c = ctx.svc.criar(ctx.ator, dados(ctx, campus_id=ctx.outro_campus))
    db.session.get(Campus, ctx.outro_campus).ativo = False        # inativado depois de a coleta existir
    db.session.commit()
    ctx.svc.editar(ctx.ator, c.id, dados(ctx, campus_id=ctx.outro_campus, data_fim=date(2026, 4, 30)))   # não mudou o campus: ok
    db.session.get(Campus, ctx.campus).ativo = False
    db.session.commit()
    with pytest.raises(Invalido, match="inativo") as e:            # escolher um campus inativo é que não pode
        ctx.svc.editar(ctx.ator, c.id, dados(ctx, campus_id=ctx.campus))
    assert e.value.detalhes["campo"] == "campus_id"


def test_ativar_e_desativar(ctx):
    c = ctx.svc.criar(ctx.ator, dados(ctx, data_inicio=date(2026, 3, 1), data_fim=date(2026, 3, 31)))
    assert ctx.svc.situacao(c) == "aberta"
    ctx.svc.definir_ativo(ctx.ator, c.id, False)
    assert ctx.svc.situacao(ctx.svc.obter(c.id)) == "desativada"
    ctx.svc.definir_ativo(ctx.ator, c.id, True)
    assert ctx.svc.situacao(ctx.svc.obter(c.id)) == "aberta"


def test_coleta_inexistente(ctx):
    for acao in (lambda: ctx.svc.obter(9999), lambda: ctx.svc.definir_ativo(ctx.ator, 9999, False),
                 lambda: ctx.svc.editar(ctx.ator, 9999, dados(ctx))):
        with pytest.raises(NaoEncontrado):
            acao()


def test_listar_com_filtros_e_contagem_de_partidas(ctx):
    a = ctx.svc.criar(ctx.ator, dados(ctx, periodo=1))
    b = ctx.svc.criar(ctx.ator, dados(ctx, periodo=2, data_inicio=date(2026, 6, 1), data_fim=date(2026, 6, 30)))
    ctx.svc.criar(ctx.ator, dados(ctx, ano=2025, data_inicio=date(2025, 3, 1), data_fim=date(2025, 3, 31)))
    partida_em(ctx, a)
    itens = {c.id: (n, s) for c, n, s in ctx.svc.listar()}
    assert itens[a.id] == (1, "aberta") and itens[b.id] == (0, "agendada") and len(itens) == 3
    assert {c.id for c, _, _ in ctx.svc.listar(filtro_situacao="encerrada")} == {x.id for x in db.session.query(Coleta).filter_by(ano=2025)}
    assert len(ctx.svc.listar(questionario_id=ctx.qid)) == 3 and ctx.svc.listar(questionario_id=9999) == []


def test_eventos_vao_para_a_auditoria(ctx, caplog):
    caplog.set_level(logging.INFO, logger="techquiz.auditoria")
    c = ctx.svc.criar(ctx.ator, dados(ctx))
    ctx.svc.editar(ctx.ator, c.id, dados(ctx, data_fim=date(2026, 4, 1)))
    ctx.svc.definir_ativo(ctx.ator, c.id, False)
    log = "\n".join(r.getMessage() for r in caplog.records)
    for ev in ("coleta_criada", "coleta_editada", "coleta_desativada"):
        assert f"evento={ev}" in log and c.codigo in log
