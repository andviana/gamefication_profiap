# Deploy do TechQuiz na VPS da Hostinger, com Docker e Traefik

**Endereço sugerido:** `https://techquiz.institutoviva.digital` (troque pelo seu em `APP_DOMAIN`)
**Pilha:** Flask (gunicorn) + PostgreSQL 17, em Docker, atrás do Traefik que já roda na VPS.
**Dados:** o banco sobe **vazio**. O primeiro passo depois de subir é criar o super admin raiz na tela `/setup`.

> Este guia foi **validado num ambiente local equivalente**: imagem construída do zero, PostgreSQL e Traefik 3.6 em contêineres, banco vazio, HTTPS pelo Traefik, setup, login, backup e restauração. O que não dá para validar fora da sua VPS são os **nomes do seu Traefik** (rede, entrypoint e resolvedor de certificado), o DNS e o certificado: por isso a seção 3 ensina a descobri-los e a seção 11 lista os sintomas de cada erro.
> Para instalar **sem Docker** num servidor próprio (systemd + Nginx), veja o [README_OPERACAO.md](../README_OPERACAO.md).

---

## 1. Visão geral

```
Internet ──► DNS (hPanel) ──► IP da VPS ──► Traefik (80/443, certificado Let's Encrypt)
                                              │  rede do Traefik
                                              ▼
                                        app  (gunicorn, porta 8000: jogo, API e painel)
                                              │  rede interna "interna" (sem portas publicadas)
                                              ▼
                                        db (PostgreSQL 17)
```

- Só a **aplicação** está na rede do Traefik. O **banco fica numa rede interna**, sem porta aberta na VPS.
- O TechQuiz **não guarda arquivos**: tudo está no banco (por isso não há MinIO nem volume de arquivos).
- O HTTPS termina no Traefik. O app confia em **um** proxy (`PROXIES_CONFIAVEIS=1`) para ler o IP real do aluno (limite de tentativas) e o esquema `https` (cookie `Secure`, CSRF).
- Os cabeçalhos de segurança (HSTS, CSP, `X-Frame-Options`…) já vêm do próprio app em produção.

### Arquivos deste deploy no projeto

| Arquivo | Para quê |
|---|---|
| `Dockerfile` | Imagem (Python 3.14, gunicorn), roda sem privilégios (usuário `app`, UID 10001) |
| `docker/entrypoint.sh` | A cada subida: espera o banco e aplica as migrações (`flask db upgrade`) |
| `docker/aguardar_servicos.py`, `docker/saude.py` | Espera do banco e verificação de saúde do contêiner (`/saude`) |
| `docker-compose.prod.yml` | `app` e `db`, rede interna, rótulos do Traefik, volume do banco |
| `.env.producao.example` | Modelo das variáveis (copie para `.env`) |
| `docker/backup.sh`, `docker/restaurar-teste.sh` | Backup (com conferência, retenção e cópia externa) e teste de restauração |
| `deploy/gunicorn.conf.py` | Configuração do gunicorn (compartilhada com o deploy sem Docker) |
| `.dockerignore` | Mantém segredos, banco local, testes e `.venv` fora da imagem |

---

## 2. Pré-requisitos

- [ ] VPS Hostinger com **Docker** e o **Traefik já funcionando** (as outras aplicações respondem por HTTPS).
- [ ] Acesso **SSH** à VPS (recomendado) e/ou ao **Gerenciador Docker** do hPanel.
- [ ] Portas **80 e 443** abertas para a internet. **Não abra** 5432 (PostgreSQL) nem 8000.
- [ ] Domínio com o DNS gerenciado no **hPanel**.
- [ ] Repositório Git do projeto no GitHub, de preferência **privado**.
- [ ] Memória livre na VPS: ~600 MB (app ~250 MB, PostgreSQL ~100 MB, mais a construção da imagem). Confira com `free -h`.

---

## 3. Descobrir os valores do seu Traefik (3 minutos)

O `docker-compose.prod.yml` precisa de 3 valores do **seu** Traefik. Conecte por SSH:

