"""Limitador de falhas: janela deslizante, bloqueio e liberação (relógio controlado, banco real)."""
from datetime import datetime, timedelta, timezone

import pytest

from app.extensions import db
from app.models import TentativaFalha
from app.repositories.tentativas import TentativaRepo
from app.services.ratelimit import LimitadorFalhas

from conftest import web  # noqa: F401

T0 = datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc)


class Relogio:
    def __init__(self):
        self.t = T0

    def __call__(self):
        return self.t

    def passa(self, **kw):
        self.t += timedelta(**kw)


@pytest.fixture
def lim(web):
    with web.app_context():
        r = Relogio()
        # os valores padrão do plano: 10 falhas em 60 s bloqueiam por 300 s
        yield LimitadorFalhas(TentativaRepo(db.session), "codigo", 10, 60, 300, relogio=r), r


def falha(lim, relogio, chave="1.2.3.4", n=1, a_cada=0):
    for _ in range(n):
        lim.registrar(chave)
        relogio.passa(seconds=a_cada)


def test_livre_sem_falhas(lim):
    limitador, _ = lim
    assert limitador.espera("1.2.3.4") == 0


def test_nove_falhas_nao_bloqueiam_dez_sim(lim):
    limitador, r = lim
    falha(limitador, r, n=9, a_cada=1)
    assert limitador.espera("1.2.3.4") == 0
    falha(limitador, r, n=1)
    assert 290 <= limitador.espera("1.2.3.4") <= 300


def test_o_bloqueio_dura_o_periodo_todo_mesmo_com_janela_menor(lim):
    limitador, r = lim
    falha(limitador, r, n=10)                                    # 10 falhas no mesmo instante
    for segundos, bloqueada in [(30, True), (61, True), (200, True), (299, True), (301, False)]:
        r.t = T0 + timedelta(seconds=segundos)
        assert (limitador.espera("1.2.3.4") > 0) is bloqueada, segundos      # a janela é de 60 s, o bloqueio é de 300 s


def test_falhas_espalhadas_demais_nao_contam(lim):
    limitador, r = lim
    falha(limitador, r, n=9, a_cada=1)
    r.passa(seconds=70)                                           # a 10ª cai fora da janela de 60 s das outras
    falha(limitador, r, n=1)
    assert limitador.espera("1.2.3.4") == 0


def test_dez_falhas_dentro_de_uma_janela_em_qualquer_ponto_bloqueiam(lim):
    limitador, r = lim
    falha(limitador, r, n=5, a_cada=20)                           # 5 falhas em 100 s
    falha(limitador, r, n=5, a_cada=2)                            # mais 5 em 10 s: as últimas 6 + ... nenhuma janela de 60 s tem 10
    assert limitador.espera("1.2.3.4") == 0
    falha(limitador, r, n=5, a_cada=1)                            # agora as últimas 10 cabem em 60 s
    assert limitador.espera("1.2.3.4") > 0


def test_cada_chave_tem_o_seu_limite(lim):
    limitador, r = lim
    falha(limitador, r, "10.0.0.1", n=10)
    assert limitador.espera("10.0.0.1") > 0 and limitador.espera("10.0.0.2") == 0


def test_limpar_libera(lim):
    limitador, r = lim
    falha(limitador, r, n=10)
    limitador.limpar("1.2.3.4")
    assert limitador.espera("1.2.3.4") == 0


def test_tipos_diferentes_nao_se_misturam(lim):
    limitador, r = lim
    login = LimitadorFalhas(TentativaRepo(db.session), "login", 10, 60, 300, relogio=r)
    falha(login, r, n=10)
    assert login.espera("1.2.3.4") > 0 and limitador.espera("1.2.3.4") == 0


def test_registrar_remove_falhas_com_mais_de_um_dia(lim):
    limitador, r = lim
    falha(limitador, r, n=1)
    r.passa(days=2)
    falha(limitador, r, n=1)
    assert db.session.query(TentativaFalha).count() == 1


def test_a_espera_diminui_com_o_tempo(lim):
    limitador, r = lim
    falha(limitador, r, n=10)
    primeira = limitador.espera("1.2.3.4")
    r.passa(seconds=100)
    assert limitador.espera("1.2.3.4") == primeira - 100
