"""Perguntas e alternativas de um questionário, com as travas de estrutura.

- Rascunho e "em coleta": qualquer alteração (adicionar, remover, trocar gabarito, número, grupo).
- Travado (já há respostas): só texto (enunciado, título, autoajuda, alternativas e feedbacks). Estrutura
  (adicionar/remover perguntas ou alternativas, número, grupo, gabarito) exige duplicar o questionário; o gabarito
  pode ser trocado por um super admin, com recálculo das respostas já gravadas.
O jogo suporta de 2 a 4 alternativas (letras A a D).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.exc import IntegrityError

from app import auditoria
from app.errors import Conflito, Invalido, NaoEncontrado, Proibido
from app.models import Alternativa, Pergunta
from app.repositories.questionarios import QuestionarioRepo
from app.repositories.referencias import ReferenciaRepo
from app.services.questionarios import TRAVADO, QuestionarioService

LETRAS = "ABCD"
MIN_ALTERNATIVAS, MAX_ALTERNATIVAS = 2, len(LETRAS)
MAX_TEXTO, MAX_TITULO, MAX_AUTOAJUDA, MAX_ALT = 5000, 160, 2000, 1000


@dataclass
class DadosAlternativa:
    texto: str
    correta: bool = False
    texto_acerto: Optional[str] = None
    texto_erro: Optional[str] = None


@dataclass
class DadosPergunta:
    texto: str
    titulo: str
    grupo_id: int
    alternativas: list[DadosAlternativa] = field(default_factory=list)
    autoajuda: Optional[str] = None
    numero: Optional[int] = None   # vazio na criação = próximo número livre


def _limpa(texto: Optional[str]) -> Optional[str]:
    texto = (texto or "").strip()
    return texto or None


class PerguntaService:
    def __init__(self, repo: QuestionarioRepo, questionarios: QuestionarioService, grupos: ReferenciaRepo):
        self.repo = repo
        self.questionarios = questionarios
        self.grupos = grupos

    # ---- consultas e utilitários --------------------------------------------------------------
    def obter(self, questionario_id: int, pergunta_id: int) -> Pergunta:
        pergunta = self.repo.pergunta(pergunta_id)
        if pergunta is None or pergunta.questionario_id != questionario_id:
            raise NaoEncontrado("Pergunta não encontrada neste questionário.")
        return pergunta

    def _travado(self, questionario) -> bool:
        return self.questionarios.resumo(questionario).estado == TRAVADO

    def _estrutura_livre(self, questionario) -> None:
        if self._travado(questionario):
            raise Conflito("Este questionário já tem respostas: a estrutura está travada. "
                           "Para adicionar ou remover perguntas, duplique o questionário e edite a cópia.")

    def _commit(self) -> None:
        try:
            self.repo.commit()
        except IntegrityError as erro:
            self.repo.rollback()
            raise Conflito("A operação conflita com os dados existentes.") from erro

    # ---- validação ----------------------------------------------------------------------------
    def _valida(self, dados: DadosPergunta, grupo_atual_id: Optional[int] = None) -> None:
        texto, titulo = (dados.texto or "").strip(), (dados.titulo or "").strip()
        if not texto:
            raise Invalido("O enunciado é obrigatório.", campo="texto")
        if len(texto) > MAX_TEXTO:
            raise Invalido(f"O enunciado deve ter no máximo {MAX_TEXTO} caracteres.", campo="texto")
        if not titulo:
            raise Invalido("O título é obrigatório.", campo="titulo")
        if len(titulo) > MAX_TITULO:
            raise Invalido(f"O título deve ter no máximo {MAX_TITULO} caracteres.", campo="titulo")
        if dados.autoajuda and len(dados.autoajuda.strip()) > MAX_AUTOAJUDA:
            raise Invalido(f"A dica deve ter no máximo {MAX_AUTOAJUDA} caracteres.", campo="autoajuda")
        grupo = self.grupos.por_id(dados.grupo_id) if dados.grupo_id else None
        if grupo is None:
            raise Invalido("Escolha o grupo da pergunta.", campo="grupo_id")
        if not grupo.ativo and grupo.id != grupo_atual_id:
            raise Invalido("Este grupo está inativo. Escolha outro ou reative-o em Cadastros.", campo="grupo_id")
        if dados.numero is not None and dados.numero < 1:
            raise Invalido("O número da pergunta deve ser 1 ou maior.", campo="numero")
        alts = dados.alternativas
        if not MIN_ALTERNATIVAS <= len(alts) <= MAX_ALTERNATIVAS:
            raise Invalido(f"A pergunta deve ter de {MIN_ALTERNATIVAS} a {MAX_ALTERNATIVAS} alternativas.", campo="alternativas")
        for i, a in enumerate(alts):
            if not (a.texto or "").strip():
                raise Invalido(f"O texto da alternativa {LETRAS[i]} é obrigatório.", campo=f"alt_texto_{i}")
            if len(a.texto.strip()) > MAX_ALT:
                raise Invalido(f"A alternativa {LETRAS[i]} deve ter no máximo {MAX_ALT} caracteres.", campo=f"alt_texto_{i}")
        corretas = [i for i, a in enumerate(alts) if a.correta]
        if len(corretas) != 1:
            raise Invalido("Marque exatamente uma alternativa como correta.", campo="correta")

    # ---- criação, edição e remoção -------------------------------------------------------------
    def criar(self, ator, questionario_id: int, dados: DadosPergunta) -> Pergunta:
        q = self.questionarios.obter(questionario_id)
        self._estrutura_livre(q)
        self._valida(dados)
        numero = dados.numero or self.repo.proximo_numero(q.id)
        if self.repo.numero_em_uso(q.id, numero):
            raise Conflito(f"Já existe a pergunta de número {numero} neste questionário.", campo="numero")
        pergunta = Pergunta(questionario_id=q.id, numero=numero, texto=dados.texto.strip(), titulo=dados.titulo.strip(),
                            grupo_id=dados.grupo_id, autoajuda=_limpa(dados.autoajuda))
        for i, a in enumerate(dados.alternativas):
            pergunta.alternativas.append(Alternativa(
                letra=LETRAS[i], texto=a.texto.strip(), correta=a.correta,
                texto_acerto=_limpa(a.texto_acerto), texto_erro=_limpa(a.texto_erro)))
        self.repo.adicionar(pergunta)
        self._commit()
        auditoria.registrar("pergunta_criada", ator, questionario=q.nome, numero=numero)
        return pergunta

    def editar(self, ator, questionario_id: int, pergunta_id: int, dados: DadosPergunta) -> Pergunta:
        q = self.questionarios.obter(questionario_id)
        pergunta = self.obter(q.id, pergunta_id)
        travado = self._travado(q)
        self._valida(dados, grupo_atual_id=pergunta.grupo_id)
        numero = dados.numero or pergunta.numero
        existentes = list(pergunta.alternativas)

        if travado:   # só texto: o que muda a estrutura ou o gabarito é recusado
            if numero != pergunta.numero or dados.grupo_id != pergunta.grupo_id:
                raise Conflito("Com respostas gravadas, o número e o grupo da pergunta não podem mudar. "
                               "Duplique o questionário para alterar a estrutura.")
            if len(dados.alternativas) != len(existentes):
                raise Conflito("Com respostas gravadas, não é possível adicionar nem remover alternativas.")
            if [a.correta for a in dados.alternativas] != [a.correta for a in existentes]:
                raise Conflito("Com respostas gravadas, o gabarito só muda pela ação “Trocar gabarito” (super admin).")
        elif self.repo.numero_em_uso(q.id, numero, ignorar_id=pergunta.id):
            raise Conflito(f"Já existe a pergunta de número {numero} neste questionário.", campo="numero")

        pergunta.numero, pergunta.grupo_id = numero, dados.grupo_id
        pergunta.texto, pergunta.titulo, pergunta.autoajuda = dados.texto.strip(), dados.titulo.strip(), _limpa(dados.autoajuda)

        # alternativas por posição (A, B, C, D): atualiza as que existem, cria as novas, remove as que sobraram
        if not travado:
            for a in existentes:                 # primeiro desmarca o gabarito antigo (índice parcial: uma correta só)
                a.correta = False
            self.repo.flush()
        for i, nova in enumerate(dados.alternativas):
            if i < len(existentes):
                alvo = existentes[i]
            else:
                alvo = Alternativa(letra=LETRAS[i], pergunta_id=pergunta.id)
                pergunta.alternativas.append(alvo)
            alvo.texto, alvo.texto_acerto, alvo.texto_erro = nova.texto.strip(), _limpa(nova.texto_acerto), _limpa(nova.texto_erro)
            if not travado:
                alvo.correta = nova.correta
        for sobra in existentes[len(dados.alternativas):]:
            pergunta.alternativas.remove(sobra)
        self._commit()
        auditoria.registrar("pergunta_editada", ator, questionario=q.nome, numero=pergunta.numero, travado=travado)
        return pergunta

    def excluir(self, ator, questionario_id: int, pergunta_id: int) -> None:
        q = self.questionarios.obter(questionario_id)
        pergunta = self.obter(q.id, pergunta_id)
        self._estrutura_livre(q)
        numero = pergunta.numero
        self.repo.remover(pergunta)
        self._commit()
        auditoria.registrar("pergunta_excluida", ator, questionario=q.nome, numero=numero)

    # ---- gabarito ------------------------------------------------------------------------------
    def trocar_gabarito(self, ator, questionario_id: int, pergunta_id: int, letra: str) -> tuple[int, int]:
        """Troca a alternativa correta. Se já há respostas, recalcula `acertou` e o total de acertos das partidas
        afetadas, numa única transação. Só super admin. Devolve (respostas, partidas) recalculadas."""
        if not getattr(ator, "eh_superadmin", False):
            raise Proibido("Só super admin troca o gabarito de uma pergunta.")
        q = self.questionarios.obter(questionario_id)
        pergunta = self.obter(q.id, pergunta_id)
        nova = next((a for a in pergunta.alternativas if a.letra == (letra or "").upper()), None)
        if nova is None:
            raise Invalido("Escolha uma das alternativas da pergunta.", campo="correta")
        antiga = next((a for a in pergunta.alternativas if a.correta), None)
        if antiga is not None and antiga.id == nova.id:
            raise Invalido("Esta já é a alternativa correta.", campo="correta")
        n_respostas, n_partidas = self.repo.respostas_da_pergunta(pergunta.id)
        if antiga is not None:
            antiga.correta = False
            self.repo.flush()                    # índice parcial: nunca duas corretas ao mesmo tempo
        nova.correta = True
        self.repo.flush()
        if n_respostas:
            self.repo.recalcular_acertos(pergunta.id, nova.id)
        self._commit()
        auditoria.registrar("gabarito_trocado", ator, questionario=q.nome, numero=pergunta.numero,
                            de=getattr(antiga, "letra", "-"), para=nova.letra, respostas=n_respostas, partidas=n_partidas)
        return n_respostas, n_partidas
