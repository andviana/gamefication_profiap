# TechQuiz Campus: guia de operação (para o setor de TI)

Este guia leva um servidor Linux do zero até o sistema funcionando em produção, e explica a rotina: logs, atualização,
backup, restauração e recuperação de acesso. Os modelos de arquivo ficam em [`deploy/`](deploy/). O guia de desenvolvimento
é o [README_ADMIN.md](README_ADMIN.md).

> **Este guia é para instalar sem Docker** (systemd + Nginx) num servidor próprio. Para a **VPS da Hostinger com Docker e
> Traefik**, siga o [docs/DEPLOY_VPS_HOSTINGER.md](docs/DEPLOY_VPS_HOSTINGER.md).

## 1. Como as peças se encaixam

```
aluno / professor ──HTTPS──▶ Nginx (443) ──HTTP local──▶ gunicorn (127.0.0.1:8000) ──▶ PostgreSQL (127.0.0.1:5432)
                              │ certificado da instituição        │ app Flask (o jogo, a API e o painel)
                              └ arquivos estáticos direto do disco
```

- **Um único aplicativo** serve o jogo (`/`), a API pública do jogo (`/api/…`) e o painel (`/entrar`, `/admin/…`).
- **Sem Docker, sem Redis, sem Node.** Tudo roda como serviço do sistema.
- **Dados:** só o PostgreSQL. As respostas dos alunos são anônimas (sem nome, e-mail, matrícula, IP ou avatar).
- **Segredos:** ficam só no arquivo de ambiente `/etc/techquiz/techquiz.env`.

## 2. Requisitos

| Item | Versão |
|---|---|
| Linux com systemd (Debian ou Ubuntu LTS) | |
| Python | 3.12 ou superior (desenvolvido e testado com 3.14; para confirmar na homologação, copie também `tests/` e rode `pip install -r requirements-dev.txt && pytest`) |
| PostgreSQL | 15 ou superior (testado com 17) |
| Nginx | 1.25.1 ou superior (os modelos usam `http2 on;`; em versão anterior troque por `listen 443 ssl http2;`) |
| Certificado TLS da instituição | com a cadeia completa |
| Nome DNS apontando para o servidor | ex.: `techquiz.ufra.edu.br` |

Portas: só **80 e 443** ficam abertas para a rede. O PostgreSQL e o gunicorn escutam apenas em `127.0.0.1`.

## 3. Instalação, passo a passo

Os comandos abaixo assumem Debian/Ubuntu e usuário com `sudo`. Os caminhos (`/opt/techquiz`, `/etc/techquiz`,
`/var/backups/techquiz`) são os dos modelos; se mudar algum, mude também nos arquivos de `deploy/`.

### 3.1 Pacotes

```bash
sudo apt update
sudo apt install -y nginx postgresql python3 python3-venv rsync
```

### 3.2 Usuário do serviço e pastas

```bash
sudo useradd --system --home /opt/techquiz --shell /usr/sbin/nologin techquiz
sudo mkdir -p /opt/techquiz /etc/techquiz /var/backups/techquiz
sudo chown techquiz:techquiz /opt/techquiz /var/backups/techquiz
sudo chmod 750 /var/backups/techquiz
```

### 3.3 Código e dependências

Copie o projeto para `/opt/techquiz/app` (por `git clone` ou `rsync`; não leve `.venv`, **`.env`** de desenvolvimento, `instance/` nem `tests/`):

```bash
sudo rsync -a --exclude .venv --exclude .env --exclude instance --exclude .git --exclude tests \
    --exclude __pycache__ --exclude .pytest_cache --exclude .claude \
    ./ /opt/techquiz/app/
sudo chown -R techquiz:techquiz /opt/techquiz
sudo -u techquiz python3 -m venv /opt/techquiz/venv
sudo -u techquiz /opt/techquiz/venv/bin/pip install -r /opt/techquiz/app/requirements.txt
```

### 3.4 Banco de dados

```bash
sudo -u postgres psql <<'SQL'
CREATE ROLE techquiz LOGIN PASSWORD 'TROQUE-ESTA-SENHA';
CREATE DATABASE techquiz OWNER techquiz ENCODING 'UTF8';
SQL
```

Confirme que o PostgreSQL só aceita conexões locais (`listen_addresses = 'localhost'`, que é o padrão).

### 3.5 Arquivo de ambiente

