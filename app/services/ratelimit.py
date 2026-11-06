"""Limitador de falhas (código de acesso por IP e login por usuário), guardado na tabela `tentativa_falha`.

Regra: **só falhas contam**. Se houver `max_falhas` falhas dentro de uma janela de `janela_seg`, a chave fica bloqueada por
`bloqueio_seg` a partir da última dessas falhas. Pedidos feitos durante o bloqueio não são contados (não o prolongam).
"""
from __future__ import annotations

import math
from datetime import timedelta
from typing import Callable

from app.models.tipos import agora_utc
from app.repositories.tentativas import TentativaRepo


class LimitadorFalhas:
    def __init__(self, repo: TentativaRepo, tipo: str, max_falhas: int, janela_seg: int, bloqueio_seg: int,
                 relogio: Callable = agora_utc):
        self.repo = repo
        self.tipo = tipo
        self.max_falhas = max_falhas
        self.janela = timedelta(seconds=janela_seg)
        self.bloqueio = timedelta(seconds=bloqueio_seg)
        self.relogio = relogio

    def espera(self, chave: str) -> int:
        """Segundos até a chave ser liberada (0 = liberada)."""
        agora = self.relogio()
        # um bloqueio pode ter sido disparado até `bloqueio` atrás, por falhas que ocorreram até `janela` antes disso
        falhas = self.repo.momentos_desde(self.tipo, chave, agora - self.bloqueio - self.janela)
        n = self.max_falhas
        liberada_em = None
        for i in range(n - 1, len(falhas)):
            if falhas[i] - falhas[i - (n - 1)] <= self.janela:        # n falhas dentro de uma janela, terminando em falhas[i]
                liberada_em = falhas[i] + self.bloqueio
        if liberada_em is None:
            return 0
        return max(0, math.ceil((liberada_em - agora).total_seconds()))

    def registrar(self, chave: str) -> None:
        agora = self.relogio()
        self.repo.registrar(self.tipo, chave, agora)
        self.repo.purgar_antes_de(agora - timedelta(days=1))
        self.repo.commit()

    def limpar(self, chave: str) -> None:
        self.repo.limpar(self.tipo, chave)
        self.repo.commit()