```bash
# 1) Qual é o contêiner do Traefik?
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Ports}}' | grep -i traefik

# 2) Quais redes existem e em qual delas o Traefik e as suas apps estão?
docker network ls
docker network inspect <rede-candidata> --format '{{range .Containers}}{{.Name}} {{end}}'

# 3) Como o Traefik foi configurado (entrypoints, resolvedor de certificado, rede)?
docker inspect <nome-do-traefik> --format '{{json .Args}}' | python3 -m json.tool
docker inspect <nome-do-traefik> --format '{{json .Config.Cmd}}' | python3 -m json.tool

# 4) Como uma das suas apps JÁ publicadas se declara (copie o padrão)?
docker inspect <contêiner-de-uma-app-existente> --format '{{json .Config.Labels}}' | python3 -m json.tool
```

| Variável do `.env` | O que procurar | Exemplo (confirme no seu!) |
|---|---|---|
| `TRAEFIK_NETWORK` | A rede em que o Traefik **e** as apps existentes aparecem juntos (passo 2). Também aparece em `--providers.docker.network=` | `traefik-public`, `proxy`, `root_default`… |
| `TRAEFIK_ENTRYPOINT` | O entrypoint HTTPS: `--entrypoints.<nome>.address=:443`, ou o rótulo `traefik.http.routers.*.entrypoints` das apps | `websecure` |
| `TRAEFIK_CERTRESOLVER` | O nome do resolvedor: `--certificatesresolvers.<nome>...`, ou o rótulo `...tls.certresolver` das apps | `letsencrypt` |

> **Regra de ouro:** copie o padrão de rótulos de uma aplicação que já funciona. Se os rótulos delas diferirem, ajuste **o `.env`**, não o compose.

---

## 4. Gerar os segredos

Gere **valores diferentes** para cada um e guarde num gerenciador de senhas. Nunca coloque no Git.

```bash
openssl rand -base64 48 | tr -d '\n='      # SECRET_KEY
openssl rand -base64 24 | tr -d '\n=/+'    # GABARITO_SAL
openssl rand -base64 24 | tr -d '\n=/+'    # POSTGRES_PASSWORD
```

- Evite `$`, `"`, `'`, `\`, `@`, `/` e `:` na senha do banco (ela entra numa URL).
- **Não troque o `GABARITO_SAL`** depois que houver coleta em andamento: os jogos abertos deixariam de corrigir as respostas.
- O app **se recusa a subir** sem `SECRET_KEY`, `GABARITO_SAL` e `POSTGRES_PASSWORD` (o compose acusa a variável faltando).

---

## 5. DNS: criar o subdomínio (hPanel)

1. hPanel → **Domínios** → seu domínio → **DNS / Servidores de nomes** → **Gerenciar registros DNS**.
2. Adicione:

| Tipo | Nome | Aponta para | TTL |
|---|---|---|---|
| **A** | `techquiz` | **IP público da VPS** (hPanel → VPS → Visão geral) | 300 |
| AAAA (opcional) | `techquiz` | IPv6 da VPS, se houver e se o Traefik atender IPv6 | 300 |

3. Se já houver um registro `techquiz` (A, AAAA ou CNAME) apontando para outro lugar, **edite-o**.
4. Se existir um registro **CAA**, ele precisa permitir `letsencrypt.org`.
5. Verifique a propagação: `dig +short techquiz.institutoviva.digital` deve mostrar o IP da VPS.

> **Faça o DNS antes de subir o projeto.** O Traefik pede o certificado assim que vê o roteador; se o DNS ainda não aponta para a VPS, a emissão falha (e várias falhas seguidas acionam limite do Let's Encrypt).

---

## 6. Preparar o repositório Git

O projeto já é um repositório Git local. Falta o **remoto** (privado) no GitHub:

```bash
# 1) crie o repositório vazio e privado no GitHub (ex.: andviana/techquiz) e depois, na pasta do projeto:
git remote add origin git@github.com:andviana/techquiz.git
git branch -M main

# 2) confirme que NENHUM segredo/dado local será enviado (nada deve aparecer nesta lista)
git ls-files | grep -E '(^|/)(\.env$|.*\.db$|\.venv/|backups/)' || echo "ok: nada sensível versionado"

