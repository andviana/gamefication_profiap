"""Modelos. Importar este pacote registra todas as tabelas no metadata (usado por migrações e testes)."""
from app.models.coleta import Coleta, Partida, Resposta
from app.models.controle import ImportacaoPrevia, TentativaFalha
from app.models.questionario import Alternativa, Pergunta, Questionario
from app.models.referencias import Campus, Curso, Grupo
from app.models.usuario import Usuario

__all__ = [
    "Alternativa", "Campus", "Coleta", "Curso", "Grupo", "ImportacaoPrevia", "Partida", "Pergunta",
    "Questionario", "Resposta", "TentativaFalha", "Usuario",
]
