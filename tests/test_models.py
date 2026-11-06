"""Constraints e relacionamentos dos modelos, exercitados no banco (SQLite em memória, com FKs ligadas)."""
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import DataError, IntegrityError

# o SQLite recusa por CHECK (IntegrityError); o PostgreSQL recusa string longa pela largura do varchar (DataError)
RECUSA = (IntegrityError, DataError)

from app.extensions import db
from app.models import (Alternativa, Campus, Coleta, Curso, Grupo, ImportacaoPrevia, Partida, Pergunta, Questionario,
                        Resposta, TentativaFalha, Usuario)


@pytest.fixture
def sess(app):
    with app.app_context():
        db.create_all()
        yield db.session
        db.session.remove()
        db.drop_all()


def salva(sess, *objs):
    sess.add_all(objs)
    sess.commit()


def viola(sess, *objs):
    """Espera que gravar viole uma constraint do banco; desfaz a transação."""
    sess.add_all(objs)
    with pytest.raises(RECUSA):
        sess.commit()
    sess.rollback()


def novo_questionario(sess, nome="Q1", n_perguntas=2):
    grupo = sess.query(Grupo).filter_by(nome="Tecnologia").first() or Grupo(nome="Tecnologia")
    q = Questionario(nome=nome, orientacoes="# Orientações")
    for i in range(1, n_perguntas + 1):
        p = Pergunta(numero=i, texto=f"Pergunta {i}?", titulo=f"Tema {i}", grupo=grupo)
        p.alternativas = [Alternativa(letra="A", texto="a", correta=True), Alternativa(letra="B", texto="b")]
        q.perguntas.append(p)
    salva(sess, q)
    return q


def nova_coleta(sess, q, codigo="ABCDE", **extra):
    campus = sess.query(Campus).first() or Campus(nome="Belém")
    curso = sess.query(Curso).first() or Curso(nome="Pedagogia")
    base = dict(codigo=codigo, questionario=q, campus=campus, curso=curso, ano=2026, periodo=1,
                data_inicio=date(2026, 3, 1), data_fim=date(2026, 3, 31))
    c = Coleta(**{**base, **extra})
    salva(sess, c)
    return c


def nova_partida(sess, coleta, acertos=1, total=2):
    p = Partida(coleta=coleta, total_acertos=acertos, total_perguntas=total)
    salva(sess, p)
    return p


def nova_resposta(partida, pergunta, alternativa, **extra):
    base = dict(partida=partida, pergunta=pergunta, alternativa=alternativa, acertou=alternativa.correta, ordem=pergunta.numero,
                tempo_ms=1000, pergunta_numero=pergunta.numero, pergunta_titulo=pergunta.titulo,
                grupo_nome=pergunta.grupo.nome, alternativa_letra=alternativa.letra)
    return Resposta(**{**base, **extra})


def test_todas_as_tabelas_do_plano(sess):
    assert set(db.metadata.tables) == {
        "usuario", "campus", "curso", "grupo", "questionario", "pergunta", "alternativa", "coleta", "partida",
        "resposta", "tentativa_falha", "importacao_previa"}


# ---- usuário ---------------------------------------------------------------------------------
def test_usuario_login_unico(sess):
    salva(sess, Usuario(nome="A", login="ana", senha_hash="x"))
    viola(sess, Usuario(nome="B", login="ana", senha_hash="x"))


def test_usuario_perfil_invalido(sess):
    viola(sess, Usuario(nome="A", login="ana", senha_hash="x", perfil="chefe"))


def test_raiz_tem_de_ser_superadmin(sess):
    viola(sess, Usuario(nome="A", login="ana", senha_hash="x", perfil="comum", raiz=True))


def test_so_pode_haver_uma_raiz(sess):
    salva(sess, Usuario(nome="A", login="ana", senha_hash="x", perfil="superadmin", raiz=True))
    viola(sess, Usuario(nome="B", login="bia", senha_hash="x", perfil="superadmin", raiz=True))
    # vários super admins promovidos e comuns são permitidos
    salva(sess, Usuario(nome="C", login="cris", senha_hash="x", perfil="superadmin"),
          Usuario(nome="D", login="davi", senha_hash="x"), Usuario(nome="E", login="eva", senha_hash="x"))
    assert sess.query(Usuario).count() == 4


def test_usuario_padroes(sess):
    u = Usuario(nome="A", login="ana", senha_hash="x")
    salva(sess, u)
    assert u.perfil == "comum" and u.raiz is False and not u.eh_superadmin
    assert u.criado_em.tzinfo is not None


# ---- referências -----------------------------------------------------------------------------
@pytest.mark.parametrize("modelo", [Campus, Curso, Grupo])
def test_referencia_nome_unico_e_ativa_por_padrao(sess, modelo):
    a = modelo(nome="X")
    salva(sess, a)
    assert a.ativo is True
    viola(sess, modelo(nome="X"))


# ---- questionário, perguntas e alternativas --------------------------------------------------
def test_questionario_nome_unico(sess):
    salva(sess, Questionario(nome="Q"))
    viola(sess, Questionario(nome="Q"))