git push -u origin main
```

O `.gitignore` já ignora `.env`, `*.db`, `instance/`, `.venv/` e `backups/`.

### Acesso da VPS ao repositório privado: deploy key somente leitura (recomendado)

```bash
# na VPS
ssh-keygen -t ed25519 -f ~/.ssh/techquiz_deploy -N "" -C "vps-techquiz-deploy"
cat ~/.ssh/techquiz_deploy.pub     # copie a saída
```

GitHub → repositório → **Settings → Deploy keys → Add deploy key** → cole a chave, **sem** marcar "Allow write access".

```bash
# na VPS
cat >> ~/.ssh/config <<'EOF'
Host github-techquiz
  HostName github.com
  User git
  IdentityFile ~/.ssh/techquiz_deploy
  IdentitiesOnly yes
EOF
chmod 600 ~/.ssh/config
git ls-remote git@github-techquiz:andviana/techquiz.git   # deve listar as referências
```

---

## 7. Subir o sistema

### Método A: por SSH (recomendado)

```bash
# na VPS
mkdir -p /opt/techquiz && cd /opt/techquiz
git clone git@github-techquiz:andviana/techquiz.git .

cp .env.producao.example .env
chmod 600 .env
nano .env        # preencha APP_DOMAIN, TRAEFIK_* e os 3 segredos da seção 4

# valida o compose (acusa variável faltando) e sobe
docker compose -f docker-compose.prod.yml config -q && echo "compose ok"
docker compose -f docker-compose.prod.yml up -d --build
```

Acompanhe (a primeira construção leva de 2 a 5 minutos):

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f app
```

No log do `app` devem aparecer, nesta ordem: `PostgreSQL: ok` → `aplicando migrações` (as linhas `Running upgrade`) → `pronto; iniciando` → `Listening at: http://0.0.0.0:8000`. O estado do `app` passa de `starting` para `healthy` em ~1 minuto.

> Os contêineres criados por SSH aparecem no **Gerenciador Docker** do hPanel (projeto `techquiz`), onde você vê estado e logs e reinicia.

### Método B: pelo Gerenciador Docker do hPanel

> Os nomes de botões podem variar conforme a versão do painel; a ideia é criar um projeto a partir de um arquivo Compose.

1. hPanel → **VPS** → **Gerenciador Docker** → **Compose** → **Criar/Adicionar projeto** (nome: `techquiz`).
2. Cole o conteúdo de `docker-compose.prod.yml`.
3. Em **Variáveis de ambiente**, informe todas as do `.env.producao.example` e **mais uma**, porque o painel não tem a pasta do projeto:
   `APP_BUILD_CONTEXT=https://<TOKEN>@github.com/andviana/techquiz.git#main`
   (o Docker constrói direto do Git; use um token fine-grained **somente leitura**).
4. Inicie e acompanhe os registros do contêiner `app`. Se o painel **não aceitar construir a partir de URL Git**, use o Método A.

---

## 8. Verificar a instalação

```bash
# 1) contêineres saudáveis
docker compose -f docker-compose.prod.yml ps          # app e db: "healthy"

# 2) o Traefik enxergou o roteador? (nome: techquiz@docker)
docker logs <nome-do-traefik> 2>&1 | grep -i techquiz | tail

# 3) HTTPS e saúde (do seu computador)
curl -s https://techquiz.institutoviva.digital/saude          # {"status":"ok",...}
curl -sI http://techquiz.institutoviva.digital | head -3      # deve redirecionar para https (se o Traefik tem redirecionamento global)

# 4) o banco NÃO está exposto (na VPS)
ss -tlnp | grep -E ':(5432|8000)\b' || echo "ok: nenhuma dessas portas escuta na VPS"
```

Rode também o `deploy/smoke-test.sh` (do seu computador; confere cabeçalhos, jogo, estáticos e a proteção do painel e da API):

```bash
sh deploy/smoke-test.sh https://techquiz.institutoviva.digital
```

### Conferir o IP real do aluno (importante para o limite de tentativas)

O limite de códigos errados é **por IP**. O app lê o último valor de `X-Forwarded-For`, que tem de ser o IP que o **Traefik** viu. Confira que um cliente não consegue forjar:

```bash
# do seu computador
curl -s -o /dev/null -H 'X-Forwarded-For: 9.9.9.9' https://techquiz.institutoviva.digital/saude
# na VPS
docker compose -f docker-compose.prod.yml logs --tail=5 app | grep saude
```

