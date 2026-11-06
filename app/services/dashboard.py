"""Dashboard: métricas por questionário, sempre sobre as respostas gravadas (snapshot de número, título e grupo).

Definições (plano, seção 11.2): respondente = partida; erro/acerto = `acertou` calculado pelo servidor; % de erro é
ponderado (erros ÷ respostas do recorte, nunca média de médias); tempo = mediana de `tempo_ms`."""
from __future__ import annotations

import csv
import io
from collections import Counter
from dataclasses import replace
from datetime import date, datetime, time, timedelta, timezone
from statistics import median
from typing import Any, Mapping, Optional
from zoneinfo import ZoneInfo

from app.config import Settings
from app.errors import Invalido, NaoEncontrado
from app.repositories.dashboard import DashboardRepo, Filtros, Linha
from app.services.questionarios import QuestionarioService

ABAS = ("questao", "grupo", "campus", "curso", "ano", "periodo", "coleta")
DIMS_COMPARATIVO = ("campus", "curso", "ano", "periodo")
ROTULO_ABA = {"questao": "Questão", "grupo": "Grupo", "campus": "Campus", "curso": "Curso", "ano": "Ano",
              "periodo": "Período", "coleta": "Coleta"}
MAX_VALORES = 200            # por filtro, para a query string não virar vetor de abuso
PERIODOS_ROTULO = {1: "1º período", 2: "2º período"}


def pct(parte: int, total: int) -> Optional[float]:
    return round(100 * parte / total, 1) if total else None


def _mediana(tempos: list[int]) -> Optional[int]:
    return int(round(median(tempos))) if tempos else None


