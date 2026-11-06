"""Perguntas e alternativas de um questionário. As travas de estrutura são do service; aqui só se traduz o formulário."""
from __future__ import annotations

from typing import Optional

from flask import current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.auth_web import superadmin_required
from app.blueprints.admin import bp
from app.blueprints.admin.forms import GabaritoForm, PerguntaForm
from app.blueprints.formularios import aplica_erro
from app.errors import ErroDominio
from app.services.perguntas import LETRAS, MAX_ALTERNATIVAS, DadosAlternativa, DadosPergunta
from app.services.questionarios import TRAVADO


def _c():
    return current_app.extensions["container"]


def _ator():
    return current_user._get_current_object()


def _grupos(atual_id: Optional[int] = None) -> list[tuple[int, str]]:
    """Grupos ativos (mais o grupo atual da pergunta, mesmo se inativo) para o campo de seleção."""
    return [(0, "Escolha…")] + [(g.id, g.nome + ("" if g.ativo else " (inativo)"))
                                for g in _c().referencias["grupo"].repo.listar() if g.ativo or g.id == atual_id]


def _valores_iniciais(pergunta) -> dict:
    valores = {"numero": str(pergunta.numero), "grupo_id": pergunta.grupo_id, "titulo": pergunta.titulo,
               "texto": pergunta.texto, "autoajuda": pergunta.autoajuda or ""}
    for i, a in enumerate(pergunta.alternativas):
        valores[f"alt_texto_{i}"] = a.texto
        valores[f"alt_acerto_{i}"] = a.texto_acerto or ""
        valores[f"alt_erro_{i}"] = a.texto_erro or ""
        if a.correta:
            valores["correta"] = str(i)
    return valores


def _linhas(form) -> list[dict]:
    return [{"texto": (getattr(form, f"alt_texto_{i}").data or "").strip(),
             "acerto": getattr(form, f"alt_acerto_{i}").data, "erro": getattr(form, f"alt_erro_{i}").data}
            for i in range(MAX_ALTERNATIVAS)]


def _dados(form, n_fixo: Optional[int] = None) -> Optional[DadosPergunta]:
    """Traduz o formulário em DadosPergunta. Devolve None (com erros no form) se algo não bate.

    As alternativas são as linhas de A até a última preenchida; linhas em branco no meio são erro (as letras
    seguem a ordem). Com `n_fixo` (questionário travado) o número de alternativas não muda.
    """
    linhas = _linhas(form)
    ultima = max((i for i, l in enumerate(linhas) if l["texto"] or l["acerto"] or l["erro"]), default=-1)
    if n_fixo is not None:
        ultima = n_fixo - 1
    erros = False
    for i in range(ultima + 1):
        if not linhas[i]["texto"]:
            getattr(form, f"alt_texto_{i}").errors = ["Preencha o texto da alternativa, sem deixar linhas em branco no meio."]
            erros = True
    numero = None
    bruto = (form.numero.data or "").strip()
    if bruto:
        try:
            numero = int(bruto)
        except ValueError:
            form.numero.errors = ["Informe um número inteiro."]
            erros = True
    marcada = (form.correta.data or "").strip()
    indice = int(marcada) if marcada.isdigit() else -1
    if not erros and not 0 <= indice <= ultima:
        form.correta.errors = ["Marque qual alternativa é a correta."]
        erros = True
    if erros:
        return None
    alternativas = [DadosAlternativa(texto=l["texto"], correta=(i == indice), texto_acerto=l["acerto"], texto_erro=l["erro"])
                    for i, l in enumerate(linhas[:ultima + 1])]
    return DadosPergunta(texto=form.texto.data, titulo=form.titulo.data, grupo_id=form.grupo_id.data or 0,
                         alternativas=alternativas, autoajuda=form.autoajuda.data, numero=numero)


def _tela(form, q, pergunta, travado: bool, titulo: str, status: Optional[int] = None):
    n_alt = len(pergunta.alternativas) if pergunta else 0
    return render_template("admin/perguntas/form.html", form=form, q=q, pergunta=pergunta, travado=travado, titulo=titulo,
                           letras=LETRAS, n_linhas=MAX_ALTERNATIVAS, n_existentes=n_alt), status or (422 if form.errors else 200)


