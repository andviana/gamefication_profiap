"""Variáveis, filtros e funções disponíveis em todos os templates."""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from flask import Flask, url_for

from app import permissoes


def registrar_contexto(app: Flask) -> None:
    settings = app.extensions["settings"]
    fuso = ZoneInfo(settings.timezone)

    @app.template_filter("data_local")
    def data_local(valor: datetime | None, formato: str = "%d/%m/%Y") -> str:
        return valor.astimezone(fuso).strftime(formato) if valor else ""

    @app.template_filter("data_br")
    def data_br(valor: date | None) -> str:
        return valor.strftime("%d/%m/%Y") if valor else ""

    @app.context_processor
    def _contexto():
        def logo(caminho: str):
            return url_for("static", filename=caminho) if caminho else None
        return {
            "instituicao": {
                "nome": settings.instituicao_nome,
                "subtitulo": settings.instituicao_subtitulo,
                "logos": [u for u in (logo(settings.logo_instituicao), logo(settings.logo_programa)) if u],
            },
            "pode_gerenciar": permissoes.pode_gerenciar,
            "pode_promover": permissoes.pode_promover,
            "pode_revogar": permissoes.pode_revogar,
        }
