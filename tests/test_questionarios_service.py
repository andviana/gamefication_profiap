"""Questionários, perguntas, travas de estrutura e troca de gabarito, direto nos serviços."""
import logging
from datetime import date

import pytest

from app.errors import Conflito, Invalido, NaoEncontrado, Proibido
from app.extensions import db
from app.models import Alternativa, Grupo, Partida, Pergunta, Questionario, Resposta, Usuario
from app.orientacoes import texto_padrao
from app.services.perguntas import DadosAlternativa, DadosPergunta

from conftest import coleta_para, cria_mundo, responde, web  # noqa: F401


@pytest.fixture
def ctx(web):
    ids = cria_mundo(web)
    with web.app_context():
        c = web.extensions["container"]
        atores = {k: db.session.get(Usuario, v) for k, v in ids.items()}
        grupo = Grupo(nome="Tecnologia")
        db.session.add(grupo)
        db.session.commit()
        yield type("Ctx", (), dict(q=c.questionarios, p=c.perguntas, ator=atores["raiz"], comum=atores["comum1"],
                                   grupo_id=grupo.id))


def dados(grupo_id, titulo="Phishing", correta=2, n=4, **extra):
    alts = [DadosAlternativa(texto=f"Alternativa {i}", correta=(i == correta), texto_erro=f"erro {i}" if i != correta else None,
                             texto_acerto="certo" if i == correta else None) for i in range(n)]
    return DadosPergunta(texto=f"Enunciado de {titulo}?", titulo=titulo, grupo_id=grupo_id, alternativas=alts, **extra)


def questionario_com(ctx, nome="Q1", n_perguntas=2):
    q = ctx.q.criar(ctx.ator, nome, "Descrição")
    for i in range(n_perguntas):
        ctx.p.criar(ctx.ator, q.id, dados(ctx.grupo_id, titulo=f"Tema {i + 1}"))
    return q


# ---- questionários ----------------------------------------------------------------------------
def test_criar_questionario_usa_o_texto_padrao_das_orientacoes(ctx):
    q = ctx.q.criar(ctx.ator, "  Letramento   Digital ", " Uma descrição ")
    assert q.nome == "Letramento Digital" and q.descricao == "Uma descrição" and q.orientacoes == texto_padrao()
    assert "Sobre a sua participação" in q.orientacoes and "{{totalPerguntas}}" in q.orientacoes


@pytest.mark.parametrize("nome,descricao,campo", [("a", None, "nome"), ("x" * 161, None, "nome"), ("Valido", "d" * 1001, "descricao")])
def test_questionario_invalido(ctx, nome, descricao, campo):
    with pytest.raises(Invalido) as e:
        ctx.q.criar(ctx.ator, nome, descricao)
    assert e.value.detalhes["campo"] == campo


def test_nome_do_questionario_e_unico_sem_diferenciar_caixa(ctx):
    a = ctx.q.criar(ctx.ator, "Letramento Digital")
    with pytest.raises(Conflito):
        ctx.q.criar(ctx.ator, "letramento digital")
    b = ctx.q.criar(ctx.ator, "Outro Questionario")
    with pytest.raises(Conflito):
        ctx.q.editar(ctx.ator, b.id, "LETRAMENTO DIGITAL", None)
    ctx.q.editar(ctx.ator, a.id, "LETRAMENTO DIGITAL", "nova")      # o próprio nome, mudando só a caixa
    assert ctx.q.obter(a.id).descricao == "nova"


def test_atualizar_orientacoes(ctx):
    q = ctx.q.criar(ctx.ator, "Q1")
    ctx.q.atualizar_orientacoes(ctx.ator, q.id, "# Novo\r\n- item\r\n")
    assert ctx.q.obter(q.id).orientacoes == "# Novo\n- item"
    for ruim in ("", "   ", "x" * 20001):
        with pytest.raises(Invalido):
            ctx.q.atualizar_orientacoes(ctx.ator, q.id, ruim)


def test_estado_derivado_rascunho_em_coleta_travado(ctx):
    q = questionario_com(ctx)
    r = ctx.q.resumo(q)
    assert (r.estado, r.n_perguntas, r.n_coletas, r.n_respostas) == ("rascunho", 2, 0, 0)
    c = coleta_para(q)
    assert ctx.q.resumo(q).estado == "em coleta"
    p1, p2 = q.perguntas
    responde(c, [(p1, p1.alternativas[0]), (p2, p2.alternativas[2])])
    r = ctx.q.resumo(q)
    assert (r.estado, r.n_coletas, r.n_respostas) == ("travado", 1, 2)
    (_, resumo), = [(x, y) for x, y in ctx.q.listar() if x.id == q.id]
    assert resumo == r


