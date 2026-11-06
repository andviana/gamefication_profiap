# Painel admin e coleta (Flask)

Backend do módulo de coleta de respostas. O plano completo está em [PLANO_ADMIN.md](PLANO_ADMIN.md). Este arquivo
cobre o que existe até agora (**Fases 0 a 4**: fundação, modelos e migrações, autenticação e usuários, cadastros, questionários, importação e coletas).

## Desenvolvimento

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env        # ajuste se quiser; em desenvolvimento tudo tem valor padrão
flask db upgrade            # cria/atualiza o banco (SQLite em instance/dev.db)
flask seed-dev              # campi e cursos de exemplo (só dev; recusa rodar em produção)
flask run                   # http://127.0.0.1:5000  ->  /saude, /setup (1º acesso), /entrar
pytest                      # testes (SQLite em memória)
```

O `.flaskenv` já define `FLASK_APP=app:create_app`, então os comandos `flask ...` funcionam sem parâmetros.

### Testes também no PostgreSQL

Defina `TEST_DATABASE_URL` com um banco **descartável** (os testes apagam o schema `public` a cada teste):

```bash
docker run -d --rm --name techquiz-pg-teste -e POSTGRES_PASSWORD=teste_descartavel -e POSTGRES_DB=techquiz_teste \
  -p 127.0.0.1:55432:5432 postgres:17-alpine
