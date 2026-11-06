"""Configuração da aplicação: lida do ENV uma única vez, validada e imutável (singleton)."""
from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

BASE_DIR = Path(__file__).resolve().parent.parent
INSTANCE_DIR = BASE_DIR / "instance"
MIGRATIONS_DIR = BASE_DIR / "migrations"

AMBIENTES = ("development", "testing", "production")
SECRET_PADRAO = "dev-inseguro-troque-em-producao"
SAL_PADRAO = "dev-sal-do-gabarito"
LOG_NIVEIS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


class ConfiguracaoInvalida(Exception):
    """A configuração do ENV é inválida; a mensagem lista todos os problemas de uma vez."""

    def __init__(self, problemas: list[str]):
        self.problemas = problemas
        super().__init__("Configuração inválida:\n- " + "\n- ".join(problemas))


def _normaliza_url_banco(url: str) -> str:
    """postgres:// e postgresql:// passam a usar o driver psycopg (v3)."""
    for antigo in ("postgres://", "postgresql://"):
        if url.startswith(antigo):
            return "postgresql+psycopg://" + url[len(antigo):]
    return url


@dataclass(frozen=True)
class Settings:
    app_env: str
    secret_key: str
    database_url: str
    gabarito_sal: str
    timezone: str
    locale: str
    log_level: str
    # sessão e login
    session_horas: int
    login_max_falhas: int
    login_bloqueio_seg: int
    # código de acesso (rate limit só sobre tentativas falhas, por IP)
    rate_limit_falhas: int
    rate_limit_janela_seg: int
    rate_limit_bloqueio_seg: int
    # importação e upload
    previa_validade_min: int
    upload_max_bytes: int
    # nº de proxies reversos confiáveis à frente do app (X-Forwarded-For)
    proxies_confiaveis: int
    # identidade da instituição (cabeçalho do painel e do jogo)
    instituicao_nome: str
    instituicao_subtitulo: str
    logo_instituicao: str
    logo_programa: str

    @property
    def eh_producao(self) -> bool:
        return self.app_env == "production"

    @property
    def eh_teste(self) -> bool:
        return self.app_env == "testing"

    @property
    def eh_desenvolvimento(self) -> bool:
        return self.app_env == "development"

    @property
    def cookie_seguro(self) -> bool:
        return self.eh_producao

    @property
    def usa_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @classmethod
    def from_env(cls, environ: Optional[Mapping[str, str]] = None) -> "Settings":
        """Constrói e valida a configuração. Reúne todos os problemas antes de falhar."""
        if environ is None:
            import os
            environ = os.environ
        problemas: list[str] = []

        def texto(chave: str, padrao: str = "") -> str:
            return (environ.get(chave) or padrao).strip()

        def inteiro(chave: str, padrao: int, minimo: int = 1) -> int:
            bruto = texto(chave)
            if not bruto:
                return padrao
            try:
                valor = int(bruto)
            except ValueError:
                problemas.append(f"{chave} deve ser um número inteiro (recebido: {bruto!r})")
                return padrao
            if valor < minimo:
                problemas.append(f"{chave} deve ser >= {minimo} (recebido: {valor})")
                return padrao
            return valor

        app_env = texto("APP_ENV", "development").lower()
        if app_env not in AMBIENTES:
            problemas.append(f"APP_ENV deve ser um de {', '.join(AMBIENTES)} (recebido: {app_env!r})")
            app_env = "development"
        producao = app_env == "production"

        # banco: padrão só em desenvolvimento/teste; produção exige URL explícita
        url = texto("DATABASE_URL")
        if not url:
            if producao:
                problemas.append("DATABASE_URL é obrigatória em produção")
            url = "sqlite:///:memory:" if app_env == "testing" else f"sqlite:///{INSTANCE_DIR / 'dev.db'}"
        else:
            url = _normaliza_url_banco(url)
            if producao and not url.startswith("postgresql"):
                problemas.append("Em produção o banco deve ser PostgreSQL (DATABASE_URL com postgresql://)")

        secret = texto("SECRET_KEY", SECRET_PADRAO)
        sal = texto("GABARITO_SAL", SAL_PADRAO)
        if producao:
            if secret == SECRET_PADRAO or len(secret) < 32:
                problemas.append("SECRET_KEY deve ser definida em produção, com pelo menos 32 caracteres")
            if sal == SAL_PADRAO or len(sal) < 16:
                problemas.append("GABARITO_SAL deve ser definido em produção, com pelo menos 16 caracteres")

        timezone = texto("TIMEZONE", "America/Belem")
        try:
            ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, ValueError):
            problemas.append(f"TIMEZONE desconhecido: {timezone!r}")

        log_level = texto("LOG_LEVEL", "INFO").upper()
        if log_level not in LOG_NIVEIS:
            problemas.append(f"LOG_LEVEL deve ser um de {', '.join(LOG_NIVEIS)} (recebido: {log_level!r})")
            log_level = "INFO"

        settings = cls(
            app_env=app_env,
            secret_key=secret,
            database_url=url,
            gabarito_sal=sal,
            timezone=timezone,
            locale=texto("LOCALE", "pt-BR"),
            log_level=log_level,
            session_horas=inteiro("SESSION_HORAS", 8),
            login_max_falhas=inteiro("LOGIN_MAX_FALHAS", 5),
            login_bloqueio_seg=inteiro("LOGIN_BLOQUEIO_SEG", 600),
            rate_limit_falhas=inteiro("RATE_LIMIT_FALHAS", 10),
            rate_limit_janela_seg=inteiro("RATE_LIMIT_JANELA_SEG", 60),
            rate_limit_bloqueio_seg=inteiro("RATE_LIMIT_BLOQUEIO_SEG", 300),
            previa_validade_min=inteiro("PREVIA_VALIDADE_MIN", 15),
            upload_max_bytes=inteiro("UPLOAD_MAX_BYTES", 2 * 1024 * 1024),
            proxies_confiaveis=inteiro("PROXIES_CONFIAVEIS", 0, minimo=0),
            instituicao_nome=texto("INSTITUICAO_NOME", "TechQuiz"),
            instituicao_subtitulo=texto("INSTITUICAO_SUBTITULO"),
            logo_instituicao=texto("LOGO_INSTITUICAO"),
            logo_programa=texto("LOGO_PROGRAMA"),
        )
        if problemas:
            raise ConfiguracaoInvalida(problemas)
        return settings


# ---- singleton ---------------------------------------------------------------------------
_instancia: Optional[Settings] = None
_trava = threading.Lock()


def get_settings() -> Settings:
    """Devolve a configuração única do processo (carrega o .env e o ENV na primeira chamada)."""
    global _instancia
    if _instancia is None:
        with _trava:
            if _instancia is None:
                from dotenv import load_dotenv
                load_dotenv(BASE_DIR / ".env", override=False)
                _instancia = Settings.from_env()
    return _instancia


def reset_settings() -> None:
    """Descarta a instância (uso em testes)."""
    global _instancia
    with _trava:
        _instancia = None
