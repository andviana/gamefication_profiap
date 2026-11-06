"""Token do gabarito: o servidor não envia um campo `correta`; envia o token da alternativa correta de cada pergunta.

token = SHA-256(sal + questionario_id + numero_da_pergunta + letra), em hexadecimal minúsculo. O jogo calcula o token da letra
que o aluno escolheu e compara com `token_correta` (feedback imediato). É ofuscação, não segurança: o sal vai ao cliente e há
só 4 letras. A qualidade dos dados não depende disso: o servidor recalcula `acertou` ao gravar a partida.
"""
from __future__ import annotations

import hashlib


def token(sal: str, questionario_id: int, numero: int, letra: str) -> str:
    return hashlib.sha256(f"{sal}{questionario_id}{numero}{letra}".encode("utf-8")).hexdigest()
