"""Leitura e validação dos dois CSVs de perguntas e alternativas. Funções puras: sem banco e sem Flask.

Formato (o mesmo do antigo conversor de CSV, já removido):
  perguntas.csv    -> Número da pergunta; Pergunta; Título; Grupo; Autoajuda
  alternativas.csv -> Número da pergunta; Letra; Texto da alternativa; Correta ou incorreta; Texto de acerto; Texto de erro
UTF-8 (com ou sem BOM); delimitador `;`, `,` ou tabulação (detectado na primeira linha). O jogo suporta de 2 a 4 alternativas (A a D).
"""
from __future__ import annotations

import csv
import io
import unicodedata
from dataclasses import dataclass, field

LETRAS = "ABCD"
MAX_PERGUNTAS = 300
MAX_LINHAS_POR_ARQUIVO = 5000
LIMITES = {"texto": 5000, "titulo": 160, "grupo": 120, "autoajuda": 2000, "alt": 1000, "feedback": 2000}

COLS_PERGUNTAS = {"numero da pergunta": "numero", "pergunta": "texto", "titulo": "titulo", "grupo": "grupo", "autoajuda": "autoajuda"}
COLS_ALTERNATIVAS = {"numero da pergunta": "numero", "letra": "letra", "texto da alternativa": "texto",
                     "correta ou incorreta": "correta", "texto de acerto": "acerto", "texto de erro": "erro"}
VERDADEIRO = {"correta", "correto", "certa", "certo", "c", "sim", "s", "1", "true", "verdadeiro", "v"}
FALSO = {"incorreta", "incorreto", "errada", "errado", "i", "nao", "n", "0", "false", "falso", "f"}


@dataclass(frozen=True)
class ErroLinha:
    arquivo: str
    linha: int | None
    mensagem: str

    def __str__(self) -> str:
        return f"{self.arquivo}{':' + str(self.linha) if self.linha else ''}: {self.mensagem}"


@dataclass
class Analise:
    perguntas: list[dict] = field(default_factory=list)
    erros: list[ErroLinha] = field(default_factory=list)
    avisos: list[ErroLinha] = field(default_factory=list)

    @property
    def n_alternativas(self) -> int:
        return sum(len(p["alternativas"]) for p in self.perguntas)


def norm(texto: str) -> str:
    """Minúsculas, sem acentos e sem espaços nas pontas (para casar cabeçalhos e valores)."""
    nfd = unicodedata.normalize("NFD", (texto or "").strip().lower())
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")


def _compacta(texto: str) -> str:
    return " ".join((texto or "").split())


def ler_tabela(arquivo: str, conteudo: bytes, colunas: dict, erros: list[ErroLinha]) -> list[dict]:
    """Lê um CSV e devolve registros (dicts com as chaves internas e `_linha`). Problemas vão para `erros`."""
    if b"\x00" in conteudo:
        erros.append(ErroLinha(arquivo, None, "o arquivo não parece ser um CSV de texto (contém bytes nulos)"))
        return []
    try:
        texto = conteudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        erros.append(ErroLinha(arquivo, None, "o arquivo não está em UTF-8 (no Excel, salve como “CSV UTF-8”)"))
        return []
    primeira = next((l for l in texto.splitlines() if l.strip()), "")
    if not primeira:
        erros.append(ErroLinha(arquivo, None, "arquivo vazio"))
        return []
    contagem = {d: primeira.count(d) for d in (";", ",", "\t")}
    delimitador = max(contagem, key=contagem.get) if max(contagem.values()) else ";"

    leitor = csv.reader(io.StringIO(texto, newline=""), delimiter=delimitador)
    try:
        cabecalho = next(leitor)
    except (StopIteration, csv.Error):
        erros.append(ErroLinha(arquivo, None, "arquivo vazio"))
        return []
    indice = {}
    for pos, titulo in enumerate(cabecalho):
        chave = colunas.get(norm(titulo))
        if chave:
            indice[chave] = pos
    faltando = [orig for orig, chave in colunas.items() if chave not in indice]
    if faltando:
        erros.append(ErroLinha(arquivo, 1, "colunas ausentes no cabeçalho: " + ", ".join(faltando)))
        return []

    registros = []
    try:
        for campos in leitor:
            if not any(c.strip() for c in campos):
                continue
            if len(registros) >= MAX_LINHAS_POR_ARQUIVO:
                erros.append(ErroLinha(arquivo, leitor.line_num, f"arquivo grande demais (máximo de {MAX_LINHAS_POR_ARQUIVO} linhas)"))
                return []
            registro = {k: (campos[p].strip() if p < len(campos) else "") for k, p in indice.items()}
            registro["_linha"] = leitor.line_num
            registros.append(registro)
    except csv.Error as erro:
        erros.append(ErroLinha(arquivo, leitor.line_num, f"CSV malformado ({erro})"))
        return []
    return registros


def _limite(erros, arquivo, linha, rotulo, valor, chave):
    if len(valor) > LIMITES[chave]:
        erros.append(ErroLinha(arquivo, linha, f"{rotulo} com mais de {LIMITES[chave]} caracteres"))


