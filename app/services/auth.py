"""Autenticação: confere login e senha e bloqueia o usuário após falhas seguidas."""
from __future__ import annotations

from typing import Callable

from app.config import Settings
from app.errors import CredenciaisInvalidas, LimiteExcedido
from app.models.controle import TIPO_LOGIN
from app.models.tipos import agora_utc
from app.models.usuario import Usuario
from app.repositories.tentativas import TentativaRepo
from app.repositories.usuarios import UsuarioRepo
from app.services import senha as politica
from app.services.ratelimit import LimitadorFalhas


class AuthService:
    def __init__(self, repo: UsuarioRepo, tentativas: TentativaRepo, settings: Settings, relogio: Callable = agora_utc):
        self.repo = repo
        self.tentativas = tentativas
        self.settings = settings
        self.relogio = relogio
        # janela = bloqueio: N falhas dentro do período de bloqueio travam o usuário por esse mesmo período
        self.limitador = LimitadorFalhas(tentativas, TIPO_LOGIN, settings.login_max_falhas, settings.login_bloqueio_seg,
                                         settings.login_bloqueio_seg, relogio=lambda: self.relogio())

    def espera_bloqueio(self, login: str) -> int:
        """Segundos restantes de bloqueio para este login (0 = liberado). Ver LimitadorFalhas."""
        return self.limitador.espera(login)

    def autenticar(self, login: str, senha: str) -> Usuario:
        login = (login or "").strip().lower()
        senha = senha or ""
        if not login or not senha:
            raise CredenciaisInvalidas()
        espera = self.espera_bloqueio(login)
        if espera > 0:   # vale para qualquer login, existente ou não, para não revelar quem existe
            raise LimiteExcedido("Muitas tentativas. Aguarde antes de tentar de novo.", espera_seg=espera)

        usuario = self.repo.por_login(login)
        if usuario is None:
            politica.gasta_tempo_de_verificacao(senha)
        if usuario is None or not politica.confere(usuario.senha_hash, senha):
            self.limitador.registrar(login)
            raise CredenciaisInvalidas()

        self.limitador.limpar(login)
        return usuario
