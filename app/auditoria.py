"""Registro de eventos sensíveis (promoção, revogação, exclusão, redefinição de senha...).

Por ora vai para o log da aplicação, no logger `techquiz.auditoria`; a Fase 7 pode direcioná-lo a um arquivo próprio.
"""
from __future__ import annotations

import logging

log = logging.getLogger("techquiz.auditoria")


def _quem(usuario) -> str:
    return "-" if usuario is None else f"{usuario.login}#{usuario.id}"


def registrar(evento: str, ator=None, alvo=None, **detalhes) -> None:
    extras = " ".join(f"{k}={v}" for k, v in detalhes.items())
    log.info("AUDITORIA evento=%s ator=%s alvo=%s %s", evento, _quem(ator), _quem(alvo), extras)