def analisar(perguntas_csv: bytes, alternativas_csv: bytes) -> Analise:
    """Valida os dois arquivos juntos. Se `erros` estiver vazio, `perguntas` está pronto para importar."""
    analise = Analise()
    erros, avisos = analise.erros, analise.avisos
    PA, AA = "perguntas.csv", "alternativas.csv"

    perguntas: dict[int, dict] = {}
    for r in ler_tabela(PA, perguntas_csv, COLS_PERGUNTAS, erros):
        linha = r["_linha"]
        try:
            numero = int(r["numero"])
        except ValueError:
            erros.append(ErroLinha(PA, linha, f"“Número da pergunta” inválido ({r['numero']!r}); use um número inteiro"))
            continue
        if numero < 1:
            erros.append(ErroLinha(PA, linha, f"“Número da pergunta” deve ser 1 ou maior (veio {numero})"))
            continue
        if numero in perguntas:
            erros.append(ErroLinha(PA, linha, f"pergunta {numero} repetida (primeira ocorrência na linha {perguntas[numero]['_linha']})"))
            continue
        texto, titulo, grupo = r["texto"], _compacta(r["titulo"]), _compacta(r["grupo"])
        if not texto:
            erros.append(ErroLinha(PA, linha, f"pergunta {numero} sem o texto do enunciado"))
        if not titulo:
            erros.append(ErroLinha(PA, linha, f"pergunta {numero} sem “Título”"))
        if not grupo:
            erros.append(ErroLinha(PA, linha, f"pergunta {numero} sem “Grupo”"))
        _limite(erros, PA, linha, f"pergunta {numero}: enunciado", texto, "texto")
        _limite(erros, PA, linha, f"pergunta {numero}: título", titulo, "titulo")
        _limite(erros, PA, linha, f"pergunta {numero}: grupo", grupo, "grupo")
        _limite(erros, PA, linha, f"pergunta {numero}: autoajuda", r["autoajuda"], "autoajuda")
        perguntas[numero] = {"numero": numero, "texto": texto, "titulo": titulo, "grupo": grupo,
                             "autoajuda": r["autoajuda"] or None, "alternativas": [], "_linha": linha}
    if len(perguntas) > MAX_PERGUNTAS:
        erros.append(ErroLinha(PA, None, f"perguntas demais ({len(perguntas)}); o máximo é {MAX_PERGUNTAS} por questionário"))

    for r in ler_tabela(AA, alternativas_csv, COLS_ALTERNATIVAS, erros):
        linha = r["_linha"]
        try:
            numero = int(r["numero"])
        except ValueError:
            erros.append(ErroLinha(AA, linha, f"“Número da pergunta” inválido ({r['numero']!r})"))
            continue
        if numero not in perguntas:
            erros.append(ErroLinha(AA, linha, f"a alternativa aponta para a pergunta {numero}, que não existe em perguntas.csv"))
            continue
        letra = r["letra"].upper().rstrip(").:- ")
        if letra not in LETRAS:
            erros.append(ErroLinha(AA, linha, f"pergunta {numero}: letra inválida ({r['letra']!r}); use A, B, C ou D"))
            continue
        if any(a["letra"] == letra for a in perguntas[numero]["alternativas"]):
            erros.append(ErroLinha(AA, linha, f"pergunta {numero}: letra {letra} repetida"))
            continue
        valor = norm(r["correta"])
        if valor in VERDADEIRO:
            correta = True
        elif valor in FALSO:
            correta = False
        else:
            erros.append(ErroLinha(AA, linha, f"pergunta {numero}, alternativa {letra}: “Correta ou incorreta” deve ser "
                                               f"“Correta” ou “Incorreta” (veio {r['correta']!r})"))
            continue
        if not r["texto"]:
            erros.append(ErroLinha(AA, linha, f"pergunta {numero}, alternativa {letra}: texto da alternativa vazio"))
        _limite(erros, AA, linha, f"pergunta {numero}, alternativa {letra}: texto", r["texto"], "alt")
        _limite(erros, AA, linha, f"pergunta {numero}, alternativa {letra}: texto de acerto", r["acerto"], "feedback")
        _limite(erros, AA, linha, f"pergunta {numero}, alternativa {letra}: texto de erro", r["erro"], "feedback")
        perguntas[numero]["alternativas"].append({"letra": letra, "texto": r["texto"], "correta": correta,
                                                  "texto_acerto": r["acerto"] or None, "texto_erro": r["erro"] or None})

    for numero in sorted(perguntas):
        p = perguntas[numero]
        alts = sorted(p["alternativas"], key=lambda a: a["letra"])
        p["alternativas"] = alts
        loc = p["_linha"]
        if not alts:
            erros.append(ErroLinha(PA, loc, f"pergunta {numero} não tem nenhuma alternativa em alternativas.csv"))
            continue
        if not 2 <= len(alts) <= 4:
            erros.append(ErroLinha(PA, loc, f"pergunta {numero} tem {len(alts)} alternativa(s); o jogo suporta de 2 a 4"))
        corretas = [a["letra"] for a in alts if a["correta"]]
        if not corretas:
            erros.append(ErroLinha(PA, loc, f"pergunta {numero} está SEM alternativa correta"))
        elif len(corretas) > 1:
            erros.append(ErroLinha(PA, loc, f"pergunta {numero} tem MAIS DE UMA alternativa correta ({', '.join(corretas)})"))
        letras = "".join(a["letra"] for a in alts)
        if letras != LETRAS[:len(letras)]:
            avisos.append(ErroLinha(PA, loc, f"pergunta {numero}: as letras {letras} não são sequenciais a partir de A"))

    analise.perguntas = [{k: v for k, v in perguntas[n].items() if k != "_linha"} for n in sorted(perguntas)]
    if not perguntas and not erros:
        erros.append(ErroLinha(PA, None, "nenhuma pergunta encontrada"))
    return analise