O primeiro campo da linha tem de ser o **seu** IP público (ou `SEU-IP` depois de `9.9.9.9, `). Se aparecer **só `9.9.9.9`**, o seu Traefik está repassando o cabeçalho de quem vem de fora: configure `forwardedHeaders.trustedIPs` no entrypoint (ou não confie em cabeçalhos externos) antes de divulgar o endereço. No ensaio local, o Traefik 3.6 descartou o valor forjado.

---

## 9. Primeiros passos depois de subir

**Faça o setup agora, antes de divulgar o endereço.** A primeira pessoa que abrir `https://techquiz.institutoviva.digital/setup` vira o **super admin raiz** (único dono da gestão de usuários e das importações; ninguém o remove pela interface). A rota some depois do primeiro cadastro.

| # | Quem | Onde | O que fazer |
|---|---|---|---|
| 1 | Raiz | `/setup` | Criar o super admin raiz (guarde a senha) |
| 2 | Raiz | Usuários | Criar as contas dos professores (usuário comum) |
| 3 | Qualquer | Cadastros | Campus, cursos e grupos |
| 4 | Super admin | Importar | Enviar `perguntas.csv` e `alternativas.csv` (modelo em `data/`) ou criar o questionário pelo painel |
| 5 | Qualquer | Coletas | Criar a coleta de cada turma (gera o código de 5 letras) |
| 6 | Alunos | `/` | Digitam o código e jogam |
| 7 | Qualquer | Dashboard | Acompanhar os resultados |

---

## 10. Operação do dia a dia

Todos os comandos na pasta `/opt/techquiz` (Método A):

```bash
docker compose -f docker-compose.prod.yml ps                  # estado
docker compose -f docker-compose.prod.yml logs -f --tail=100 app
docker compose -f docker-compose.prod.yml restart app
docker compose -f docker-compose.prod.yml logs app | grep AUDITORIA     # eventos sensíveis (login, promoções, importações, troca de gabarito)
```

### Atualizar para uma nova versão

```bash
cd /opt/techquiz
sh docker/backup.sh                                   # sempre faça antes
git pull
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml logs --tail=50 app    # as migrações rodam sozinhas na subida
```

### Esqueci a senha do super admin raiz

```bash
docker compose -f docker-compose.prod.yml exec app flask redefinir-superadmin
```

Pede a nova senha duas vezes, encerra as sessões abertas e destrava o login. Para outro usuário, um super admin redefine a senha dele no painel.

### Recomeçar do zero (apaga TUDO)

> ⚠️ **Irreversível:** banco, usuários, questionários e respostas. Faça `sh docker/backup.sh` antes se houver algo a guardar.

```bash
cd /opt/techquiz
docker compose -f docker-compose.prod.yml down -v      # -v remove o volume do banco
docker compose -f docker-compose.prod.yml up -d        # volta à tela /setup: faça-o logo
```

### Parar e remover

```bash
docker compose -f docker-compose.prod.yml down          # para e remove os contêineres, MANTÉM os dados (volume)
```

---

## 11. Solução de problemas

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| **404 do Traefik** ("page not found") | Roteador não criado: rede errada, `traefik.enable`, entrypoint/resolvedor com outro nome, contêiner fora da rede do Traefik | `docker inspect techquiz-app-1 --format '{{json .NetworkSettings.Networks}}'` deve listar a rede do Traefik; reveja `TRAEFIK_*` (seção 3); `docker logs <traefik> \| grep -i techquiz` |
| **502 / 504** | App ainda subindo, não saudável ou porta errada | `docker compose … ps` e `logs app`; o serviço escuta na **8000** (rótulo `loadbalancer.server.port`) |
| Certificado inválido / certificado padrão do Traefik | Certificado ainda não emitido: DNS não aponta para a VPS, porta 80/443 fechada, resolvedor com outro nome, CAA bloqueando, limite do Let's Encrypt | Confirme `dig +short`; `docker logs <traefik> \| grep -i acme`; aguarde alguns minutos; evite reiniciar em loop |
| O login **não fica** (volta para a tela de entrar) | O cookie é `Secure` e o app não está vendo HTTPS | Confira `PROXIES_CONFIAVEIS: "1"` no compose e que o acesso é por `https://` |
| Login ou formulário dá **400** | Falha na verificação de origem (CSRF): o endereço acessado difere do que o Traefik repassa | Acesse pelo mesmo `APP_DOMAIN` configurado; confira que não há outro proxy alterando o `Host` |
| Alunos de uma sala recebem **429** | O app vê o mesmo IP para todos (NAT da rede ou proxy mal configurado) | Veja "Conferir o IP real" (seção 8); se a sala inteira usa o mesmo IP público, os acertos de código não contam, só as falhas |
| `app` reiniciando / `unhealthy` | Banco ainda subindo, variável faltando, erro de migração | `logs app`; `docker compose … config -q` acusa variável faltando |
| O log diz **"Configuração inválida"** | `SECRET_KEY`/`GABARITO_SAL` curtos demais ou ausentes | Corrija o `.env` (mínimo 32 e 16 caracteres) e `up -d` |
| `/saude` responde **503** | Banco inacessível ou schema fora de versão; o corpo diz qual | `logs app` e `logs db` |
| Construção falha ou trava | Pouca memória na VPS | `free -h`; `docker builder prune`; construa em horário de menor uso |