```bash
sudo cp /opt/techquiz/app/deploy/techquiz.env.example /etc/techquiz/techquiz.env
sudo chown root:techquiz /etc/techquiz/techquiz.env && sudo chmod 640 /etc/techquiz/techquiz.env
sudo editor /etc/techquiz/techquiz.env
```

Preencha, no mínimo:

- `SECRET_KEY` e `GABARITO_SAL`: valores aleatórios longos (o próprio arquivo ensina a gerar). **Guarde-os num cofre.**
  Trocar o `GABARITO_SAL` com uma coleta em andamento faz o jogo deixar de corrigir as respostas dos alunos que já abriram a partida.
- `DATABASE_URL` com a senha do passo anterior (caracteres como `@` ou `/` na senha precisam de codificação percentual).
- `PROXIES_CONFIAVEIS=1` (há um Nginx na frente).

O aplicativo **se recusa a subir** se faltar algo obrigatório em produção e lista todos os problemas de uma vez.

Para que os comandos `flask …` manuais usem a mesma configuração, ligue o arquivo ao app:

```bash
sudo ln -s /etc/techquiz/techquiz.env /opt/techquiz/app/.env
```

### 3.6 Criar as tabelas

```bash
cd /opt/techquiz/app && sudo -u techquiz /opt/techquiz/venv/bin/flask db upgrade
```

### 3.7 Serviço do aplicativo (systemd)

```bash
sudo cp /opt/techquiz/app/deploy/techquiz.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now techquiz
systemctl status techquiz --no-pager
curl -s http://127.0.0.1:8000/saude        # deve mostrar "status":"ok"
```

Se o serviço não subir: `journalctl -u techquiz -n 50 --no-pager` mostra o motivo (ver a seção 9).

### 3.8 Nginx e HTTPS

```bash
sudo cp /opt/techquiz/app/deploy/nginx-techquiz.conf /etc/nginx/sites-available/techquiz
sudo cp /opt/techquiz/app/deploy/nginx-techquiz-proxy.inc /etc/nginx/techquiz-proxy.inc
sudo editor /etc/nginx/sites-available/techquiz      # nome do site e caminhos do certificado
sudo rm -f /etc/nginx/sites-enabled/default          # senão o site padrão do Nginx responde por nomes não configurados
sudo ln -s /etc/nginx/sites-available/techquiz /etc/nginx/sites-enabled/techquiz
sudo nginx -t && sudo systemctl reload nginx
```

### 3.9 Criar o super admin raiz, **agora**

A primeira pessoa que abrir `https://SEU-SITE/setup` vira o **super admin raiz** (único dono da gestão de usuários e das
importações; ninguém o remove pela interface). A rota some depois do primeiro cadastro. **Faça isso logo após o deploy e antes
de divulgar o endereço.** Se alguém assumir antes por engano, apague o banco e refaça a partir do passo 3.6, ou use
`flask redefinir-superadmin` (seção 6) para retomar a conta raiz.

### 3.10 Verificação automática

```bash
sh /opt/techquiz/app/deploy/smoke-test.sh https://SEU-SITE
```

Confere `/saude`, o redirecionamento de HTTP para HTTPS, os cabeçalhos de segurança, o jogo, os estáticos e a proteção do
painel e da API. Tem de terminar com "Tudo certo."

### 3.11 Backup semanal

```bash
sudo cp /opt/techquiz/app/deploy/techquiz-backup.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now techquiz-backup.timer
systemctl list-timers techquiz-backup.timer
sudo systemctl start techquiz-backup.service && ls -la /var/backups/techquiz     # primeiro backup, para conferir
```

## 4. Rotina e logs

| O que fazer | Comando |
|---|---|
| Ver o estado | `systemctl status techquiz` e `curl -s https://SEU-SITE/saude` |
| Acompanhar os logs | `journalctl -u techquiz -f` |
| Ver eventos sensíveis (login, promoções, importações, troca de gabarito) | `journalctl -u techquiz \| grep AUDITORIA` |
| Reiniciar | `sudo systemctl restart techquiz` |
| Recarregar sem derrubar conexões | `sudo systemctl reload techquiz` |

O log de acesso mostra IP, rota, status e tempo, **nunca** o corpo das requisições (códigos de coleta, respostas e senhas não
vão para o log).

## 5. Atualizar para uma versão nova

