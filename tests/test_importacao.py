"""Importação de CSV: analisador (puro) e serviço (prévia + confirmação)."""
from datetime import timedelta
from pathlib import Path

import pytest

from app.errors import Conflito, Invalido, NaoEncontrado, Proibido
from app.extensions import db
from app.models import Alternativa, Grupo, ImportacaoPrevia, Pergunta, Questionario, Usuario
from app.models.tipos import agora_utc
from app.orientacoes import texto_padrao
from app.repositories.importacoes import PreviaRepo
from app.services.csv_import import analisar

from conftest import cria_mundo, web  # noqa: F401

DADOS = Path(__file__).resolve().parent.parent / "data"
CAB_P = "Número da pergunta;Pergunta;Título;Grupo;Autoajuda"
CAB_A = "Número da pergunta;Letra;Texto da alternativa;Correta ou incorreta;Texto de acerto;Texto de erro"


def csv_bytes(cabecalho, *linhas, bom=True, sep=";"):
    texto = "\n".join([cabecalho, *linhas]).replace(";", sep)
    return ((b"\xef\xbb\xbf" if bom else b"") + texto.encode("utf-8"))


def ok_p():
    return csv_bytes(CAB_P, "1;Qual é a certa?;Phishing;Segurança;dica")


def ok_a(*extra):
    return csv_bytes(CAB_A, "1;A;errada;Incorreta;;porque não", "1;B;certa;Correta;parabéns;", *extra)


def erros_de(perguntas, alternativas):
    return [str(e) for e in analisar(perguntas, alternativas).erros]


# ---- analisador: arquivos reais e formatos -------------------------------------------------------
def test_os_csvs_reais_do_projeto_passam():
    a = analisar((DADOS / "perguntas.csv").read_bytes(), (DADOS / "alternativas.csv").read_bytes())
    assert a.erros == [] and a.avisos == []
    assert len(a.perguntas) == 8 and a.n_alternativas == 28
    assert {p["grupo"] for p in a.perguntas} == {"Segurança Digital", "Tecnologia", "Gestão Universitária"}
    assert [next(x["letra"] for x in p["alternativas"] if x["correta"]) for p in a.perguntas] == list("CBDACABB")
    assert a.perguntas[0]["autoajuda"].startswith("Instituições sérias") and a.perguntas[1]["autoajuda"] is None


@pytest.mark.parametrize("sep", [";", ",", "\t"])
def test_detecta_o_delimitador(sep):
    a = analisar(csv_bytes(CAB_P, "1;Enunciado;Título;Grupo;", sep=sep),
                 csv_bytes(CAB_A, "1;A;x;Incorreta;;", "1;B;y;Correta;;", sep=sep))
    assert a.erros == [] and a.n_alternativas == 2


def test_aceita_sem_bom_e_cabecalho_com_outra_caixa_e_sem_acento():
    p = csv_bytes("NUMERO DA PERGUNTA;pergunta;TITULO;grupo;autoajuda", "1;Enunciado;T;G;", bom=False)
    a = csv_bytes("numero da pergunta;LETRA;Texto da Alternativa;correta ou incorreta;texto de acerto;texto de erro",
                  "1;A;x;Incorreta;;", "1;B;y;Correta;;", bom=False)
    assert analisar(p, a).erros == []


def test_campos_com_aspas_e_quebras_de_linha():
    p = csv_bytes(CAB_P, '1;"Linha 1\nLinha 2; com ""aspas""";Tema;Grupo;')
    a = analisar(p, ok_a())
    assert a.erros == [] and a.perguntas[0]["texto"] == 'Linha 1\nLinha 2; com "aspas"'


@pytest.mark.parametrize("valor,esperado", [("Correta", True), ("sim", True), ("C", True), ("verdadeiro", True),
                                            ("Incorreta", False), ("não", False), ("I", False), ("falso", False)])