TEST_DATABASE_URL=postgresql://postgres:teste_descartavel@127.0.0.1:55432/techquiz_teste pytest
docker stop techquiz-pg-teste
```

O Docker é só ferramenta de teste local; a produção roda sem Docker (ver o plano, Fase 7).

## Primeiro acesso, perfis e recuperação

- **Primeiro acesso:** com o banco vazio, qualquer endereço leva a `/setup`, onde se cria o **super admin raiz**. Essa página
  responde 404 assim que existe um usuário. **Em produção, faça o setup logo após o deploy e antes de divulgar a URL**:
  quem abrir primeiro vira o dono do sistema.
- **Perfis:** raiz (único, imutável), super admin (promovido só pela raiz) e comum. A matriz completa está na seção 13 do plano
  e é imposta nos serviços (`app/permissoes.py`), não só escondendo botões.
- **Login:** 5 senhas erradas seguidas travam o usuário por 10 min (valores em `.env`). A sessão expira após 8 h sem uso e é
  derrubada quando a senha ou o perfil do usuário são alterados por outra pessoa.
- **Esqueceu a senha da raiz?** No servidor: `flask redefinir-superadmin` (pede a nova senha, derruba as sessões e destrava o login).
  É o único comando de produção; não existe caminho equivalente pela web.
- Eventos sensíveis (criação, promoção, revogação, exclusão, redefinição de senha) vão para o logger `techquiz.auditoria`.

## Questionários, perguntas e importação

- **Cadastros** (campus, curso, grupo): qualquer usuário logado cria, renomeia e inativa/reativa. Nada é apagado.
- **Questionário:** reúne perguntas e o texto de orientações (com o aviso de privacidade). O **estado é derivado**, não gravado:
  *rascunho* (sem coleta), *em coleta* (tem coleta, sem resposta) e *travado* (já há respostas).
- **Travado:** só se corrige texto. Adicionar/remover perguntas ou alternativas, mudar número, grupo ou gabarito exige **duplicar**
  o questionário. Exceção: um super admin pode **trocar o gabarito**, e o sistema recalcula os acertos já gravados (com auditoria).
- **Perguntas:** de 2 a 4 alternativas (A a D, limite do jogo), exatamente uma correta. O banco reforça as regras (uma correta por
  pergunta; pergunta com resposta não pode ser apagada).
- **Importar CSV** (só super admin): `perguntas.csv` + `alternativas.csv` -> prévia sem gravar -> confirmar. Cria um questionário
  **novo** em rascunho e **não altera nada** que já exista. A prévia vale 15 min e só pode ser confirmada uma vez. Modelos para
  baixar na própria tela; os CSVs atuais em `data/` já passam na validação.

## Coletas

- Uma **coleta** é uma turma: vincula um questionário a campus, curso, ano e período, e gera um **código de 5 letras** (sem I, L e O)
  que os alunos digitam ao abrir o jogo. O código não muda.
- **Prazo:** de 00:00 do dia de início até 23:59:59 do dia de fim, no fuso `TIMEZONE`. **Situação:** *aberta*, *agendada*,
  *encerrada* ou *desativada* (calculada na hora; desativar derruba o código mesmo dentro do prazo).
- **Ano:** ano atual − 1, atual e atual + 1. **Duplicidade** (mesma turma) é permitida, com aviso e confirmação.
- Só questionários **com perguntas** podem ser vinculados. Vincular um rascunho o passa a "em coleta" e a estrutura dele trava na
  primeira resposta.
- **Depois da 1ª partida** a identidade da turma (questionário, campus, curso, ano, período) trava; prazo e ativar/desativar seguem
  livres. Coletas não são apagadas, só desativadas.

## O jogo e a API pública

O jogo é servido na raiz `/` (arquivos em `app/static/game/`). Sem login, ele usa dois endpoints JSON (CSRF isento, `Cache-Control: no-store`, corpo até 64 KB):

- `POST /api/coleta/iniciar` `{codigo}`: confere o código e devolve o questionário (orientações, perguntas, alternativas e, por pergunta, `token_correta`; **nunca** a letra correta). O token é `SHA-256(sal + questionario_id + numero + letra)`; o jogo calcula o token de cada letra para dar o feedback na hora.
- `POST /api/partidas` `{uuid, codigo, respostas:[{pergunta, alternativa, tempo_ms, ordem}]}`: grava a partida (201) e é **idempotente** pelo UUID (reenvio devolve 200). O servidor recalcula o acerto. Não recebe nome, avatar, XP nem IP.
- Erros com `motivo` estável: `inexistente` (404), `inativa` e `fora_do_prazo` (410), `coleta_encerrada` (410), `questionario_alterado` e `uuid_em_uso` (409), `limite_excedido` (429 com `Retry-After`), `invalido` (422), `corpo_grande` (413).
- **Rate limit** por IP só nas **falhas** de código (padrão 10 por minuto, bloqueio de 5 min), guardado em `tentativa_falha`. Atrás de proxy, configure `PROXIES_CONFIAVEIS` para o IP ser o do cliente.

Testes do jogo: `pytest` já executa a suíte de Node (precisa do `node` no PATH; `node --test tests/js/api.test.js` roda só ela) e `/static/game/teste.html` traz 38 verificações no navegador.

## Dashboard

Em `/admin/dashboard` (qualquer usuário logado): escolha um questionário (obrigatório) e filtre por coleta, campus, curso, ano, período, grupo, questão e data. Clicar numa barra ou célula filtra; clicar de novo desfaz, e o gráfico clicado continua mostrando as outras categorias. O endereço guarda os filtros, então dá para compartilhar um recorte. Cada gráfico tem **PNG** e **Tabela** (os mesmos dados em texto), e a tabela de dados no fim exporta o **CSV** do recorte. A opção *Usar padrões nas barras* ajuda quem tem daltonismo ou imprime em preto e branco.

### API de leitura

Qualquer usuário logado consulta `GET /admin/api/dashboard/…` (JSON; sem login responde 401). Todos os endpoints pedem `questionario=<id>` e aceitam os mesmos filtros: `coleta` (código), `campus`, `curso`, `ano`, `periodo`, `grupo`, `questao`, `de` e `ate` (AAAA-MM-DD, no fuso `TIMEZONE`, fim inclusivo) ou `dias=N`. Os de lista aceitam valores repetidos ou separados por vírgula.

| Endpoint | Devolve |
|---|---|
| `questionarios` | cartões para escolher o questionário (sem pedir `questionario`) |
| `opcoes` | valores existentes para a barra de filtros |
| `resumo` | respondentes, respostas, acertos, erros, % e tempo mediano, mais o `geral` sem filtros |
| `questoes?ordem=erro\|acerto&limite=10` | ranking de questões |
| `grupos`, `comparativo?dim=`, `heatmap?dim=` | % de erro por grupo, por campus/curso/ano/período e grupo × dimensão |
| `questao/<n>` | detalhe e distribuição das alternativas escolhidas |
| `evolucao?passo=semana\|dia` | partidas ao longo do tempo |
| `tabela?aba=` e `export.csv?aba=` | tabela com totais e o CSV do recorte (abas: questao, grupo, campus, curso, ano, periodo, coleta) |

% de erro = erros ÷ respostas do recorte (ponderado); tempo = mediana; respondente = partida (quem joga duas vezes conta duas vezes).

## Configuração (ENV)

Toda a configuração vem de variáveis de ambiente (arquivo `.env` em desenvolvimento), lida **uma vez** por
`app.config.get_settings()` e imutável. Os valores padrão e a lista completa estão em [.env.example](.env.example).

Em **produção** (`APP_ENV=production`) o app se recusa a subir se faltar `DATABASE_URL` (PostgreSQL), `SECRET_KEY`
(>= 32 caracteres) ou `GABARITO_SAL` (>= 16 caracteres). A mensagem lista todos os problemas de uma vez.

## Banco e migrações

- Desenvolvimento: SQLite (`instance/dev.db`), com chaves estrangeiras ligadas. Produção: PostgreSQL.
- Não há comando próprio para criar o banco: use `flask db upgrade`.
- Nunca edite uma migração já aplicada em outro ambiente. Para mudar o schema: altere os modelos e rode `flask db migrate -m "descrição"`, revise o arquivo gerado e aplique com `flask db upgrade`.
- `wsgi.py` (gunicorn) **falha ao subir** se o schema estiver ausente ou desatualizado, dizendo o que fazer.
  `GET /saude` informa o estado (`ok`, `sem_migracoes`, `ausente`, `desatualizado`) e responde 503 se estiver degradado.

## Produção

O procedimento completo (instalação, HTTPS, systemd, backup semanal, atualização, restauração e recuperação de acesso) está em
**[README_OPERACAO.md](README_OPERACAO.md)**, para o setor de TI. Os modelos revisáveis ficam em [`deploy/`](deploy/): serviço
do systemd, `gunicorn.conf.py`, site do Nginx, `techquiz.env.example`, backup (`techquiz-backup.sh` e timer semanal), teste de
restauração e `smoke-test.sh` (verificação pós-deploy).

## Estrutura

```
app/
  __init__.py      create_app (fábrica)
  config.py        Settings (singleton, validado)
  extensions.py    db, migrate, login_manager, csrf
  container.py     montagem das dependências
  errors.py        exceções de domínio
  http_errors.py   tradução de exceções em resposta (JSON na API, HTML no painel)
  db_schema.py     verificação do schema (Alembic)
  auth_web.py      carregador de sessão (id:token) e decoradores de permissão
  permissoes.py    quem pode gerenciar, promover e revogar quem (funções puras)
  auditoria.py     registro de eventos sensíveis
  blueprints/      saude, auth, admin (usuários, cadastros, questionários, perguntas, importação, coletas), api (jogo), jogo (/)
  templates/ static/   gov.br DS, Font Awesome e Raleway servidos localmente (sem CDN)
  cli.py           seed-dev (somente desenvolvimento) e redefinir-superadmin
  models/          12 tabelas (usuario, campus, curso, grupo, questionario, pergunta, alternativa,
                   coleta, partida, resposta, tentativa_falha, importacao_previa) e o tipo UTCDateTime
  repositories/    acesso ao banco
  services/        regras de negócio (usuários, autenticação, referências, questionários, perguntas, importação, coletas, jogo, ratelimit, gabarito)
                   csv_import.py é o analisador de CSV, puro (sem banco)
migrations/        Alembic (Flask-Migrate)
deploy/            modelos de produção (systemd, Nginx, gunicorn, backup)
tests/            (tests/js: Node)
wsgi.py
```