@bp.route("/questionarios/<int:questionario_id>/perguntas/nova", methods=["GET", "POST"])
@login_required
def perguntas_nova(questionario_id: int):
    svc = _c().perguntas
    q = _c().questionarios.obter(questionario_id)
    form = PerguntaForm()
    form.grupo_id.choices = _grupos()
    status = None
    if form.validate_on_submit():
        dados = _dados(form)
        if dados:
            try:
                p = svc.criar(_ator(), questionario_id, dados)
            except ErroDominio as erro:
                status = aplica_erro(form, erro)
            else:
                flash(f"Pergunta {p.numero} criada.", "success")
                return redirect(url_for("admin.questionarios_detalhe", questionario_id=questionario_id))
    return _tela(form, q, None, False, "Nova pergunta", status)


@bp.route("/questionarios/<int:questionario_id>/perguntas/<int:pergunta_id>/editar", methods=["GET", "POST"])
@login_required
def perguntas_editar(questionario_id: int, pergunta_id: int):
    svc = _c().perguntas
    q = _c().questionarios.obter(questionario_id)
    pergunta = svc.obter(questionario_id, pergunta_id)
    travado = _c().questionarios.resumo(q).estado == TRAVADO
    form = PerguntaForm(data=_valores_iniciais(pergunta)) if request.method == "GET" else PerguntaForm()
    form.grupo_id.choices = _grupos(pergunta.grupo_id)
    status = None
    if form.validate_on_submit():
        dados = _dados(form, n_fixo=len(pergunta.alternativas) if travado else None)
        if dados and travado:   # com respostas gravadas a estrutura não vem do formulário: fica como está
            dados.numero, dados.grupo_id = pergunta.numero, pergunta.grupo_id
            for nova, atual in zip(dados.alternativas, pergunta.alternativas):
                nova.correta = atual.correta
        if dados:
            try:
                svc.editar(_ator(), questionario_id, pergunta_id, dados)
            except ErroDominio as erro:
                status = aplica_erro(form, erro)
            else:
                flash(f"Pergunta {pergunta.numero} atualizada.", "success")
                return redirect(url_for("admin.questionarios_detalhe", questionario_id=questionario_id))
    return _tela(form, q, pergunta, travado, f"Editar a pergunta {pergunta.numero}", status)


@bp.post("/questionarios/<int:questionario_id>/perguntas/<int:pergunta_id>/excluir")
@login_required
def perguntas_excluir(questionario_id: int, pergunta_id: int):
    numero = _c().perguntas.obter(questionario_id, pergunta_id).numero
    _c().perguntas.excluir(_ator(), questionario_id, pergunta_id)
    flash(f"Pergunta {numero} excluída.", "success")
    return redirect(url_for("admin.questionarios_detalhe", questionario_id=questionario_id))


@bp.route("/questionarios/<int:questionario_id>/perguntas/<int:pergunta_id>/gabarito", methods=["GET", "POST"])
@superadmin_required
def perguntas_gabarito(questionario_id: int, pergunta_id: int):
    svc = _c().perguntas
    q = _c().questionarios.obter(questionario_id)
    pergunta = svc.obter(questionario_id, pergunta_id)
    form = GabaritoForm()
    if form.validate_on_submit():
        try:
            respostas, partidas = svc.trocar_gabarito(_ator(), questionario_id, pergunta_id, form.correta.data)
        except ErroDominio as erro:
            aplica_erro(form, erro)
        else:
            extra = f" {respostas} respostas em {partidas} partidas foram recalculadas." if respostas else ""
            flash(f"Gabarito da pergunta {pergunta.numero} trocado.{extra}", "success")
            return redirect(url_for("admin.questionarios_detalhe", questionario_id=questionario_id))
    respostas, partidas = svc.repo.respostas_da_pergunta(pergunta_id)
    return render_template("admin/perguntas/gabarito.html", form=form, q=q, pergunta=pergunta, respostas=respostas,
                           partidas=partidas), (422 if form.errors else 200)