def test_aceita_variacoes_de_correta_ou_incorreta(valor, esperado):
    a = analisar(ok_p(), csv_bytes(CAB_A, f"1;A;x;{valor};;", f"1;B;y;{'Incorreta' if esperado else 'Correta'};;"))
    assert a.erros == [] and a.perguntas[0]["alternativas"][0]["correta"] is esperado


def test_normaliza_espacos_do_titulo_e_do_grupo():
    a = analisar(csv_bytes(CAB_P, "1;Enunciado;  Meu   título ;  Segurança   Digital ;"), ok_a())
    assert (a.perguntas[0]["titulo"], a.perguntas[0]["grupo"]) == ("Meu título", "Segurança Digital")


# ---- analisador: erros ------------------------------------------------------------------------------
def test_arquivo_vazio_ou_sem_linhas():
    assert "arquivo vazio" in erros_de(b"", ok_a())[0]
    assert "arquivo vazio" in erros_de(b"\xef\xbb\xbf   \n", ok_a())[0]
    assert any("nenhuma pergunta encontrada" in e for e in erros_de(csv_bytes(CAB_P), csv_bytes(CAB_A)))


def test_codificacao_que_nao_e_utf8():
    latin1 = "Número da pergunta;Pergunta;Título;Grupo;Autoajuda\n1;Ação?;T;G;".encode("latin-1")
    assert "não está em UTF-8" in erros_de(latin1, ok_a())[0]


def test_bytes_nulos_e_recusado():
    assert "bytes nulos" in erros_de(b"abc\x00def", ok_a())[0]


def test_coluna_ausente_no_cabecalho():
    e = erros_de(csv_bytes("Número da pergunta;Pergunta;Título", "1;a;b"), ok_a())
    assert "colunas ausentes" in e[0] and "grupo" in e[0] and "autoajuda" in e[0]


@pytest.mark.parametrize("linha,trecho", [
    ("abc;Enunciado;T;G;", "inválido"), ("0;Enunciado;T;G;", "1 ou maior"), ("-3;Enunciado;T;G;", "1 ou maior"),
    ("1;;T;G;", "sem o texto do enunciado"), ("1;Enunciado;;G;", "sem “Título”"), ("1;Enunciado;T;;", "sem “Grupo”"),
    (f"1;Enunciado;{'t' * 161};G;", "título com mais de 160"), (f"1;{'e' * 5001};T;G;", "enunciado com mais de 5000"),
])
def test_erros_em_perguntas(linha, trecho):
    e = erros_de(csv_bytes(CAB_P, linha), ok_a())
    assert any(trecho in x for x in e), e
    assert e[0].startswith("perguntas.csv:2")           # aponta o arquivo e a linha


def test_pergunta_repetida():
    e = erros_de(csv_bytes(CAB_P, "1;A?;T;G;", "1;B?;T;G;"), ok_a())
    assert any("repetida (primeira ocorrência na linha 2)" in x and ":3:" in x for x in e)


@pytest.mark.parametrize("linhas,trecho", [
    (["9;A;x;Incorreta;;"], "pergunta 9, que não existe"),
    (["x;A;x;Incorreta;;"], "“Número da pergunta” inválido"),
    (["1;E;x;Incorreta;;"], "letra inválida"),
    (["1;A;repetida;Incorreta;;"], "letra A repetida"),
    (["1;C;x;talvez;;"], "deve ser “Correta” ou “Incorreta”"),
    (["1;C;;Incorreta;;"], "texto da alternativa vazio"),
])
def test_erros_em_alternativas(linhas, trecho):
    e = erros_de(ok_p(), ok_a(*linhas))
    assert any(trecho in x and x.startswith("alternativas.csv") for x in e), e


@pytest.mark.parametrize("linhas_a,trecho", [
    (["1;A;x;Incorreta;;"], "tem 1 alternativa"),
    (["1;A;x;Incorreta;;", "1;B;y;Incorreta;;"], "SEM alternativa correta"),
    (["1;A;x;Correta;;", "1;B;y;Correta;;"], "MAIS DE UMA alternativa correta (A, B)"),
    ([], "não tem nenhuma alternativa"),
])
def test_erros_por_pergunta(linhas_a, trecho):
    e = erros_de(ok_p(), csv_bytes(CAB_A, *linhas_a))
    assert any(trecho in x for x in e), e