def test_numero_unico_dentro_do_questionario_mas_repete_entre_questionarios(sess):
    q1 = novo_questionario(sess, "Q1")
    q2 = novo_questionario(sess, "Q2")  # também tem a pergunta 1
    assert [p.numero for p in q2.perguntas] == [1, 2]
    viola(sess, Pergunta(questionario_id=q1.id, numero=1, texto="dup", titulo="t", grupo_id=q1.perguntas[0].grupo_id))


def test_perguntas_e_alternativas_vem_ordenadas(sess):
    q = novo_questionario(sess, n_perguntas=3)
    sess.expire_all()
    assert [p.numero for p in q.perguntas] == [1, 2, 3]
    assert [a.letra for a in q.perguntas[0].alternativas] == ["A", "B"]


def test_questionario_derivado(sess):
    original = novo_questionario(sess, "v1")
    copia = Questionario(nome="v2", derivado_de=original)
    salva(sess, copia)
    assert copia.derivado_de_id == original.id
    sess.delete(original)  # só rascunho pode ser apagado; a cópia perde a referência
    sess.commit()
    sess.refresh(copia)
    assert copia.derivado_de_id is None


def test_apagar_questionario_em_rascunho_leva_perguntas_e_alternativas(sess):
    q = novo_questionario(sess)
    sess.delete(q)
    sess.commit()
    assert sess.query(Pergunta).count() == 0 and sess.query(Alternativa).count() == 0


def test_so_uma_alternativa_correta_por_pergunta(sess):
    q = novo_questionario(sess)
    viola(sess, Alternativa(pergunta_id=q.perguntas[0].id, letra="C", texto="c", correta=True))
    salva(sess, Alternativa(pergunta_id=q.perguntas[0].id, letra="C", texto="c", correta=False))  # incorreta pode


def test_trocar_o_gabarito_numa_transacao_e_permitido(sess):
    q = novo_questionario(sess)
    a, b = q.perguntas[0].alternativas
    a.correta = False   # primeiro tira a antiga...
    sess.flush()
    b.correta = True    # ...depois marca a nova
    sess.commit()
    assert sess.query(Alternativa).filter_by(pergunta_id=q.perguntas[0].id, correta=True).one().letra == "B"


def test_letra_unica_por_pergunta_e_de_um_caractere(sess):
    q = novo_questionario(sess)
    pid = q.perguntas[0].id
    viola(sess, Alternativa(pergunta_id=pid, letra="A", texto="repetida"))
    viola(sess, Alternativa(pergunta_id=pid, letra="AB", texto="longa"))


def test_pergunta_exige_grupo_existente(sess):
    q = novo_questionario(sess)
    viola(sess, Pergunta(questionario_id=q.id, numero=9, texto="t", titulo="t", grupo_id=9999))


# ---- coleta ----------------------------------------------------------------------------------
def test_coleta_valida(sess):
    c = nova_coleta(sess, novo_questionario(sess))
    assert c.ativo is True and c.criada_em.tzinfo is not None and c.codigo == "ABCDE"


@pytest.mark.parametrize("extra", [{"codigo": "ABCD"}, {"codigo": "ABCDEF"}, {"periodo": 3}, {"periodo": 0},
                                   {"data_inicio": date(2026, 4, 1), "data_fim": date(2026, 3, 1)}])
def test_coleta_recusa_dados_invalidos(sess, extra):
    q = novo_questionario(sess)
    campus, curso = Campus(nome="Belém"), Curso(nome="Pedagogia")
    base = dict(codigo="ABCDE", questionario=q, campus=campus, curso=curso, ano=2026, periodo=1,
                data_inicio=date(2026, 3, 1), data_fim=date(2026, 3, 31))
    viola(sess, Coleta(**{**base, **extra}))


def test_coleta_prazo_de_um_dia_e_valido(sess):
    nova_coleta(sess, novo_questionario(sess), data_inicio=date(2026, 3, 1), data_fim=date(2026, 3, 1))


def test_codigo_da_coleta_e_unico(sess):
    q = novo_questionario(sess)
    nova_coleta(sess, q, "ABCDE")
    viola(sess, Coleta(codigo="ABCDE", questionario=q, campus=sess.query(Campus).first(), curso=sess.query(Curso).first(),
                       ano=2026, periodo=2, data_inicio=date(2026, 8, 1), data_fim=date(2026, 8, 2)))


def test_nao_apaga_questionario_campus_ou_curso_com_coleta(sess):
    q = novo_questionario(sess)
    c = nova_coleta(sess, q)
    for alvo in (q, c.campus, c.curso):
        sess.delete(alvo)
        with pytest.raises(IntegrityError):
            sess.commit()
        sess.rollback()


# ---- partida e resposta ----------------------------------------------------------------------
def test_partida_usa_uuid_e_recusa_totais_incoerentes(sess):
    c = nova_coleta(sess, novo_questionario(sess))
    p = nova_partida(sess, c)
    sess.expire_all()
    assert isinstance(sess.get(Partida, p.id).id, uuid.UUID)
    viola(sess, Partida(coleta=c, total_acertos=3, total_perguntas=2))
    viola(sess, Partida(coleta=c, total_acertos=-1, total_perguntas=2))