def test_listar_traz_o_resumo_de_cada_um(ctx):
    a, b = questionario_com(ctx, "Alfa", 3), ctx.q.criar(ctx.ator, "Beta")
    coleta_para(a)
    por_nome = {q.nome: r for q, r in ctx.q.listar()}
    assert (por_nome["Alfa"].estado, por_nome["Alfa"].n_perguntas) == ("em coleta", 3)
    assert (por_nome["Beta"].estado, por_nome["Beta"].n_perguntas) == ("rascunho", 0)


def test_excluir_so_rascunho(ctx):
    rascunho, com_coleta = questionario_com(ctx, "Rascunho"), questionario_com(ctx, "Com coleta")
    coleta_para(com_coleta)
    with pytest.raises(Conflito, match="Só um questionário em rascunho"):     # a regra do serviço, antes do FK do banco
        ctx.q.excluir(ctx.ator, com_coleta.id)
    ctx.q.excluir(ctx.ator, rascunho.id)
    assert db.session.get(Questionario, rascunho.id) is None
    assert db.session.query(Pergunta).filter_by(questionario_id=rascunho.id).count() == 0     # perguntas junto
    assert db.session.query(Alternativa).count() == 2 * 4                                      # só as do outro
    with pytest.raises(NaoEncontrado):
        ctx.q.excluir(ctx.ator, rascunho.id)


def test_duplicar_cria_um_rascunho_independente(ctx):
    original = questionario_com(ctx, "Original", 2)
    ctx.q.atualizar_orientacoes(ctx.ator, original.id, "# Texto próprio")
    coleta_para(original)
    copia = ctx.q.duplicar(ctx.ator, original.id)
    assert copia.nome == "Original (cópia)" and copia.derivado_de_id == original.id and copia.orientacoes == "# Texto próprio"
    assert ctx.q.resumo(copia).estado == "rascunho" and ctx.q.resumo(copia).n_coletas == 0
    assert [(p.numero, p.titulo, [(a.letra, a.correta) for a in p.alternativas]) for p in copia.perguntas] == \
           [(p.numero, p.titulo, [(a.letra, a.correta) for a in p.alternativas]) for p in original.perguntas]
    assert {p.id for p in copia.perguntas}.isdisjoint({p.id for p in original.perguntas})       # cópia de verdade
    ctx.p.editar(ctx.ator, copia.id, copia.perguntas[0].id, dados(ctx.grupo_id, titulo="Mudou", correta=0))
    assert original.perguntas[0].titulo != "Mudou" and original.perguntas[0].alternativas[2].correta   # original intacto
    assert ctx.q.duplicar(ctx.ator, original.id).nome == "Original (cópia 2)"
    assert ctx.q.duplicar(ctx.ator, copia.id).nome.startswith("Original (cópia) (cópia")


# ---- perguntas: criação e validação ----------------------------------------------------------
def test_criar_pergunta_numera_sozinho_e_atribui_letras(ctx):
    q = ctx.q.criar(ctx.ator, "Q1")
    p1 = ctx.p.criar(ctx.ator, q.id, dados(ctx.grupo_id, correta=1))
    p2 = ctx.p.criar(ctx.ator, q.id, dados(ctx.grupo_id, titulo="Outra", n=3, correta=0))
    assert (p1.numero, p2.numero) == (1, 2)
    assert [(a.letra, a.correta) for a in p1.alternativas] == [("A", False), ("B", True), ("C", False), ("D", False)]
    assert len(p2.alternativas) == 3 and p2.alternativas[0].correta


def test_numero_informado_nao_pode_repetir(ctx):
    q = ctx.q.criar(ctx.ator, "Q1")
    ctx.p.criar(ctx.ator, q.id, dados(ctx.grupo_id, numero=5))
    with pytest.raises(Conflito) as e:
        ctx.p.criar(ctx.ator, q.id, dados(ctx.grupo_id, numero=5))
    assert e.value.detalhes["campo"] == "numero"
    outro = ctx.q.criar(ctx.ator, "Q2")
    ctx.p.criar(ctx.ator, outro.id, dados(ctx.grupo_id, numero=5))      # em outro questionário pode


