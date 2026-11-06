"""Consultas de agregação do dashboard. Tudo parte de `resposta` (juntando partida, coleta, campus e curso) e os
filtros entram num único lugar (`_base`), para KPIs, gráficos e tabelas sempre concordarem entre si.

Contagens e somas vão no SQL; só a mediana do tempo é calculada em Python, porque o SQLite não tem percentil."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import NamedTuple, Optional

from sqlalchemy import Select, case, distinct, func, select
from sqlalchemy.orm import Session

from app.models import Campus, Coleta, Curso, Partida, Pergunta, Resposta


class Dim(NamedTuple):
    id: object       # expressão que identifica a categoria (e que agrupa)
    rotulo: object   # expressão do nome mostrado


DIMENSOES: dict[str, Dim] = {
    "campus": Dim(Campus.id, Campus.nome),
    "curso": Dim(Curso.id, Curso.nome),
    "ano": Dim(Coleta.ano, Coleta.ano),
    "periodo": Dim(Coleta.periodo, Coleta.periodo),
    "coleta": Dim(Coleta.id, Coleta.codigo),
    "grupo": Dim(Resposta.grupo_nome, Resposta.grupo_nome),
    "questao": Dim(Resposta.pergunta_numero, Resposta.pergunta_titulo),
}


@dataclass(frozen=True)
class Filtros:
    """Recorte pedido. `inicio` e `fim` já são instantes UTC (fim exclusivo); o service converte os dias."""
    questionario_id: int
    coletas: tuple[str, ...] = ()
    campus: tuple[int, ...] = ()
    curso: tuple[int, ...] = ()
    ano: tuple[int, ...] = ()
    periodo: tuple[int, ...] = ()
    grupo: tuple[str, ...] = ()
    questao: tuple[int, ...] = ()
    inicio: Optional[datetime] = None
    fim: Optional[datetime] = None

    def sem(self, *dimensoes: str) -> "Filtros":
        """O mesmo recorte sem as dimensões dadas (o gráfico não ignora a si mesmo só na visão dele)."""
        return replace(self, **{("coletas" if d == "coleta" else d): () for d in dimensoes})


@dataclass
class Linha:
    chave: tuple
    rotulo: tuple
    respostas: int = 0
    acertos: int = 0
    respondentes: int = 0
    tempos: list[int] = field(default_factory=list)


class DashboardRepo:
    def __init__(self, sessao: Session):
        self.s = sessao

    @staticmethod
    def _base(sel: Select, f: Filtros) -> Select:
        sel = (sel.select_from(Resposta)
               .join(Partida, Resposta.partida_id == Partida.id)
               .join(Coleta, Partida.coleta_id == Coleta.id)
               .join(Campus, Coleta.campus_id == Campus.id)
               .join(Curso, Coleta.curso_id == Curso.id)
               .where(Coleta.questionario_id == f.questionario_id))
        for dimensao, valores in (("coleta", f.coletas), ("campus", f.campus), ("curso", f.curso), ("ano", f.ano),
                                  ("periodo", f.periodo), ("grupo", f.grupo), ("questao", f.questao)):
            if valores:
                sel = sel.where(DIMENSOES[dimensao].id.in_(valores) if dimensao != "coleta" else Coleta.codigo.in_(valores))
        if f.inicio:
            sel = sel.where(Partida.finalizada_em >= f.inicio)
        if f.fim:
            sel = sel.where(Partida.finalizada_em < f.fim)
        return sel

    def agregados(self, f: Filtros, dims: tuple[str, ...] = (), tempos: bool = True) -> list[Linha]:
        """Respostas, acertos e respondentes por categoria (uma linha só, sem `dims`). Com `tempos`, traz também os
        tempos de cada categoria (a mediana é calculada depois); quem não mostra o tempo pode pular essa leitura, que é a mais cara."""
        ds = [DIMENSOES[d] for d in dims]
        ids = [d.id for d in ds]
        sel = select(*ids, *[func.max(d.rotulo) for d in ds], func.count(Resposta.id),
                     func.coalesce(func.sum(case((Resposta.acertou, 1), else_=0)), 0),
                     func.count(distinct(Resposta.partida_id)))
        sel = self._base(sel, f)
        if ids:
            sel = sel.group_by(*ids)
        n = len(ids)
        linhas = {tuple(r[:n]): Linha(tuple(r[:n]), tuple(r[n:2 * n]), int(r[2 * n]), int(r[2 * n + 1]), int(r[2 * n + 2]))
                  for r in self.s.execute(sel).all()}
        if not ids and not linhas:
            linhas[()] = Linha((), ())
        if tempos:
            por_chave = defaultdict(list)
            for r in self.s.execute(self._base(select(*ids, Resposta.tempo_ms), f)).all():
                por_chave[tuple(r[:n])].append(int(r[n]))
            for chave, linha in linhas.items():
                linha.tempos = por_chave.get(chave, [])
        return list(linhas.values())

    def partidas_finalizadas(self, f: Filtros) -> list[datetime]:
        """Instante de cada partida que tem ao menos uma resposta dentro do recorte."""
        sel = self._base(select(Partida.id, Partida.finalizada_em).distinct(), f)
        return [r[1] for r in self.s.execute(sel).all()]

    def distribuicao(self, f: Filtros, numero: int) -> dict[str, int]:
        """Quantas vezes cada letra foi escolhida na questão `numero` (as demais restrições do recorte valem)."""
        sel = select(Resposta.alternativa_letra, func.count()).where(Resposta.pergunta_numero == numero)
        return dict(self.s.execute(self._base(sel, f.sem("questao")).group_by(Resposta.alternativa_letra)).all())

    def pergunta(self, questionario_id: int, numero: int) -> Optional[Pergunta]:
        return self.s.scalar(select(Pergunta).where(Pergunta.questionario_id == questionario_id, Pergunta.numero == numero))

    def partidas_por_questionario(self) -> dict[int, int]:
        sel = (select(Coleta.questionario_id, func.count()).select_from(Partida)
               .join(Coleta, Partida.coleta_id == Coleta.id).group_by(Coleta.questionario_id))
        return dict(self.s.execute(sel).all())

    def valores_das_coletas(self, questionario_id: int) -> list[Coleta]:
        return list(self.s.scalars(select(Coleta).where(Coleta.questionario_id == questionario_id).order_by(Coleta.id)))
