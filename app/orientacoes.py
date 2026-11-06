"""Texto padrão das orientações de um questionário novo (aviso de privacidade + como jogar).

Formato: `# título`, `- item`, parágrafos em branco; o jogo substitui `{{titulo}}`, `{{totalPerguntas}}` etc.
A redação do aviso de privacidade deve ser validada pela instituição (seção 14 do plano); cada questionário a edita.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

ARQUIVO = Path(__file__).parent / "textos" / "orientacoes_padrao.txt"


@lru_cache(maxsize=1)
def texto_padrao() -> str:
    return ARQUIVO.read_text(encoding="utf-8")