1. **Backup manual:** `sudo -u techquiz /opt/techquiz/app/deploy/techquiz-backup.sh`
2. Copie o código novo para `/opt/techquiz/app` (mesmo `rsync` do passo 3.3) e `sudo chown -R techquiz:techquiz /opt/techquiz`.
3. Dependências: `sudo -u techquiz /opt/techquiz/venv/bin/pip install -r /opt/techquiz/app/requirements.txt`
4. Migrações: `cd /opt/techquiz/app && sudo -u techquiz /opt/techquiz/venv/bin/flask db upgrade`
5. `sudo systemctl restart techquiz` e `sh deploy/smoke-test.sh https://SEU-SITE`

Se algo der errado, volte o código anterior e restaure o backup do passo 1 (seção 7). O aplicativo recusa subir com o banco
desatualizado, o que evita rodar código novo sobre tabelas antigas.

## 6. Recuperar o acesso do super admin raiz

Esqueceu a senha da conta raiz? No servidor:

```bash
cd /opt/techquiz/app && sudo -u techquiz /opt/techquiz/venv/bin/flask redefinir-superadmin
```

O comando pede a nova senha duas vezes, encerra as sessões abertas e destrava o login. Os super admins promovidos continuam
gerindo usuários comuns e importações enquanto isso, mas não alteram a raiz. Para destravar outro usuário (5 senhas erradas
travam por 10 minutos), um super admin redefine a senha dele no painel.

## 7. Backup e restauração

**O que existe:** um `pg_dump` compactado toda **semana** (domingo, 03:00), com **retenção de 8 semanas**, gravado em
`/var/backups/techquiz` (modo 0600) com arquivo `.sha256` de conferência. O arquivo é testado (`pg_restore --list`) antes de ser
aceito, e os antigos só são apagados depois que o novo está pronto.

**Cópia fora do servidor (obrigatória na prática):** o backup no mesmo disco não protege contra perda do servidor. Defina
`BACKUP_COPIA_CMD` no arquivo de ambiente com o comando da instituição (rsync, scp, montagem de rede…); ele recebe o caminho do
arquivo em `$1`. Se a cópia falhar, o serviço falha e aparece em `systemctl --failed`.

**Quando rodar um backup manual** (por causa do risco de perder até uma semana de respostas):

- antes de **trocar o gabarito** de um questionário travado (a troca reescreve acertos de partidas já gravadas);
- ao **fim de cada coleta**;
- antes de **atualizar** o sistema.

```bash
sudo -u techquiz /opt/techquiz/app/deploy/techquiz-backup.sh
```

**Teste de restauração** (faça na homologação e repita de vez em quando). Restaura num banco temporário, confere a soma de
verificação, conta as linhas e apaga o temporário, sem tocar na produção:

```bash
sudo -u postgres sh /opt/techquiz/app/deploy/techquiz-restore-check.sh /var/backups/techquiz/techquiz-AAAAMMDD-HHMMSS.dump
```

**Restaurar de verdade** (desastre ou volta de versão):

```bash
sudo systemctl stop techquiz
sudo -u postgres dropdb techquiz && sudo -u postgres createdb -O techquiz -E UTF8 techquiz
sudo -u postgres pg_restore --no-owner --role=techquiz -d techquiz /var/backups/techquiz/techquiz-AAAAMMDD-HHMMSS.dump
cd /opt/techquiz/app && sudo -u techquiz /opt/techquiz/venv/bin/flask db upgrade     # leva o schema à versão do código
sudo systemctl start techquiz
```

## 8. Dados: retenção e eliminação

Não há expiração automática nem exclusão pela interface (as coletas só podem ser desativadas): as respostas ficam até a
instituição decidir. Os dados são anônimos, mas **confirme o prazo de guarda com o comitê de ética**. Se for preciso eliminar
uma coleta inteira, faça **backup antes** e rode, trocando o código:

```sql
BEGIN;
DELETE FROM partida WHERE coleta_id = (SELECT id FROM coleta WHERE codigo = 'ABCDE');   -- leva as respostas junto
DELETE FROM coleta  WHERE codigo = 'ABCDE';
COMMIT;
```

## 9. Solução de problemas