def test_letras_nao_sequenciais_sao_so_aviso():
    a = analisar(ok_p(), csv_bytes(CAB_A, "1;A;x;Incorreta;;", "1;C;y;Correta;;"))
    assert a.erros == [] and "não são sequenciais" in a.avisos[0].mensagem


def test_limite_de_perguntas():
    linhas = [f"{i};Enunciado {i};T;G;" for i in range(1, 302)]
    e = erros_de(csv_bytes(CAB_P, *linhas), ok_a())
    assert any("perguntas demais (301)" in x for x in e)


def test_reune_todos_os_erros_de_uma_vez():
    e = erros_de(csv_bytes(CAB_P, "x;a;b;c;", "2;;;;"), csv_bytes(CAB_A, "9;A;x;Incorreta;;"))
    assert len(e) >= 5      # o usuário corrige tudo numa rodada, não um erro por vez


# ---- serviço: prévia ------------------------------------------------------------------------------
@pytest.fixture
def ctx(web):
    ids = cria_mundo(web)
    with web.app_context():
        c = web.extensions["container"]
        atores = {k: db.session.get(Usuario, v) for k, v in ids.items()}
        yield type("Ctx", (), dict(svc=c.importacao, ator=atores["raiz"], promo=atores["promo1"], comum=atores["comum1"],
                                   outro=atores["promo2"], settings=c.settings))


def arquivos_reais():
    return (("perguntas.csv", (DADOS / "perguntas.csv").read_bytes()), ("alternativas.csv", (DADOS / "alternativas.csv").read_bytes()))


def previa_real(ctx, nome="Letramento Digital 2026.1", ator=None):
    return ctx.svc.analisar(ator or ctx.ator, nome, "Descrição", *arquivos_reais())


def test_previa_dos_csvs_reais(ctx):
    p = previa_real(ctx)
    assert p.ok and len(p.token) >= 40 and p.nome == "Letramento Digital 2026.1"
    assert (len(p.analise.perguntas), p.analise.n_alternativas) == (8, 28)
    assert p.grupos_novos == ["Gestão Universitária", "Segurança Digital", "Tecnologia"] and p.grupos_existentes == []
    # a prévia não cria nada além do registro da própria prévia
    assert db.session.query(Questionario).count() == 0 and db.session.query(Grupo).count() == 0
    assert db.session.query(ImportacaoPrevia).one().expira_em - db.session.query(ImportacaoPrevia).one().criada_em == timedelta(minutes=15)


def test_so_super_admin_importa(ctx):
    with pytest.raises(Proibido):
        previa_real(ctx, ator=ctx.comum)
    assert previa_real(ctx, ator=ctx.promo).ok                      # promovido pode
    with pytest.raises(Proibido):
        ctx.svc.confirmar(ctx.comum, "qualquer")


def test_previa_com_erros_nao_gera_token_nem_grava_nada(ctx):
    p = ctx.svc.analisar(ctx.ator, "Meu Questionário", None, ("perguntas.csv", csv_bytes(CAB_P, "x;a;b;c;")), ("alternativas.csv", ok_a()))
    assert not p.ok and p.token is None and p.analise.erros
    assert db.session.query(ImportacaoPrevia).count() == 0 and db.session.query(Questionario).count() == 0


@pytest.mark.parametrize("pedaco,campo", [
    (("perguntas.txt", b"x"), "arquivo_perguntas"), (("perguntas.csv", b""), "arquivo_perguntas"),
    (("perguntas.csv", b"x" * (2 * 1024 * 1024 + 1)), "arquivo_perguntas"),
])
def test_arquivo_invalido_antes_de_analisar(ctx, pedaco, campo):
    with pytest.raises(Invalido) as e:
        ctx.svc.analisar(ctx.ator, "Meu Questionário", None, pedaco, ("alternativas.csv", ok_a()))
    assert e.value.detalhes["campo"] == campo


