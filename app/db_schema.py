"""Verifica se o schema do banco está na revisão mais recente das migrações (Alembic)."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

from app import config
from app.extensions import db

# resultados de status_schema()
SEM_MIGRACOES = "sem_migracoes"   # ainda não há revisões (início do desenvolvimento)
OK = "ok"
AUSENTE = "ausente"               # há revisões, mas o banco nunca foi migrado
DESATUALIZADO = "desatualizado"   # o banco está numa revisão anterior à mais recente


class SchemaDesatualizado(RuntimeError):
    """O banco não está na revisão atual. A mensagem diz como corrigir."""


def _script(diretorio: Optional[Path] = None) -> Optional[ScriptDirectory]:
    # lê MIGRATIONS_DIR do módulo a cada chamada (permite trocar o diretório nos testes)
    diretorio = diretorio or config.MIGRATIONS_DIR
    if not (diretorio / "env.py").exists():
        return None
    cfg = Config()
    cfg.set_main_option("script_location", str(diretorio))
    return ScriptDirectory.from_config(cfg)


def status_schema(diretorio: Optional[Path] = None) -> str:
    """Compara a revisão do banco com a mais recente. Precisa de um app context ativo."""
    script = _script(diretorio)
    if script is None or not script.get_heads():
        return SEM_MIGRACOES
    with db.engine.connect() as conexao:
        atuais = set(MigrationContext.configure(conexao).get_current_heads())
    if not atuais:
        return AUSENTE
    return OK if atuais == set(script.get_heads()) else DESATUALIZADO


def verificar_schema_atualizado(diretorio: Optional[Path] = None) -> str:
    """Falha cedo, com mensagem clara, se o banco não estiver atualizado."""
    estado = status_schema(diretorio)
    if estado in (AUSENTE, DESATUALIZADO):
        motivo = "não foi criado" if estado == AUSENTE else "está desatualizado"
        raise SchemaDesatualizado(
            f"O schema do banco {motivo}. Execute `flask --app app:create_app db upgrade` e inicie de novo."
        )
    return estado