def test_uuid_repetido_e_recusado(sess):
    c = nova_coleta(sess, novo_questionario(sess))
    p = nova_partida(sess, c)
    # insert direto (Core): o banco, e não o mapa de identidade do ORM, é quem recusa o UUID repetido
    with pytest.raises(IntegrityError):
        sess.execute(Partida.__table__.insert().values(id=p.id, coleta_id=c.id, total_acertos=0, total_perguntas=2,
                                                       finalizada_em=datetime.now(timezone.utc)))
    sess.rollback()


def test_resposta_grava_snapshot_e_e_unica_por_pergunta(sess):
    q = novo_questionario(sess)
    c = nova_coleta(sess, q)
    p = nova_partida(sess, c)
    perg = q.perguntas[0]
    salva(sess, nova_resposta(p, perg, perg.alternativas[0]))
    r = sess.query(Resposta).one()
    assert (r.pergunta_numero, r.pergunta_titulo, r.grupo_nome, r.alternativa_letra, r.acertou) == (1, "Tema 1", "Tecnologia", "A", True)
    viola(sess, nova_resposta(p, perg, perg.alternativas[1]))


@pytest.mark.parametrize("extra", [{"tempo_ms": -1}, {"ordem": 0}])
def test_resposta_recusa_valores_invalidos(sess, extra):
    q = novo_questionario(sess)
    p = nova_partida(sess, nova_coleta(sess, q))
    perg = q.perguntas[0]
    viola(sess, nova_resposta(p, perg, perg.alternativas[0], **extra))


def test_o_snapshot_nao_muda_quando_o_texto_e_corrigido(sess):
    q = novo_questionario(sess)
    p = nova_partida(sess, nova_coleta(sess, q))
    perg = q.perguntas[0]
    salva(sess, nova_resposta(p, perg, perg.alternativas[0]))
    perg.titulo = "Título corrigido"
    sess.commit()
    assert sess.query(Resposta).one().pergunta_titulo == "Tema 1"


def test_nao_apaga_pergunta_alternativa_ou_questionario_com_resposta(sess):
    q = novo_questionario(sess)
    p = nova_partida(sess, nova_coleta(sess, q))
    perg = q.perguntas[0]
    salva(sess, nova_resposta(p, perg, perg.alternativas[0]))
    for alvo in (perg.alternativas[0], perg, q):
        sess.delete(alvo)
        with pytest.raises(IntegrityError):
            sess.commit()
        sess.rollback()


def test_apagar_partida_leva_as_respostas(sess):
    q = novo_questionario(sess)
    p = nova_partida(sess, nova_coleta(sess, q))
    salva(sess, nova_resposta(p, q.perguntas[0], q.perguntas[0].alternativas[0]))
    sess.delete(p)
    sess.commit()
    assert sess.query(Resposta).count() == 0


# ---- controle --------------------------------------------------------------------------------
def test_tentativa_falha_tipos(sess):
    salva(sess, TentativaFalha(tipo="codigo", chave="10.0.0.1"), TentativaFalha(tipo="login", chave="ana"))
    viola(sess, TentativaFalha(tipo="outro", chave="x"))


def test_importacao_previa_guarda_json(sess):
    u = Usuario(nome="A", login="ana", senha_hash="x", perfil="superadmin", raiz=True)
    salva(sess, u)
    expira = datetime.now(timezone.utc) + timedelta(minutes=15)
    salva(sess, ImportacaoPrevia(token="t" * 64, usuario_id=u.id, nome_questionario="Q", expira_em=expira,
                                 payload={"perguntas": [{"numero": 1, "texto": "Olá, ação!"}]}))
    sess.expire_all()
    prev = sess.get(ImportacaoPrevia, "t" * 64)
    assert prev.payload["perguntas"][0]["texto"] == "Olá, ação!" and prev.usada is False


def test_apagar_usuario_apaga_suas_previas(sess):
    u = Usuario(nome="A", login="ana", senha_hash="x")
    salva(sess, u)
    salva(sess, ImportacaoPrevia(token="t" * 64, usuario_id=u.id, nome_questionario="Q", payload={},
                                 expira_em=datetime.now(timezone.utc)))
    sess.delete(u)
    sess.commit()
    assert sess.query(ImportacaoPrevia).count() == 0


# ---- tipo de data ----------------------------------------------------------------------------
def test_datas_voltam_em_utc_com_fuso(sess):
    belem = timezone(timedelta(hours=-3))
    local = datetime(2026, 3, 1, 9, 0, tzinfo=belem)
    salva(sess, TentativaFalha(tipo="codigo", chave="ip", momento=local))
    sess.expire_all()
    lido = sess.query(TentativaFalha).one().momento
    assert lido.tzinfo is not None and lido == local and lido.utcoffset() == timedelta(0) and lido.hour == 12


def test_datetime_sem_fuso_e_recusado(sess):
    sess.add(TentativaFalha(tipo="codigo", chave="ip", momento=datetime(2026, 3, 1, 9, 0)))
    with pytest.raises(Exception, match="sem fuso"):
        sess.commit()
    sess.rollback()