def _quebra(**mudancas):
    d = dados(1)
    for k, v in mudancas.items():
        setattr(d, k, v)
    return d


@pytest.mark.parametrize("mudanca,campo", [
    ({"texto": "  "}, "texto"), ({"titulo": ""}, "titulo"), ({"titulo": "t" * 161}, "titulo"), ({"autoajuda": "a" * 2001}, "autoajuda"),
    ({"numero": 0}, "numero"), ({"grupo_id": 9999}, "grupo_id"), ({"grupo_id": 0}, "grupo_id"),
])
def test_validacao_dos_campos_da_pergunta(ctx, mudanca, campo):
    q = ctx.q.criar(ctx.ator, "Q1")
    d = dados(ctx.grupo_id)
    for k, v in mudanca.items():
        setattr(d, k, v)
    with pytest.raises(Invalido) as e:
        ctx.p.criar(ctx.ator, q.id, d)
    assert e.value.detalhes["campo"] == campo


@pytest.mark.parametrize("alts,campo", [
    ([DadosAlternativa("só uma", True)], "alternativas"),
    ([DadosAlternativa(f"alt {i}", i == 0) for i in range(5)], "alternativas"),          # o jogo suporta no máximo 4
    ([DadosAlternativa("a", False), DadosAlternativa("b", False)], "correta"),            # nenhuma correta
    ([DadosAlternativa("a", True), DadosAlternativa("b", True)], "correta"),              # duas corretas
    ([DadosAlternativa("a", True), DadosAlternativa("  ", False)], "alt_texto_1"),        # texto em branco
])
def test_validacao_das_alternativas(ctx, alts, campo):
    q = ctx.q.criar(ctx.ator, "Q1")
    d = dados(ctx.grupo_id)
    d.alternativas = alts
    with pytest.raises(Invalido) as e:
        ctx.p.criar(ctx.ator, q.id, d)
    assert e.value.detalhes["campo"] == campo
    assert db.session.query(Pergunta).count() == 0


def test_grupo_inativo_nao_serve_para_pergunta_nova(ctx):
    q = ctx.q.criar(ctx.ator, "Q1")
    db.session.get(Grupo, ctx.grupo_id).ativo = False
    db.session.commit()
    with pytest.raises(Invalido, match="inativo"):
        ctx.p.criar(ctx.ator, q.id, dados(ctx.grupo_id))


def test_pergunta_existente_pode_manter_o_grupo_que_foi_inativado(ctx):
    q = questionario_com(ctx, n_perguntas=1)
    db.session.get(Grupo, ctx.grupo_id).ativo = False
    db.session.commit()
    ctx.p.editar(ctx.ator, q.id, q.perguntas[0].id, dados(ctx.grupo_id, titulo="Editada"))
    assert q.perguntas[0].titulo == "Editada"


# ---- perguntas: edição livre (rascunho e em coleta) ------------------------------------------
@pytest.mark.parametrize("estado", ["rascunho", "em coleta"])
def test_edicao_livre_muda_tudo_inclusive_gabarito_e_alternativas(ctx, estado):
    q = questionario_com(ctx, n_perguntas=1)
    if estado == "em coleta":
        coleta_para(q)
    p = q.perguntas[0]
    outro_grupo = Grupo(nome="Gestão")
    db.session.add(outro_grupo)
    db.session.commit()
    # número, grupo, textos, gabarito (de C para A) e uma alternativa a menos (4 -> 3)
    ctx.p.editar(ctx.ator, q.id, p.id, DadosPergunta(
        texto="Novo?", titulo="Novo", grupo_id=outro_grupo.id, numero=7, autoajuda="dica",
        alternativas=[DadosAlternativa("x", True), DadosAlternativa("y"), DadosAlternativa("z")]))
    db.session.expire_all()
    p = db.session.get(Pergunta, p.id)
    assert (p.numero, p.grupo_id, p.texto, p.autoajuda) == (7, outro_grupo.id, "Novo?", "dica")
    assert [(a.letra, a.texto, a.correta) for a in p.alternativas] == [("A", "x", True), ("B", "y", False), ("C", "z", False)]


