"""Utilitários compartilhados pelos blueprints que usam formulários."""
from __future__ import annotations

from flask import flash

from app.errors import ErroDominio


def aplica_erro(form, erro: ErroDominio) -> int:
    """Mostra o erro de domínio junto ao campo indicado (422) ou, sem campo, como aviso geral com o status do erro
    (409, 403...). Devolve o status HTTP que a tela deve responder."""
    campo = erro.detalhes.get("campo")
    if campo and hasattr(form, campo):
        getattr(form, campo).errors = [*getattr(form, campo).errors, erro.mensagem]
        return 422
    flash(erro.mensagem, "danger")
    return erro.status
