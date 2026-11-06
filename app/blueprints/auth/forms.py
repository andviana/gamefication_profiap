from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField, SubmitField
from wtforms.validators import InputRequired

OBRIGATORIO = InputRequired("Campo obrigatório.")


class LoginForm(FlaskForm):
    login = StringField("Login", [OBRIGATORIO], render_kw={"autocomplete": "username", "autofocus": True})
    senha = PasswordField("Senha", [OBRIGATORIO], render_kw={"autocomplete": "current-password"})
    enviar = SubmitField("Entrar")


class SetupForm(FlaskForm):
    nome = StringField("Seu nome", [OBRIGATORIO], render_kw={"autocomplete": "name", "autofocus": True})
    login = StringField("Login", [OBRIGATORIO], render_kw={"autocomplete": "username"})
    senha = PasswordField("Senha", [OBRIGATORIO], render_kw={"autocomplete": "new-password"})
    confirmacao = PasswordField("Confirme a senha", [OBRIGATORIO], render_kw={"autocomplete": "new-password"})
    enviar = SubmitField("Criar super admin")


class AlterarSenhaForm(FlaskForm):
    atual = PasswordField("Senha atual", [OBRIGATORIO], render_kw={"autocomplete": "current-password", "autofocus": True})
    nova = PasswordField("Nova senha", [OBRIGATORIO], render_kw={"autocomplete": "new-password"})
    confirmacao = PasswordField("Confirme a nova senha", [OBRIGATORIO], render_kw={"autocomplete": "new-password"})
    enviar = SubmitField("Alterar senha")
