from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField, SubmitField
from wtforms.validators import InputRequired

OBRIGATORIO = InputRequired("Campo obrigatório.")


class NovoUsuarioForm(FlaskForm):
    nome = StringField("Nome", [OBRIGATORIO], render_kw={"autofocus": True})
    login = StringField("Login", [OBRIGATORIO], render_kw={"autocomplete": "off"})
    senha = PasswordField("Senha inicial", [OBRIGATORIO], render_kw={"autocomplete": "new-password"})
    confirmacao = PasswordField("Confirme a senha", [OBRIGATORIO], render_kw={"autocomplete": "new-password"})
    enviar = SubmitField("Criar usuário")


class EditarUsuarioForm(FlaskForm):
    nome = StringField("Nome", [OBRIGATORIO], render_kw={"autofocus": True})
    login = StringField("Login", [OBRIGATORIO], render_kw={"autocomplete": "off"})
    enviar = SubmitField("Salvar")


class RedefinirSenhaForm(FlaskForm):
    nova = PasswordField("Nova senha", [OBRIGATORIO], render_kw={"autocomplete": "new-password", "autofocus": True})
    confirmacao = PasswordField("Confirme a nova senha", [OBRIGATORIO], render_kw={"autocomplete": "new-password"})
    enviar = SubmitField("Redefinir senha")


class ReferenciaForm(FlaskForm):
    nome = StringField("Nome", [OBRIGATORIO], render_kw={"autofocus": True})
    enviar = SubmitField("Salvar")


# ---- questionários e perguntas ----------------------------------------------------------------
from wtforms import SelectField, TextAreaField  # noqa: E402
from wtforms.validators import Optional  # noqa: E402

from app.services.perguntas import LETRAS, MAX_ALTERNATIVAS  # noqa: E402


class QuestionarioForm(FlaskForm):
    nome = StringField("Nome do questionário", [OBRIGATORIO], render_kw={"autofocus": True})
    descricao = TextAreaField("Descrição (opcional)", [Optional()], render_kw={"rows": 3})
    enviar = SubmitField("Salvar")


class OrientacoesForm(FlaskForm):
    orientacoes = TextAreaField("Texto das orientações", [OBRIGATORIO], render_kw={"rows": 22, "spellcheck": "true"})
    enviar = SubmitField("Salvar orientações")


class PerguntaForm(FlaskForm):
    numero = StringField("Número", [Optional()], render_kw={"inputmode": "numeric", "placeholder": "automático"})
    grupo_id = SelectField("Grupo", coerce=int, validate_choice=False)
    titulo = StringField("Título (tema)", [OBRIGATORIO], render_kw={"autofocus": True})
    texto = TextAreaField("Enunciado", [OBRIGATORIO], render_kw={"rows": 4})
    autoajuda = TextAreaField("Dica (opcional)", [Optional()], render_kw={"rows": 2})
    correta = StringField("Alternativa correta", [Optional()])   # recebe o índice marcado nos botões de rádio
    enviar = SubmitField("Salvar pergunta")


# uma linha por alternativa (A a D): texto, feedback de acerto e feedback de erro
for _i in range(MAX_ALTERNATIVAS):
    setattr(PerguntaForm, f"alt_texto_{_i}", TextAreaField(f"Alternativa {LETRAS[_i]}", [Optional()], render_kw={"rows": 2}))
    setattr(PerguntaForm, f"alt_acerto_{_i}", TextAreaField("Feedback se o aluno acertar", [Optional()], render_kw={"rows": 2}))
    setattr(PerguntaForm, f"alt_erro_{_i}", TextAreaField("Feedback se o aluno errar", [Optional()], render_kw={"rows": 2}))


class GabaritoForm(FlaskForm):
    correta = StringField("Nova alternativa correta", [OBRIGATORIO])
    enviar = SubmitField("Trocar gabarito")


# ---- importação de CSV ------------------------------------------------------------------------
from flask_wtf.file import FileField, FileRequired  # noqa: E402
from wtforms import HiddenField  # noqa: E402


class ImportacaoForm(FlaskForm):
    nome = StringField("Nome do novo questionário", [OBRIGATORIO], render_kw={"autofocus": True})
    descricao = TextAreaField("Descrição (opcional)", [Optional()], render_kw={"rows": 2})
    arquivo_perguntas = FileField("Arquivo perguntas.csv", [FileRequired("Selecione o arquivo de perguntas.")],
                                  render_kw={"accept": ".csv,text/csv"})
    arquivo_alternativas = FileField("Arquivo alternativas.csv", [FileRequired("Selecione o arquivo de alternativas.")],
                                     render_kw={"accept": ".csv,text/csv"})
    enviar = SubmitField("Analisar arquivos")


class ConfirmarImportacaoForm(FlaskForm):
    token = HiddenField(validators=[OBRIGATORIO])
    enviar = SubmitField("Confirmar importação")


# ---- coletas ------------------------------------------------------------------------------------
from wtforms import DateField  # noqa: E402


class DataField(DateField):
    """Campo de data (<input type="date">) com mensagem em português."""

    def process_formdata(self, valuelist):
        try:
            super().process_formdata(valuelist)
        except ValueError:
            self.data = None
            raise ValueError("Informe uma data válida.")


class ColetaForm(FlaskForm):
    questionario_id = SelectField("Questionário", coerce=int, validate_choice=False)
    campus_id = SelectField("Campus", coerce=int, validate_choice=False)
    curso_id = SelectField("Curso", coerce=int, validate_choice=False)
    ano = SelectField("Ano", coerce=int, validate_choice=False)
    periodo = SelectField("Período", coerce=int, validate_choice=False)
    data_inicio = DataField("Início", [OBRIGATORIO])
    data_fim = DataField("Fim", [OBRIGATORIO])
    enviar = SubmitField("Salvar")