def test_edicao_pode_aumentar_as_alternativas_e_preserva_os_ids_existentes(ctx):
    q = questionario_com(ctx, n_perguntas=1)
    p = q.perguntas[0]
    ids_antes = [a.id for a in p.alternativas]
    d = dados(ctx.grupo_id, correta=3)
    ctx.p.editar(ctx.ator, q.id, p.id, d)
    assert [a.id for a in db.session.get(Pergunta, p.id).alternativas] == ids_antes       # mesmas linhas, atualizadas


def test_editar_para_um_numero_ja_usado_e_conflito(ctx):
    q = questionario_com(ctx, n_perguntas=2)
    d = dados(ctx.grupo_id, numero=2)
    with pytest.raises(Conflito):
        ctx.p.editar(ctx.ator, q.id, q.perguntas[0].id, d)


def test_excluir_pergunta_em_rascunho_leva_as_alternativas(ctx):
    q = questionario_com(ctx, n_perguntas=2)
    ctx.p.excluir(ctx.ator, q.id, q.perguntas[0].id)
    assert db.session.query(Pergunta).count() == 1 and db.session.query(Alternativa).count() == 4


def test_pergunta_de_outro_questionario_nao_e_acessivel(ctx):
    a, b = questionario_com(ctx, "Alfa", 1), questionario_com(ctx, "Beta", 1)
    with pytest.raises(NaoEncontrado):
        ctx.p.editar(ctx.ator, a.id, b.perguntas[0].id, dados(ctx.grupo_id))
    with pytest.raises(NaoEncontrado):
        ctx.p.excluir(ctx.ator, a.id, b.perguntas[0].id)


# ---- travas de estrutura (já há respostas) -----------------------------------------------------
@pytest.fixture
def travado(ctx):
    q = questionario_com(ctx, n_perguntas=2)
    c = coleta_para(q)
    p1, p2 = q.perguntas
    responde(c, [(p1, p1.alternativas[0]), (p2, p2.alternativas[2])])
    assert ctx.q.resumo(q).estado == "travado"
    return q


def test_travado_permite_corrigir_textos(ctx, travado):
    p = travado.perguntas[0]
    d = DadosPergunta(texto="Enunciado corrigido?", titulo="Título corrigido", grupo_id=p.grupo_id, autoajuda="nova dica",
                      alternativas=[DadosAlternativa(f"Texto corrigido {a.letra}", a.correta, "ok", "ruim") for a in p.alternativas])
    ctx.p.editar(ctx.ator, travado.id, p.id, d)
    db.session.expire_all()
    p = db.session.get(Pergunta, p.id)
    assert p.texto == "Enunciado corrigido?" and p.titulo == "Título corrigido" and p.alternativas[1].texto == "Texto corrigido B"
    assert [a.correta for a in p.alternativas] == [False, False, True, False]      # gabarito intacto


def test_travado_recusa_mudancas_de_estrutura(ctx, travado):
    p = travado.perguntas[0]
    base = lambda **kw: dados(p.grupo_id, correta=2, **kw)   # noqa: E731
    outro_grupo = Grupo(nome="Gestão")
    db.session.add(outro_grupo)
    db.session.commit()
    casos = [
        (base(numero=9), "número e o grupo"),
        (dados(outro_grupo.id, correta=2), "número e o grupo"),
        (base(), None),                                           # este é válido: só texto igual
        (dados(p.grupo_id, correta=2, n=3), "adicionar nem remover alternativas"),
        (dados(p.grupo_id, correta=0), "gabarito só muda"),
    ]
    for d, trecho in casos:
        if trecho is None:
            ctx.p.editar(ctx.ator, travado.id, p.id, d)
        else:
            with pytest.raises(Conflito, match=trecho):
                ctx.p.editar(ctx.ator, travado.id, p.id, d)
    assert db.session.get(Pergunta, p.id).numero == 1 and len(db.session.get(Pergunta, p.id).alternativas) == 4


def test_travado_nao_cria_nem_exclui_perguntas(ctx, travado):
    with pytest.raises(Conflito, match="duplique"):
        ctx.p.criar(ctx.ator, travado.id, dados(ctx.grupo_id))
    with pytest.raises(Conflito, match="duplique"):
        ctx.p.excluir(ctx.ator, travado.id, travado.perguntas[0].id)
    assert db.session.query(Pergunta).filter_by(questionario_id=travado.id).count() == 2


