"""token de sessao do usuario

Revision ID: beafbd7d3252
Revises: b1ce84a00cae
Create Date: 2026-11-05 15:44:42.865293

Adiciona `usuario.sessao_token` (NOT NULL). Usuários que já existam recebem um token próprio antes da coluna
virar obrigatória; por isso a coluna nasce nula, é preenchida e só então é travada.
"""
import secrets

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'beafbd7d3252'
down_revision = 'b1ce84a00cae'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('usuario', schema=None) as batch_op:
        batch_op.add_column(sa.Column('sessao_token', sa.String(length=32), nullable=True))

    conexao = op.get_bind()
    for (usuario_id,) in conexao.execute(sa.text('SELECT id FROM usuario')).fetchall():
        conexao.execute(sa.text('UPDATE usuario SET sessao_token = :t WHERE id = :i'),
                        {'t': secrets.token_hex(16), 'i': usuario_id})

    with op.batch_alter_table('usuario', schema=None) as batch_op:
        batch_op.alter_column('sessao_token', existing_type=sa.String(length=32), nullable=False)


def downgrade():
    with op.batch_alter_table('usuario', schema=None) as batch_op:
        batch_op.drop_column('sessao_token')
