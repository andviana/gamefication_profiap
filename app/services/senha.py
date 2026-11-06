"""Política e hash de senha."""
from __future__ import annotations

import secrets
from functools import lru_cache

from werkzeug.security import check_password_hash, generate_password_hash

from app.errors import Invalido

MIN_SENHA = 8
MAX_SENHA = 128


def validar_senha(senha: str, campo: str = "senha") -> None:
    if len(senha) < MIN_SENHA:
        raise Invalido(f"A senha deve ter pelo menos {MIN_SENHA} caracteres.", campo=campo)
    if len(senha) > MAX_SENHA:
        raise Invalido(f"A senha deve ter no máximo {MAX_SENHA} caracteres.", campo=campo)


def gerar_hash(senha: str) -> str:
    return generate_password_hash(senha)


def confere(hash_guardado: str, senha: str) -> bool:
    return check_password_hash(hash_guardado, senha)


@lru_cache(maxsize=1)
def _hash_falso() -> str:
    return generate_password_hash(secrets.token_hex(16))


def gasta_tempo_de_verificacao(senha: str) -> None:
    """Para login inexistente, faz uma verificação de custo igual, para o tempo de resposta não revelar quem existe."""
    check_password_hash(_hash_falso(), senha)
