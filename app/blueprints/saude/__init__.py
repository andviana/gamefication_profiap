"""Verificação de saúde (pública, sem dados sensíveis): usada por monitoramento e pelo Nginx."""
from __future__ import annotations

from flask import Blueprint, current_app, jsonify
from sqlalchemy import text

from app import db_schema
from app.extensions import db

bp = Blueprint("saude", __name__)


@bp.get("/saude")
def saude():
    settings = current_app.extensions["settings"]
    corpo = {"status": "ok", "ambiente": settings.app_env, "banco": "ok", "schema": None}
    codigo = 200
    try:
        db.session.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 - qualquer falha de conexão degrada o status
        current_app.logger.exception("Falha ao consultar o banco em /saude")
        corpo.update(status="indisponivel", banco="erro")
        return jsonify(corpo), 503
    try:
        corpo["schema"] = db_schema.status_schema()
    except Exception:  # noqa: BLE001
        current_app.logger.exception("Falha ao verificar o schema em /saude")
        corpo["schema"] = "indisponivel"
    if corpo["schema"] in (db_schema.AUSENTE, db_schema.DESATUALIZADO, "indisponivel"):
        corpo["status"] = "degradado"
        codigo = 503
    return jsonify(corpo), codigo