class DashboardService:
    def __init__(self, repo: DashboardRepo, questionarios: QuestionarioService, settings: Settings, relogio=None):
        self.repo = repo
        self.questionarios = questionarios
        self.settings = settings
        self.relogio = relogio or (lambda: datetime.now(timezone.utc))

    @property
    def _fuso(self) -> ZoneInfo:
        return ZoneInfo(self.settings.timezone)

    # ---- filtros ------------------------------------------------------------------------------
    def filtros(self, args: Mapping[str, Any]) -> Filtros:
        """Lê a query string (valores repetidos ou separados por vírgula). Valor inválido é 422, nunca ignorado."""
        def lista(nome: str) -> list[str]:
            brutos = args.getlist(nome) if hasattr(args, "getlist") else list(args.get(nome) or [])
            valores = [v.strip() for b in brutos for v in str(b).split(",") if v.strip()]
            if len(valores) > MAX_VALORES:
                raise Invalido(f"Filtro '{nome}' com valores demais.", campo=nome)
            return valores

        def inteiros(nome: str) -> tuple[int, ...]:
            try:
                return tuple(sorted({int(v) for v in lista(nome)}))
            except ValueError:
                raise Invalido(f"Filtro '{nome}' deve conter números inteiros.", campo=nome) from None

        def dia(nome: str) -> Optional[date]:
            bruto = (args.get(nome) or "").strip()
            if not bruto:
                return None
            try:
                return date.fromisoformat(bruto)
            except ValueError:
                raise Invalido(f"Filtro '{nome}' deve ser uma data AAAA-MM-DD.", campo=nome) from None

        qid = inteiros("questionario")
        if len(qid) != 1:
            raise Invalido("Escolha um questionário.", campo="questionario")
        self.questionarios.obter(qid[0])   # 404 se não existir
        de, ate = dia("de"), dia("ate")
        bruto_dias = (args.get("dias") or "").strip()
        if bruto_dias:
            if not bruto_dias.isdigit() or not 1 <= int(bruto_dias) <= 3650:
                raise Invalido("Filtro 'dias' deve ser um número de 1 a 3650.", campo="dias")
            hoje = self.relogio().astimezone(self._fuso).date()
            de = hoje - timedelta(days=int(bruto_dias) - 1)
        if de and ate and de > ate:
            raise Invalido("A data inicial é posterior à final.", campo="de")
        fuso = self._fuso
        return Filtros(
            questionario_id=qid[0],
            coletas=tuple(sorted({v.upper() for v in lista("coleta")})),
            campus=inteiros("campus"), curso=inteiros("curso"), ano=inteiros("ano"), periodo=inteiros("periodo"),
            grupo=tuple(sorted(set(lista("grupo")))), questao=inteiros("questao"),
            inicio=datetime.combine(de, time.min, fuso).astimezone(timezone.utc) if de else None,
            fim=datetime.combine(ate + timedelta(days=1), time.min, fuso).astimezone(timezone.utc) if ate else None,
        )

    # ---- seleção do questionário --------------------------------------------------------------
    def cartoes(self) -> list[dict]:
        """Um cartão por questionário, para a escolha inicial (a página não abre com nenhum selecionado)."""
        cartoes = []
        partidas = self.repo.partidas_por_questionario()
        for q, r in self.questionarios.listar():
            cartoes.append({
                "id": q.id, "nome": q.nome, "estado": r.estado, "n_perguntas": r.n_perguntas, "n_coletas": r.n_coletas,
                "n_respostas": r.n_respostas, "derivado_de": q.derivado_de.nome if q.derivado_de else None,
                "n_partidas": partidas.get(q.id, 0)})
        return cartoes

    def opcoes(self, questionario_id: int) -> dict:
        """Valores que existem nas coletas do questionário (e as perguntas), para montar a barra de filtros."""
        q = self.questionarios.obter(questionario_id)
        coletas = self.repo.valores_das_coletas(q.id)
        unicos = lambda itens: sorted(set(itens))   # noqa: E731
        return {
            "questionario": {"id": q.id, "nome": q.nome, "estado": self.questionarios.resumo(q).estado},
            "coletas": [{"codigo": c.codigo, "campus": c.campus.nome, "curso": c.curso.nome, "ano": c.ano,
                         "periodo": c.periodo} for c in coletas],
            "campus": [{"id": i, "nome": n} for i, n in unicos({(c.campus_id, c.campus.nome) for c in coletas})],
            "curso": [{"id": i, "nome": n} for i, n in unicos({(c.curso_id, c.curso.nome) for c in coletas})],
            "ano": unicos({c.ano for c in coletas}),
            "periodo": [{"id": p, "nome": PERIODOS_ROTULO[p]} for p in unicos({c.periodo for c in coletas})],
            "grupo": unicos({p.grupo.nome for p in q.perguntas}),
            "questao": [{"numero": p.numero, "titulo": p.titulo, "grupo": p.grupo.nome} for p in q.perguntas],
        }

    # ---- formatação das linhas ----------------------------------------------------------------
    @staticmethod
    def _metricas(linha: Linha) -> dict:
        erros = linha.respostas - linha.acertos
        return {"respostas": linha.respostas, "acertos": linha.acertos, "erros": erros,
                "respondentes": linha.respondentes, "pct_acerto": pct(linha.acertos, linha.respostas),
                "pct_erro": pct(erros, linha.respostas), "tempo_mediano_ms": _mediana(linha.tempos)}

    def _categoria(self, dim: str, linha: Linha) -> dict:
        chave, rotulo = linha.chave[0], linha.rotulo[0]
        if dim == "questao":
            return {"numero": chave, "titulo": rotulo, "rotulo": f"Q{chave} · {rotulo}"}
        if dim == "periodo":
            return {"id": chave, "rotulo": PERIODOS_ROTULO.get(chave, str(chave))}
        if dim == "grupo":
            return {"id": chave, "rotulo": rotulo}
        if dim == "ano":
            return {"id": chave, "rotulo": str(chave)}
        return {"id": chave, "rotulo": rotulo}

    def _por_dimensao(self, f: Filtros, dim: str, tempos: bool = True) -> list[dict]:
        # o grupo de uma questão é fixo depois da 1ª resposta, então agrupar por (questão, grupo) dá uma linha por questão
        dims = ("questao", "grupo") if dim == "questao" else (dim,)
        linhas = []
        for ln in self.repo.agregados(f, dims, tempos):
            item = {**self._categoria(dim, ln), **self._metricas(ln)}
            if dim == "questao":
                item["grupo"] = ln.chave[1]
            linhas.append(item)
        return linhas

    @staticmethod
    def _dim_comparativo(dim: str) -> None:
        if dim not in DIMS_COMPARATIVO:
            raise Invalido(f"Dimensão desconhecida. Use: {', '.join(DIMS_COMPARATIVO)}.", campo="dim")

    # ---- endpoints ----------------------------------------------------------------------------
    def resumo(self, f: Filtros) -> dict:
        atual = self._metricas(self.repo.agregados(f)[0])
        geral = self._metricas(self.repo.agregados(Filtros(questionario_id=f.questionario_id), tempos=False)[0])
        return {**atual, "geral": geral}

    def questoes(self, f: Filtros, menor: bool = False, limite: Optional[int] = 10) -> dict:
        linhas = [x for x in self._por_dimensao(f.sem("questao"), "questao") if x["respostas"]]
        linhas.sort(key=lambda x: (-x["pct_erro"], x["numero"]))
        if menor:
            linhas.reverse()
        return {"total": len(linhas), "itens": linhas[:limite] if limite else linhas}

    def grupos(self, f: Filtros) -> dict:
        linhas = sorted((x for x in self._por_dimensao(f.sem("grupo"), "grupo", tempos=False) if x["respostas"]),
                        key=lambda x: (-x["pct_erro"], -x["respostas"], x["rotulo"]))
        return {"itens": linhas}

    def comparativo(self, f: Filtros, dim: str) -> dict:
        self._dim_comparativo(dim)
        sem = f.sem(dim)
        linhas = sorted((x for x in self._por_dimensao(sem, dim, tempos=False) if x["respostas"]),
                        key=lambda x: (-x["pct_erro"], x["rotulo"]))
        return {"dim": dim, "media_pct_erro": self._metricas(self.repo.agregados(sem, tempos=False)[0])["pct_erro"], "itens": linhas}

    def heatmap(self, f: Filtros, dim: str) -> dict:
        self._dim_comparativo(dim)
        sem = f.sem(dim, "grupo")
        celulas = []
        for ln in self.repo.agregados(sem, ("grupo", dim), tempos=False):
            m = self._metricas(ln)
            celulas.append({"grupo": ln.chave[0], "id": ln.chave[1],
                            "rotulo": self._categoria(dim, Linha(ln.chave[1:], ln.rotulo[1:]))["rotulo"],
                            "respostas": m["respostas"], "erros": m["erros"], "pct_erro": m["pct_erro"]})
        celulas.sort(key=lambda c: (c["grupo"], str(c["id"])))
        return {"dim": dim, "grupos": sorted({c["grupo"] for c in celulas}),
                "colunas": [{"id": i, "rotulo": r} for i, r in sorted({(c["id"], c["rotulo"]) for c in celulas}, key=lambda t: t[1])],
                "celulas": celulas}

    def questao(self, f: Filtros, numero: int) -> dict:
        pergunta = self.repo.pergunta(f.questionario_id, numero)
        if pergunta is None:
            raise NaoEncontrado("Questão não encontrada neste questionário.")
        so_ela = replace(f, questao=(numero,))
        metricas = self._metricas(self.repo.agregados(so_ela)[0])
        contagem = self.repo.distribuicao(f, numero)
        total = sum(contagem.values())
        alternativas = [{"letra": a.letra, "texto": a.texto, "correta": a.correta, "escolhas": contagem.get(a.letra, 0),
                         "pct": pct(contagem.get(a.letra, 0), total)} for a in pergunta.alternativas]
        return {"numero": pergunta.numero, "titulo": pergunta.titulo, "enunciado": pergunta.texto,
                "grupo": pergunta.grupo.nome, **metricas, "alternativas": alternativas}

    def evolucao(self, f: Filtros, passo: str = "semana") -> dict:
        if passo not in ("semana", "dia"):
            raise Invalido("O passo deve ser 'semana' ou 'dia'.", campo="passo")
        dias = Counter(m.astimezone(self._fuso).date() for m in self.repo.partidas_finalizadas(f))
        if passo == "semana":
            dias = self._semanas(dias)
        pontos = []
        if dias:
            passo_dias = 7 if passo == "semana" else 1
            atual, ultimo = min(dias), max(dias)
            while atual <= ultimo:
                pontos.append({"inicio": atual.isoformat(), "partidas": dias.get(atual, 0)})
                atual += timedelta(days=passo_dias)
        return {"passo": passo, "pontos": pontos, "total": sum(dias.values())}

    @staticmethod
    def _semanas(dias: Counter) -> Counter:
        semanas: Counter = Counter()
        for d, n in dias.items():
            semanas[d - timedelta(days=d.weekday())] += n   # segunda-feira
        return semanas

    # ---- tabela e exportação ------------------------------------------------------------------
    def tabela(self, f: Filtros, aba: str) -> dict:
        if aba not in ABAS:
            raise Invalido(f"Aba desconhecida. Use: {', '.join(ABAS)}.", campo="aba")
        itens = self._por_dimensao(f, aba)
        itens.sort(key=lambda x: x["numero"] if aba == "questao" else (str(x["id"]) if aba in ("ano", "periodo", "coleta") else x["rotulo"]))
        total = self._metricas(self.repo.agregados(f)[0])
        return {"aba": aba, "rotulo_aba": ROTULO_ABA[aba], "itens": itens, "totais": total}

    def csv(self, f: Filtros, aba: str) -> str:
        """CSV UTF-8 com BOM, separador `;` e vírgula decimal (abre direto no Excel em português)."""
        t = self.tabela(f, aba)
        saida = io.StringIO()
        saida.write("﻿")
        w = csv.writer(saida, delimiter=";", lineterminator="\r\n")
        cab = [ROTULO_ABA[aba]] + (["Grupo"] if aba == "questao" else []) + [
            "Respondentes", "Respostas", "Acertos", "Erros", "% acerto", "% erro", "Tempo mediano (s)"]
        w.writerow(cab)

        def linha(rotulo, grupo, m):
            return [_seguro(rotulo)] + ([_seguro(grupo)] if aba == "questao" else []) + [
                m["respondentes"], m["respostas"], m["acertos"], m["erros"], _num(m["pct_acerto"]), _num(m["pct_erro"]),
                _num(None if m["tempo_mediano_ms"] is None else round(m["tempo_mediano_ms"] / 1000, 1))]

        for item in t["itens"]:
            w.writerow(linha(item["rotulo"], item.get("grupo"), item))
        w.writerow(linha("Total", "", t["totais"]))
        return saida.getvalue()


def _num(valor: Optional[float]) -> str:
    return "" if valor is None else f"{valor:.1f}".replace(".", ",")


def _seguro(texto: Any) -> Any:
    """Neutraliza fórmulas: o Excel executa células que começam com = + - @ (rótulos vêm de dados digitados)."""
    texto = "" if texto is None else str(texto)
    return "'" + texto if texto[:1] in ("=", "+", "-", "@", "\t", "\r") else texto
