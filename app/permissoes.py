"""Regras de quem pode fazer o quê com usuários (matriz da seção 13 do plano). Funções puras, sem Flask nem banco."""
from __future__ import annotations

from app.models.usuario import Usuario


def pode_gerenciar(ator: Usuario, alvo: Usuario) -> bool:
    """Editar, redefinir a senha ou excluir outro usuário.

    - ninguém mexe na raiz, e ninguém usa esta via em si mesmo (a própria senha é em /conta/senha);
    - super admin promovido gerencia só usuários comuns;
    - a raiz também gerencia super admins promovidos.
    """
    if alvo.raiz or ator.id == alvo.id:
        return False
    if alvo.eh_superadmin:
        return ator.raiz
    return ator.eh_superadmin


def pode_promover(ator: Usuario, alvo: Usuario) -> bool:
    return ator.raiz and not alvo.eh_superadmin


def pode_revogar(ator: Usuario, alvo: Usuario) -> bool:
    return ator.raiz and alvo.eh_superadmin and not alvo.raiz