def test_nome_ja_existente_e_recusado_na_previa(ctx):
    ctx.svc.questionarios.adicionar(Questionario(nome="Existente"))
    ctx.svc.questionarios.commit()
    with pytest.raises(Conflito) as e:
        previa_real(ctx, nome="existente")
    assert e.value.detalhes["campo"] == "nome"


def test_grupo_existente_e_reaproveitado_sem_diferenciar_caixa_e_inativo_e_erro(ctx):
    db.session.add_all([Grupo(nome="TECNOLOGIA"), Grupo(nome="Segurança Digital", ativo=False)])
    db.session.commit()
    p = previa_real(ctx)
    assert not p.ok
    assert any("“Segurança Digital” existe, mas está inativo" in str(e) for e in p.analise.erros)
    assert p.grupos_existentes == ["TECNOLOGIA"] and p.grupos_novos == ["Gestão Universitária"]
    db.session.get(Grupo, db.session.query(Grupo).filter_by(nome="Segurança Digital").one().id).ativo = True
    db.session.commit()
    assert previa_real(ctx, nome="Outro nome").ok


# ---- serviço: confirmação ---------------------------------------------------------------------
def test_confirmar_cria_o_questionario_completo(ctx):
    p = previa_real(ctx)
    q = ctx.svc.confirmar(ctx.ator, p.token)
    db.session.expire_all()
    q = db.session.get(Questionario, q.id)
    assert q.nome == "Letramento Digital 2026.1" and q.descricao == "Descrição" and q.orientacoes == texto_padrao()
    assert len(q.perguntas) == 8 and sum(len(p.alternativas) for p in q.perguntas) == 28
    assert [p.numero for p in q.perguntas] == list(range(1, 9)) and q.perguntas[0].grupo.nome == "Segurança Digital"
    assert [next(a.letra for a in p.alternativas if a.correta) for p in q.perguntas] == list("CBDACABB")
    assert q.perguntas[0].alternativas[2].texto_acerto.startswith("Correto: desconfie")
    assert {g.nome for g in db.session.query(Grupo)} == {"Segurança Digital", "Tecnologia", "Gestão Universitária"}
    assert ctx.svc.questionarios.contagens()[q.id] == (8, 0, 0)         # rascunho: sem coleta nem resposta
    assert db.session.query(ImportacaoPrevia).filter_by(usada=True).count() == 1


def test_confirmar_nao_apaga_nem_altera_o_que_ja_existe(ctx):
    antigo = Questionario(nome="Antigo", orientacoes="# Meu texto")
    antigo.perguntas.append(Pergunta(numero=1, texto="velha", titulo="v", grupo=Grupo(nome="Tecnologia"),
                                     alternativas=[Alternativa(letra="A", texto="a", correta=True), Alternativa(letra="B", texto="b")]))
    db.session.add(antigo)
    db.session.commit()
    ctx.svc.confirmar(ctx.ator, previa_real(ctx).token)
    db.session.expire_all()
    antigo = db.session.query(Questionario).filter_by(nome="Antigo").one()
    assert antigo.orientacoes == "# Meu texto" and antigo.perguntas[0].texto == "velha"
    assert db.session.query(Grupo).filter_by(nome="Tecnologia").count() == 1          # reaproveitou o grupo
    assert db.session.query(Questionario).count() == 2


def test_token_e_de_uso_unico(ctx):
    p = previa_real(ctx)
    ctx.svc.confirmar(ctx.ator, p.token)
    with pytest.raises(Conflito, match="já foi usada ou expirou"):
        ctx.svc.confirmar(ctx.ator, p.token)           # duplo clique
    assert db.session.query(Questionario).count() == 1