| Sintoma | Causa provável e o que fazer |
|---|---|
| `systemctl status techquiz` mostra "failed" e o log diz **"Configuração inválida"** | Falta ou está errada uma variável do `techquiz.env`; a mensagem lista todas. Corrija e `systemctl restart techquiz` |
| O log diz **"O schema do banco está desatualizado"** (ou "não foi criado") | Rode `flask db upgrade` (passo 3.6 ou 5) e reinicie |
| Nginx responde **502** | O gunicorn está parado: `systemctl status techquiz`, `journalctl -u techquiz -n 50` |
| O login **não fica** (volta para a tela de entrar) | O cookie é `Secure`: só funciona por **HTTPS**. Acesse pelo endereço `https://` |
| Login dá **400** | Falha na verificação de origem (CSRF): o endereço acessado tem de ser o mesmo configurado no Nginx; confira o `Host` e o redirecionamento |
| Alunos de uma sala recebem **429** (muitas tentativas) | O app está vendo o IP do Nginx em vez do IP do aluno. Veja "IP real" abaixo |
| `/saude` responde **503** | Banco inacessível ou schema fora de versão; o corpo diz qual |
| Painel lento com muitos dados | Os testes com 160 mil respostas ficaram abaixo de 0,6 s por consulta; se piorar, veja `journalctl` e o tamanho do `max_connections` do PostgreSQL |

### IP real do cliente

O limite de tentativas de código erradas é **por IP** e só conta as **falhas**. Isso só funciona se o app enxergar o IP do aluno
e não o do Nginx. Os modelos já fazem o Nginx **sobrescrever** `X-Forwarded-For` com o IP que ele viu (um cliente não consegue
forjar o cabeçalho) e o app lê esse valor quando `PROXIES_CONFIAVEIS=1`.

Confira na homologação: acesse de um computador qualquer e olhe o log (`journalctl -u techquiz -f`): o primeiro campo da linha
de acesso tem de ser o IP desse computador, e **não** `127.0.0.1`. Se houver **outro** proxy ou balanceador da instituição na
frente do Nginx, ele passa a ser o IP visto: configure no Nginx o módulo `realip` (`set_real_ip_from` com o IP do balanceador e
`real_ip_header X-Forwarded-For`) e repita a conferência.

### HTTPS e o jogo

O painel exige HTTPS (cookie `Secure`). O jogo calcula o gabarito com `crypto.subtle`, que só existe em HTTPS ou localhost;
quando falta, ele usa uma implementação própria, então continua funcionando, mas **sirva tudo por HTTPS** de qualquer forma.

## 10. Segurança: o que já vem pronto e o que cabe à TI

**Já implementado no aplicativo:** senha com hash forte e bloqueio após 5 erros; sessão de 8 h de inatividade em cookie
`HttpOnly`, `Secure` e `SameSite=Lax`; proteção CSRF em todos os formulários; perfis (raiz, super admin, comum) validados no
servidor; cabeçalhos `Content-Security-Policy` (sem script inline nem de outra origem), `X-Frame-Options: DENY`,
`Strict-Transport-Security`, `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`; páginas do painel sem cache;
mensagens de erro genéricas (detalhes só no log); limite de tentativas de código por IP; o servidor recalcula os acertos (o
jogo não é fonte de verdade); a API não envia o gabarito em texto.

**Cabe à TI:** firewall (só 80/443); atualizações do sistema, do Nginx e do PostgreSQL; certificado dentro da validade;
permissões dos arquivos (`techquiz.env` com modo 0640, backups com 0600); monitoramento de `/saude`; guarda do cofre de
segredos; cópia externa do backup; revisão periódica da lista de usuários do painel.

## 11. Checklist da homologação (turma-piloto)

- [ ] `smoke-test.sh` termina com "Tudo certo."
- [ ] `/setup` feito e a conta raiz funciona; senha guardada
- [ ] Importação de um questionário real por um super admin; coleta criada com prazo; código testado por um aluno
- [ ] Turma-piloto joga; as partidas aparecem no dashboard e o número confere com a contagem manual
- [ ] IP real conferido no log (seção 9) e uma sala inteira atrás do mesmo IP consegue jogar sem receber 429
- [ ] Backup manual feito, **copiado para fora do servidor** e o teste de restauração passou
- [ ] `flask redefinir-superadmin` testado
- [ ] Um professor usa o dashboard sem ajuda e responde às perguntas-guia (quais questões têm mais erro? qual alternativa errada
      os alunos escolhem? como se comparam campus e cursos?)
- [ ] Reiniciar o servidor (`reboot`): o serviço e o timer voltam sozinhos