---

## 12. Cópia de segurança e restauração

**O que existe:** um `pg_dump` compactado, **semanal**, com **retenção de 8 semanas** (56 dias), conferência do arquivo (`pg_restore --list`) e soma de verificação. Os antigos só são apagados depois que o novo está pronto.

**Fazer a cópia:**

```bash
cd /opt/techquiz
sh docker/backup.sh        # grava em ./backups/techquiz-AAAAMMDD-HHMMSS.dump (+ .sha256)
```

**Agendar** (todo domingo às 3h) com `crontab -e`:

```cron
0 3 * * 0 cd /opt/techquiz && sh docker/backup.sh >> backups/backup.log 2>&1
```

**Cópia fora da VPS (obrigatória na prática):** backup só na própria VPS não protege contra perda do servidor. Defina `BACKUP_COPIA_CMD` (rsync, scp…) no ambiente do cron, por exemplo:

```cron
0 3 * * 0 cd /opt/techquiz && BACKUP_COPIA_CMD='rsync -a --chmod=F600 "$1" usuario@outro-servidor:/dados/techquiz/' sh docker/backup.sh >> backups/backup.log 2>&1
```

Use também o **snapshot da VPS** no hPanel.

**Quando rodar um backup manual** (por causa do risco de perder até uma semana de respostas): antes de **trocar o gabarito** de um questionário travado, ao **fim de cada coleta** e antes de **atualizar** o sistema.

**Teste de restauração** (faça logo após o primeiro backup e repita de vez em quando; não toca na produção):

```bash
sh docker/restaurar-teste.sh backups/techquiz-AAAAMMDD-HHMMSS.dump
```

**Restaurar de verdade** (desastre ou volta de versão):

```bash
cd /opt/techquiz
docker compose -f docker-compose.prod.yml stop app
docker compose -f docker-compose.prod.yml exec -T db sh -c 'dropdb -U "$POSTGRES_USER" "$POSTGRES_DB" && createdb -U "$POSTGRES_USER" "$POSTGRES_DB"'
cat backups/techquiz-AAAAMMDD-HHMMSS.dump | docker compose -f docker-compose.prod.yml exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-privileges --exit-on-error'
docker compose -f docker-compose.prod.yml up -d        # a subida aplica as migrações que faltarem
```

---

## 13. Dados: retenção e eliminação

Não há expiração automática nem exclusão pela interface (as coletas só podem ser desativadas): as respostas ficam até a instituição decidir. Os dados são **anônimos** (sem nome, e-mail, matrícula, IP ou avatar), mas **confirme o prazo de guarda com o comitê de ética**. Para eliminar uma coleta, faça **backup antes** e rode, trocando o código:

```bash
docker compose -f docker-compose.prod.yml exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"' <<'SQL'
BEGIN;
DELETE FROM partida WHERE coleta_id = (SELECT id FROM coleta WHERE codigo = 'ABCDE');   -- leva as respostas junto
DELETE FROM coleta  WHERE codigo = 'ABCDE';
COMMIT;
SQL
```

---

## 14. Segurança (resumo)