def test_consumo_do_token_e_atomico(ctx):
    p = previa_real(ctx)
    repo = PreviaRepo(db.session)
    agora = agora_utc()
    assert repo.consumir(p.token, ctx.ator.id, agora) is True
    assert repo.consumir(p.token, ctx.ator.id, agora) is False      # a segunda chamada (corrida) perde


def test_repositorio_so_consome_a_previa_do_proprio_dono(ctx):
    p = previa_real(ctx)
    repo = PreviaRepo(db.session)
    assert repo.consumir(p.token, ctx.outro.id, agora_utc()) is False      # a camada de baixo também confere o dono
    assert repo.consumir(p.token, ctx.ator.id, agora_utc()) is True


def test_previa_expirada_e_recusada(ctx):
    p = previa_real(ctx)
    ctx.svc.relogio = lambda: agora_utc() + timedelta(minutes=16)
    with pytest.raises(Conflito, match="expirou"):
        ctx.svc.confirmar(ctx.ator, p.token)
    assert db.session.query(Questionario).count() == 0


def test_previa_de_outro_usuario_ou_inexistente(ctx):
    p = previa_real(ctx)
    with pytest.raises(NaoEncontrado):
        ctx.svc.confirmar(ctx.outro, p.token)          # outro super admin não usa a prévia alheia
    with pytest.raises(NaoEncontrado):
        ctx.svc.confirmar(ctx.ator, "token-que-nao-existe")
    with pytest.raises(NaoEncontrado):
        ctx.svc.confirmar(ctx.ator, "")
    assert ctx.svc.confirmar(ctx.ator, p.token)        # a prévia do dono segue válida


def test_nome_criado_entre_a_previa_e_a_confirmacao(ctx):
    p = previa_real(ctx)
    ctx.svc.questionarios.adicionar(Questionario(nome="Letramento Digital 2026.1"))
    ctx.svc.questionarios.commit()
    with pytest.raises(Conflito, match="Já existe um questionário"):
        ctx.svc.confirmar(ctx.ator, p.token)
    assert db.session.query(Pergunta).count() == 0


def test_falha_no_meio_nao_cria_nada_e_a_previa_continua_valida(ctx, monkeypatch):
    p = previa_real(ctx)
    original = type(ctx.svc)._cria

    def quebra(self, previa):
        original(self, previa)                     # monta tudo na sessão...
        raise RuntimeError("falha simulada")       # ...e falha antes do commit

    monkeypatch.setattr(type(ctx.svc), "_cria", quebra)
    with pytest.raises(RuntimeError):
        ctx.svc.confirmar(ctx.ator, p.token)
    assert db.session.query(Questionario).count() == 0 and db.session.query(Pergunta).count() == 0
    assert db.session.query(Grupo).count() == 0                                       # nem os grupos
    assert db.session.query(ImportacaoPrevia).one().usada is False                    # o "usada" também foi desfeito
    monkeypatch.undo()
    assert ctx.svc.confirmar(ctx.ator, p.token)                                       # e agora funciona


def test_previas_antigas_sao_purgadas(ctx):
    p1 = previa_real(ctx, nome="Primeira")
    ctx.svc.confirmar(ctx.ator, p1.token)                       # usada
    p2 = previa_real(ctx, nome="Segunda")                       # esta chamada purga a usada
    tokens = {x.token for x in db.session.query(ImportacaoPrevia)}
    assert tokens == {p2.token}
    ctx.svc.relogio = lambda: agora_utc() + timedelta(hours=1)
    previa_real(ctx, nome="Terceira")                           # purga a expirada
    assert p2.token not in {x.token for x in db.session.query(ImportacaoPrevia)}


def test_questionario_importado_obedece_as_regras_de_estrutura(ctx):
    q = ctx.svc.confirmar(ctx.ator, previa_real(ctx).token)
    c = db.session.get(Questionario, q.id)
    container = ctx.svc.questionarios                          # (repositório; as regras estão nos testes de perguntas)
    assert len(c.perguntas) == 8 and container.por_id(q.id) is c
