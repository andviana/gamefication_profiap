"""Comandos de linha de comando. Os de produção ficam restritos à recuperação de acesso (Fase 2);
os demais são ferramentas de desenvolvimento e se recusam a rodar em produção."""
from __future__ import annotations

import click
from flask import Flask, current_app
from flask.cli import with_appcontext

from app.extensions import db
from app.models import Campus, Curso

CAMPI_EXEMPLO = ("Belém", "Paragominas", "Tomé-Açu", "Parauapebas")
CURSOS_EXEMPLO = ("Sistemas de Informação", "Pedagogia", "Agronomia", "Letras")


def semear_desenvolvimento() -> dict[str, int]:
    """Cria campi e cursos de exemplo que ainda não existem. Idempotente. Devolve quantos foram criados."""
    criados = {"campus": 0, "curso": 0}
    for modelo, chave, nomes in ((Campus, "campus", CAMPI_EXEMPLO), (Curso, "curso", CURSOS_EXEMPLO)):
        existentes = {nome for (nome,) in db.session.query(modelo.nome)}
        for nome in nomes:
            if nome not in existentes:
                db.session.add(modelo(nome=nome))
                criados[chave] += 1
    db.session.commit()
    return criados


@click.command("seed-dev")
@with_appcontext
def seed_dev_cmd() -> None:
    """Cadastra campi e cursos de exemplo (somente desenvolvimento e teste)."""
    if current_app.extensions["settings"].eh_producao:
        raise click.ClickException("seed-dev não pode ser executado em produção.")
    criados = semear_desenvolvimento()
    click.echo(f"Campi criados: {criados['campus']}. Cursos criados: {criados['curso']}.")


@click.command("redefinir-superadmin")
@with_appcontext
def redefinir_superadmin_cmd() -> None:
    """Redefine a senha do super admin raiz. Recuperação de acesso: exige acesso ao shell do servidor."""
    from app.errors import ErroDominio
    container = current_app.extensions["container"]
    senha = click.prompt("Nova senha", hide_input=True, confirmation_prompt=True)
    try:
        raiz = container.usuarios.redefinir_senha_da_raiz(senha)
    except ErroDominio as erro:
        raise click.ClickException(erro.mensagem)
    click.echo(f"Senha de {raiz.login} redefinida. As sessões abertas foram encerradas.")


def registrar_comandos(app: Flask) -> None:
    app.cli.add_command(seed_dev_cmd)
    app.cli.add_command(redefinir_superadmin_cmd)
