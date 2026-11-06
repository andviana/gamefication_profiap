"""Exceções de domínio. Os services lançam estas; um único handler as traduz em resposta HTTP."""
from __future__ import annotations

from typing import Any, Optional


class ErroDominio(Exception):
    """Base: carrega status HTTP, um motivo estável (para o cliente) e uma mensagem legível."""

    status = 400
    motivo = "erro"
    mensagem_padrao = "Não foi possível concluir a operação."

    def __init__(self, mensagem: Optional[str] = None, *, motivo: Optional[str] = None,
                 status: Optional[int] = None, **detalhes: Any):
        self.mensagem = mensagem or self.mensagem_padrao
        if motivo:
            self.motivo = motivo
        if status:
            self.status = status
        self.detalhes = detalhes
        super().__init__(self.mensagem)


class Invalido(ErroDominio):
    status = 422
    motivo = "invalido"
    mensagem_padrao = "Os dados enviados são inválidos."


class NaoEncontrado(ErroDominio):
    status = 404
    motivo = "nao_encontrado"
    mensagem_padrao = "Registro não encontrado."


class Proibido(ErroDominio):
    status = 403
    motivo = "proibido"
    mensagem_padrao = "Você não tem permissão para esta ação."


class Conflito(ErroDominio):
    status = 409
    motivo = "conflito"
    mensagem_padrao = "A operação conflita com o estado atual."


class Encerrado(ErroDominio):
    status = 410
    motivo = "encerrado"
    mensagem_padrao = "Este recurso foi encerrado."


class LimiteExcedido(ErroDominio):
    status = 429
    motivo = "limite_excedido"
    mensagem_padrao = "Muitas tentativas. Aguarde um pouco e tente de novo."

    def __init__(self, mensagem: Optional[str] = None, *, espera_seg: int = 0, **detalhes: Any):
        super().__init__(mensagem, espera_seg=espera_seg, **detalhes)
        self.espera_seg = espera_seg


class CredenciaisInvalidas(ErroDominio):
    status = 401
    motivo = "credenciais_invalidas"
    mensagem_padrao = "Login ou senha incorretos."


class Duplicidade(Conflito):
    """Já existe coleta com a mesma identidade. Não é um erro fatal: a tela avisa e pede confirmação."""
    motivo = "duplicidade"
    mensagem_padrao = "Já existe uma coleta para esta turma."

    def __init__(self, existentes, mensagem=None):
        super().__init__(mensagem)
        self.existentes = list(existentes)