def test_duplicar_um_travado_libera_a_estrutura(ctx, travado):
    copia = ctx.q.duplicar(ctx.ator, travado.id)
    nova = ctx.p.criar(ctx.ator, copia.id, dados(ctx.grupo_id, titulo="Pergunta nova"))
    ctx.p.excluir(ctx.ator, copia.id, copia.perguntas[0].id)
    assert nova.numero == 3 and db.session.query(Pergunta).filter_by(questionario_id=travado.id).count() == 2


def test_o_banco_tambem_protege_perguntas_com_resposta(ctx, travado):
    from sqlalchemy.exc import IntegrityError
    db.session.delete(travado.perguntas[0])
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


# ---- troca de gabarito ----------------------------------------------------------------------------
def test_so_super_admin_troca_o_gabarito(ctx, travado):
    with pytest.raises(Proibido):
        ctx.p.trocar_gabarito(ctx.comum, travado.id, travado.perguntas[0].id, "A")
    assert travado.perguntas[0].alternativas[2].correta


def test_trocar_gabarito_sem_respostas_so_muda_a_alternativa(ctx):
    q = questionario_com(ctx, n_perguntas=1)
    p = q.perguntas[0]
    assert ctx.p.trocar_gabarito(ctx.ator, q.id, p.id, "b") == (0, 0)            # minúscula aceita
    db.session.expire_all()
    assert [a.correta for a in db.session.get(Pergunta, p.id).alternativas] == [False, True, False, False]


def test_trocar_gabarito_valida_a_letra(ctx):
    q = questionario_com(ctx, n_perguntas=1)
    p = q.perguntas[0]
    for letra, trecho in [("Z", "Escolha uma das alternativas"), ("", "Escolha uma das alternativas"), ("C", "já é a alternativa correta")]:
        with pytest.raises(Invalido, match=trecho):
            ctx.p.trocar_gabarito(ctx.ator, q.id, p.id, letra)


def test_trocar_gabarito_recalcula_respostas_e_partidas(ctx):
    q = questionario_com(ctx, n_perguntas=2)
    c = coleta_para(q)
    p1, p2 = q.perguntas
    A1, B1, C1, D1 = p1.alternativas          # gabarito atual de p1 = C
    A2, B2, C2, D2 = p2.alternativas          # gabarito atual de p2 = C
    pa = responde(c, [(p1, C1), (p2, C2)])    # 2 acertos
    pb = responde(c, [(p1, A1), (p2, C2)])    # 1 acerto (p2)
    pc = responde(c, [(p1, B1), (p2, A2)])    # 0 acertos
    pd = responde(c, [(p1, A1), (p2, B2)])    # 0 acertos
    assert [p.total_acertos for p in (pa, pb, pc, pd)] == [2, 1, 0, 0]

    resultado = ctx.p.trocar_gabarito(ctx.ator, q.id, p1.id, "A")     # p1: C -> A
    assert resultado == (4, 4)

    db.session.expire_all()
    acertou_p1 = {r.partida_id: r.acertou for r in db.session.query(Resposta).filter_by(pergunta_id=p1.id)}
    assert acertou_p1 == {pa.id: False, pb.id: True, pc.id: False, pd.id: True}      # quem marcou A agora acertou
    acertou_p2 = [r.acertou for r in db.session.query(Resposta).filter_by(pergunta_id=p2.id).order_by(Resposta.partida_id)]
    assert sorted(acertou_p2) == [False, False, True, True]                           # p2 não foi tocada
    assert [db.session.get(Partida, p.id).total_acertos for p in (pa, pb, pc, pd)] == [1, 2, 0, 1]
    for partida in db.session.query(Partida):                                          # coerência: total = soma de acertou
        assert partida.total_acertos == sum(1 for r in partida.respostas if r.acertou)
    assert [a.correta for a in db.session.get(Pergunta, p1.id).alternativas] == [True, False, False, False]


def test_trocar_gabarito_e_auditado(ctx, travado, caplog):
    caplog.set_level(logging.INFO, logger="techquiz.auditoria")
    ctx.p.trocar_gabarito(ctx.ator, travado.id, travado.perguntas[0].id, "D")
    log = "\n".join(r.getMessage() for r in caplog.records)
    assert "evento=gabarito_trocado" in log and "de=C" in log and "para=D" in log and "respostas=1" in log