- `APP_ENV=production`: o app recusa subir sem segredos fortes e sem PostgreSQL; cookies `Secure`/`HttpOnly`/`SameSite=Lax`; CSRF em todos os formulários; CSP sem script inline; HSTS; mensagens de erro genéricas.
- Banco sem portas publicadas e fora da rede do Traefik.
- Contêiner da aplicação roda sem privilégios de administrador (usuário `app`, UID 10001).
- O `.env` fica só na VPS (`chmod 600`) e nunca vai para o Git nem para a imagem (`.dockerignore`).
- Mantenha o sistema operacional da VPS atualizado e o firewall (UFW) liberando só 22, 80 e 443.
- Atualize as imagens de vez em quando: `docker compose -f docker-compose.prod.yml pull db && docker compose -f docker-compose.prod.yml up -d --build`.

---

## 15. Variáveis de ambiente (referência)

| Variável | Obrigatória | Descrição |
|---|---|---|
| `APP_DOMAIN` | sim | `techquiz.institutoviva.digital` (sem `https://`) |
| `TRAEFIK_NETWORK` | sim | Rede Docker do Traefik (seção 3) |
| `TRAEFIK_ENTRYPOINT` | não (`websecure`) | Entrypoint HTTPS |
| `TRAEFIK_CERTRESOLVER` | não (`letsencrypt`) | Resolvedor de certificado |
| `SECRET_KEY` | sim | Assina a sessão (≥ 32 caracteres) |
| `GABARITO_SAL` | sim | Sal dos tokens do gabarito (≥ 16 caracteres); não trocar com coleta em andamento |
| `POSTGRES_PASSWORD` | sim | Senha do PostgreSQL |
| `POSTGRES_DB` / `POSTGRES_USER` | não | `techquiz` / `techquiz` |
| `TIMEZONE` | não | `America/Belem` (prazos das coletas) |
| `LOG_LEVEL` | não | `INFO` |
| `WEB_CONCURRENCY` | não | Processos do gunicorn (3) |
| `INSTITUICAO_NOME`, `INSTITUICAO_SUBTITULO`, `LOGO_INSTITUICAO`, `LOGO_PROGRAMA` | não | Identidade do painel e do jogo |
| `APP_VERSAO` | não (`latest`) | Rótulo da imagem construída (`techquiz-app:<versão>`) |
| `APP_BUILD_CONTEXT` | só no Método B | URL do Git para o build |
| `BACKUP_DIR`, `BACKUP_RETENCAO_DIAS`, `BACKUP_COPIA_CMD` | não | Usados por `docker/backup.sh` |

---

## 16. Verificação feita ao preparar este guia

Ambiente local equivalente (imagem construída do zero com Python 3.14, PostgreSQL 17 e Traefik 3.6 em contêineres, rede externa de teste, banco vazio):

- A imagem (275 MB) não contém `.env` nem `tests/` e roda como `app` (UID 10001). O compose recusa subir sem `SECRET_KEY`, `GABARITO_SAL` ou `POSTGRES_PASSWORD`.
- `app` e `db` ficam `healthy`; as migrações rodam sozinhas na subida; `/saude` mostra banco e schema `ok`.
- Pelo Traefik, em HTTPS: cabeçalhos de segurança do app presentes, `/setup` cria o super admin raiz, o login persiste e o dashboard abre; depois do primeiro cadastro `/setup` some (404).
- Um `X-Forwarded-For` forjado **não** chegou ao app: o Traefik o substituiu pelo IP real que viu.
- `docker/backup.sh` gerou o `.dump` e o `.sha256`; `docker/restaurar-teste.sh` restaurou num banco temporário (contagens e versão do schema conferidas) e **recusou** um arquivo corrompido.
- A sequência completa de **restaurar de verdade** (seção 12: parar o app, recriar o banco, `pg_restore`, subir de novo) **não foi executada de ponta a ponta** aqui; os comandos reaproveitam o `pg_dump` e o `pg_restore` já testados. Ensaie-a uma vez na VPS, num momento sem coleta em andamento, antes de precisar dela.
- O que **não** foi possível testar fora da VPS: o seu Traefik real (nomes da rede, do entrypoint e do resolvedor), o redirecionamento global de HTTP para HTTPS, o DNS e a emissão do certificado Let's Encrypt.
