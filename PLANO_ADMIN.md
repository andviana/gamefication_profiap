# Plano de Implementação — Módulo Admin e Coleta de Dados

Status: planejamento (nenhum código escrito). Decisões fechadas em 2026-11-05.

## 1. Objetivo

Coletar respostas anônimas dos alunos e permitir a análise por campus, curso, ano, período, grupo e questão. O sistema tem três partes:

1. **Jogo** (front existente), com tela de código e leitura de perguntas via API.
2. **API pública JSON** para validar código, entregar perguntas e receber partidas.
3. **Painel admin** (Flask MVC, com login) para gerir cadastros, questionários, coletas, usuários e o dashboard.

Os dados se organizam assim: um **questionário** reúne as perguntas e o texto de orientações; uma **coleta** (código da turma) vincula um questionário a campus, curso, ano e período; as **partidas** dos alunos pertencem à coleta.

## 2. Decisões consolidadas

| Tema | Decisão |
|---|---|
| Arquitetura | Um único app Flask serve o jogo estático e a API, na mesma origem (sem CORS) |
| Perguntas e questionários | O banco é a fonte da verdade; sem arquivo em runtime. As perguntas pertencem a um **questionário**; cada coleta vincula um questionário e o jogo recebe o questionário da coleta pela API |
| Estrutura do questionário | **Rascunho** (sem coleta): edição livre. **Em coleta** (tem coleta, sem resposta): estrutura ainda editável, com aviso. **Travado** (a partir da 1ª resposta): não adiciona nem remove perguntas/alternativas; permite corrigir texto e trocar o gabarito (com recálculo, só super admin). Mudança de estrutura = **duplicar** o questionário e editar a cópia |
| Importação de perguntas | Só pela tela de upload no admin, **só super admin** (sem comando CLI). Upload dos 2 CSVs → prévia → confirmação → cria um **novo questionário**. **Não apaga nada** (decisão que substitui o "zerar tudo") |
| Orientações e privacidade | Texto **por questionário**, editado no admin (formato atual: `# título`, `- item`, parágrafos, `{{totalPerguntas}}` etc.); o aviso de privacidade fica dentro dele. O jogo o recebe da coleta pela API |
| Coleta | Vincula um questionário. Coletas repetidas são permitidas, com **aviso de duplicidade** (mesmo questionário, campus, curso, ano e período). Ano = lista com **ano atual − 1, atual e atual + 1** |
| Valores padrão (todos por ENV) | Rate limit do código: **10 falhas/min por IP, bloqueio de 5 min**. Sessão do painel: **8 h de inatividade**, cookie seguro e `SameSite=Lax`. Login: **5 senhas erradas seguidas travam o usuário por 10 min**. Prévia de importação: 15 min. Upload de CSV: 2 MB. Fuso `America/Belem`. Idioma `pt-BR` |
| Backup em produção | `pg_dump` **semanal**, retenção de **8 semanas**, por timer do systemd, com cópia fora do servidor definida pela TI |
| Retenção | **Sem expiração automática**: as respostas ficam até a instituição decidir. Não há exclusão de coleta pela interface (preserva o histórico). Por serem anônimas, não há titular a localizar; a eliminação, se exigida, é feita pelo administrador do banco |
| XP | **Não é gravado**; a análise usa só respostas, acertos e tempo (que o servidor controla) |
| Produção | Servidor da instituição, **sem Docker**: gunicorn + systemd + Nginx (HTTPS) + Postgres (ver Fase 7) |
| Upload de CSV | Até 2 MB por arquivo, UTF-8 com ou sem BOM, delimitador `;` ou `,`, extensão `.csv`; limite configurável por ENV |
| Código de acesso | 5 letras sem ambíguas, regenera em colisão |
| Rate limit | Só tentativas falhas contam, por IP; contador na tabela `tentativa_falha` (sem Redis nem Flask-Limiter) |
| Prazo da coleta | Só datas, fim inclusivo, fuso do ENV (padrão America/Belem) |
| Gabarito na API | Token por alternativa (hash de pergunta + letra + sal); o JS compara o hash da escolhida (`crypto.subtle`). Ofuscação, não segurança. Exige HTTPS em produção |
| Anonimato em amostras pequenas | Sem tratamento especial no dashboard (decisão do usuário); mostra sempre o `n` |
| Senha | Mínimo 8 caracteres, sem outras regras |
| Partidas | Código por turma, UUID anônimo gerado no cliente, grava só ao finalizar |
| Integridade | Snapshot na resposta; campus, curso e grupo em uso só inativam; perguntas só são removidas em rascunho (travado, nunca); nada é apagado por importação |
| Grupo | Tabela `grupo`; o `Título` fica como tema da pergunta |
| Dashboard | API de agregação SQL + **ECharts** (servido localmente). **Questionário obrigatório e sem padrão**: a página abre pedindo a escolha; nada é agregado entre questionários. Especificação na seção 11 |
| Formulários | Flask-WTF (CSRF e validação) |
| Usuários e perfis | Flask-Login com 3 níveis: **super admin raiz** (o 1º usuário, criado no setup público; imutável), **super admin promovido** e **usuário comum**. Matriz de permissões na seção 13 |
| Exportações | Importar CSV: só super admin. CSV do recorte e PNG do dashboard: qualquer usuário logado. Não existe mais backup obrigatório da importação |
| Interface do painel | Design system do governo federal (gov.br DS), servido localmente. Seção 12 |
| Banco | SQLAlchemy + Flask-Migrate, SQLite em dev e Postgres em produção |
| Config | Variáveis de ENV, carregadas por um singleton |

## 3. Arquitetura

Camadas, com dependências sempre apontando para baixo:

```
Blueprints (controllers: HTTP, validação de entrada, resposta)
   └─ Services (regras de negócio, transações)
        └─ Repositories (consultas SQLAlchemy)
             └─ Models (entidades)
```

- **App factory** (`create_app`) que recebe a config, para facilitar os testes.
- **Injeção de dependências:** repositories e services são montados num contêiner simples (`extensions`/`container.py`) e injetados nos blueprints. Não usamos framework de DI, para manter o KISS.
- **Config singleton:** uma classe `Settings` que lê o ENV uma única vez, valida e fica imutável. Dev, prod e test se diferenciam por `APP_ENV`.
- **Early return/early stop:** validações na entrada das funções, com retorno ou erro imediato.
- **Erros:** exceções de domínio (`CodigoInvalido`, `ColetaExpirada` etc.) são traduzidas num único handler.

### Estrutura de pastas (como ficou)

```
projeto_adam/
├─ app/
│  ├─ __init__.py            # create_app, cabeçalhos de segurança
│  ├─ config.py  extensions.py  container.py  errors.py  http_errors.py
│  ├─ auth_web.py  permissoes.py  auditoria.py  db_schema.py  cli.py
│  ├─ models/                # usuario, referencias (campus, curso, grupo), questionario (+pergunta,
│  │                         # alternativa), coleta (+partida, resposta), controle (tentativa_falha,
│  │                         # importacao_previa), tipos (UTCDateTime)
│  ├─ repositories/          # acesso ao banco, um por assunto
│  ├─ services/              # auth, usuarios, referencias, questionarios, perguntas, importacao,
│  │                         # csv_import, coletas, jogo, gabarito, ratelimit, dashboard, senha
│  ├─ blueprints/
│  │  ├─ auth/               # entrar, sair, setup, alterar senha
│  │  ├─ admin/              # usuários, cadastros, questionários, perguntas, importação, coletas,
│  │  │                      # dashboard (página e API JSON em /admin/api/dashboard)
│  │  ├─ api/                # API pública do jogo (/api/coleta/iniciar, /api/partidas)
│  │  ├─ jogo.py             # serve o jogo na raiz /
│  │  └─ saude/              # /saude
│  ├─ templates/             # base e telas do painel (gov.br DS)
│  ├─ textos/                # texto padrão das orientações
│  └─ static/
│     ├─ game/               # o jogo (index.html, js, css, assets, teste.html)
│     ├─ css/ js/ img/       # painel e dashboard
│     └─ vendor/             # gov.br DS, Font Awesome, Raleway e ECharts, locais (sem CDN)
├─ migrations/               # Alembic
├─ deploy/                   # modelos de produção (systemd, Nginx, gunicorn, backup, smoke test)
├─ tests/                    # pytest (SQLite e PostgreSQL) e tests/js (Node)
├─ data/                     # CSVs de exemplo e referência do formato
├─ README.md  README_ADMIN.md  README_OPERACAO.md  ESCOPO.md  PLANO_ADMIN.md
├─ .env.example  requirements.txt  requirements-dev.txt  wsgi.py
```

O jogo foi movido para `app/static/game/` na Fase 5 e usa `<base href="/static/game/">`.

## 4. Modelo de dados

Convenções: `id` inteiro (exceto `partida`, que usa UUID), `ativo` booleano para inativar campus, curso e grupo, timestamps em UTC.

| Tabela | Campos principais | Restrições |
|---|---|---|
| `usuario` | id, nome, login, senha_hash, perfil (`comum` \| `superadmin`), raiz (bool), criado_em | login único; exatamente **um** usuário com `raiz=true` (o primeiro), que tem `perfil=superadmin`; `raiz` nunca é alterável pela aplicação |
| `campus` | id, nome, ativo | nome único |
| `curso` | id, nome, ativo | nome único |
| `grupo` | id, nome, ativo | nome único |
| `questionario` | id, nome, descricao, orientacoes (texto), derivado_de_id (nulo), criado_em | nome único; o **estado é derivado**, não armazenado: *rascunho* (sem coleta), *em coleta* (tem coleta, sem resposta), *travado* (tem ao menos uma resposta) |
| `pergunta` | id, questionario_id, numero, texto, titulo, grupo_id, autoajuda | (questionario_id, numero) único; FK questionário e grupo; sem soft delete (remoção só em rascunho) |
| `alternativa` | id, pergunta_id, letra, texto, correta, texto_acerto, texto_erro | (pergunta_id, letra) único; no máximo 1 correta por pergunta (garantido pelo banco, por índice parcial único) |
| `coleta` | id, codigo, questionario_id, campus_id, curso_id, ano, periodo, data_inicio, data_fim, ativo, criada_em | codigo único (5 chars); periodo ∈ {1,2}; ano ∈ {atual−1, atual, atual+1} (validado no service); data_fim ≥ data_inicio; o questionário não muda depois da 1ª partida |
| `partida` | id (UUID), coleta_id, finalizada_em, total_acertos, total_perguntas (ambos calculados no servidor; sem XP) | PK UUID garante idempotência |
| `resposta` | id, partida_id, pergunta_id, alternativa_id, acertou, ordem, tempo_ms, mais o snapshot (`pergunta_numero`, `pergunta_titulo`, `grupo_nome`, `alternativa_letra`) | (partida_id, pergunta_id) único |
| `tentativa_falha` | id, tipo (`codigo` \| `login`), chave (IP para `codigo`; login do usuário para `login`), momento | índice (tipo, chave, momento); linhas antigas removidas periodicamente. Serve ao rate limit do código por IP e ao bloqueio de login por usuário |
| `importacao_previa` | token, usuario_id, nome do questionário, payload (JSON já validado), expira_em, usada | token único; uso único; expira em ~15 min (evita criar dois questionários com duplo clique) |

Observações:

- **Snapshot:** a resposta guarda também o texto/nome vigente no momento. Como o texto pode ser corrigido depois de travado, o histórico não muda. O dashboard agrega por esses campos de snapshot (`pergunta_numero`, `grupo_nome`), nunca pelo texto atual.
- **Grupo** é global (compartilhado entre questionários) e não é apagado por importação.
- **Troca de gabarito** em questionário travado recalcula `acertou` das respostas daquela pergunta (e `total_acertos` das partidas afetadas) numa transação (ver Fase 3).
- **Índices:** `coleta.codigo`, `coleta.questionario_id`, `resposta.pergunta_id`, `partida.coleta_id` e `partida.finalizada_em`, para o dashboard.
- **Campus e curso na coleta:** o dashboard junta com `coleta`, que carrega campus, curso, ano e período. Não duplicamos esses dados em `partida`.
- Não gravamos avatar, IP ou qualquer dado identificável.

## 5. Contratos da API pública

| Método e rota | Função |
|---|---|
| `POST /api/coleta/iniciar` `{codigo}` | Verifica se o código existe, está ativo e dentro do prazo. Se ok, devolve o **questionário da coleta**: texto de orientações (com privacidade) e as perguntas com alternativas, em ordem fixa por número (alternativas por letra), como o jogo faz hoje. Não envia flag `correta`: cada alternativa leva um token e a pergunta leva o token da correta (ver abaixo). Em falha, retorna um motivo (`inexistente`, `inativa`, `fora_do_prazo`), registra em `tentativa_falha` e, acima do limite por IP, responde 429 com o tempo de espera. Código válido não conta. |
| `POST /api/partidas` | Corpo: `{uuid, codigo, respostas:[{pergunta, alternativa, tempo_ms, ordem}]}` (sem XP). Revalida o código e o prazo, confere que as perguntas pertencem ao questionário da coleta, recalcula `acertou` no servidor, grava a partida e as respostas numa única transação e responde 201. Um UUID repetido retorna sucesso idempotente. |

Regras:

- O servidor é a autoridade para **acertou/errou**, e nunca confia no flag enviado pelo cliente.
- Se o código expirar entre o início e o fim da partida, a gravação é recusada com mensagem clara. O jogo mostra o relatório mesmo assim, avisando que não foi salvo.
- Falha de rede ao salvar: o jogo faz até 3 tentativas automáticas (falha de servidor ou de rede é repetida; erro 4xx não) e, se ainda falhar, avisa no pódio e oferece **Tentar enviar de novo**. Reenviar nunca duplica a partida (UUID).
- Coleta desativada ou fora do prazo ao salvar: resposta 410 com motivo `coleta_encerrada`. O jogo mostra "Esta coleta foi encerrada; suas respostas não foram salvas" e ainda exibe o relatório. Perguntas que não pertencem ao questionário da coleta são rejeitadas (422, motivo `invalido`).
- O XP e a pontuação do jogo continuam existindo no cliente como mecânica, mas **não são enviados nem gravados**.

**Esquema do gabarito (ofuscação):**
- O token de uma letra é `SHA-256(sal_global + questionario_id + numero_pergunta + letra)`. O servidor envia o `sal` (que vem do ENV) e, por pergunta, apenas o `token_correta`; o jogo calcula o token de cada letra (nenhuma alternativa traz token).
- Cada pergunta traz `token_correta`. O jogo calcula o token da letra escolhida com `crypto.subtle.digest` e compara com `token_correta` para o feedback imediato.
- Não existe campo `correta` no JSON. Isto é ofuscação: quem ler o JS pode calcular o token das 5 letras. Não protege contra ataque deliberado.
- `crypto.subtle` só existe em contexto seguro (HTTPS ou localhost). Quando falta, o jogo usa um SHA-256 próprio em JavaScript, então não quebra; ainda assim, em produção o sistema deve ser servido por HTTPS, o que o cookie de sessão seguro do painel exige.
- O servidor continua sendo a autoridade: ao gravar a partida, recalcula `acertou` pela alternativa enviada.

## 6. Fases de implementação

Cada fase termina com testes passando e algo demonstrável.

### Fase 0 — Fundação (**concluída**)
- Estrutura de pastas, `requirements.txt`, `.env.example`, `Settings` singleton, app factory, extensões, handler de erros.
- Conexão SQLite (dev) e Postgres (prod) por `DATABASE_URL`.
- Pytest com fixtures de app e banco em memória.
- Criação do banco: sem comando próprio. Usa o `flask db upgrade` padrão do Flask-Migrate, executado no deploy (entrypoint/README) e no setup de dev. O app, ao subir, falha com mensagem clara se o schema estiver ausente ou desatualizado.
- **Pronto quando:** `flask run` sobe, `/saude` responde e os testes de config passam.
- **Resultado:** 38 testes passando. Entregues: `app/` (fábrica, `Settings` singleton validado, extensões, contêiner, exceções de domínio, tratamento de erros JSON/HTML, verificação de schema, `/saude`), `migrations/` (Flask-Migrate inicializado, sem revisões ainda), `wsgi.py`, `.env.example`, `requirements*.txt` com versões fixas e `README_ADMIN.md`. Python 3.14, Flask 3.1.3, SQLAlchemy 2.1.8, psycopg 3.3.8.
- **Decisões de implementação:** `wsgi.py` verifica o schema ao subir e o CLI do Flask (`FLASK_APP=app:create_app`) não, para `flask db upgrade` poder rodar; SQLite com chaves estrangeiras ligadas; `postgres://` é normalizado para o driver psycopg 3; o carregador de usuário do Flask-Login é provisório até a Fase 2.
- **Ainda não verificado:** execução contra um PostgreSQL real (não há servidor Postgres neste ambiente); entra na Fase 1, junto com a primeira migração.

### Fase 1 — Modelos e migrações (**concluída**)
- Todos os modelos da seção 4 e a migração inicial.
- Seed de desenvolvimento (campi e cursos de exemplo).
- **Pronto quando:** `flask db upgrade` roda limpo em SQLite e em Postgres.
- **Resultado:** 12 tabelas, migração inicial `b1ce84a00cae`, comando `flask seed-dev` (4 campi e 4 cursos, idempotente, recusa produção). **86 testes no SQLite e 90 no PostgreSQL 17.11** (contêiner temporário), incluindo: a migração produz exatamente o schema dos modelos, e o downgrade a desfaz.
- **O banco garante as regras, e não só o código:** uma única raiz e raiz sempre super admin; uma única alternativa correta por pergunta (índices parciais iguais nos dois bancos); código de coleta com 5 caracteres, período 1 ou 2 e prazo coerente; totais da partida coerentes; uma resposta por (partida, pergunta); FKs `RESTRICT` impedem apagar pergunta, alternativa, questionário, campus ou curso com respostas ou coletas; `CASCADE` só onde é seguro (alternativas de uma pergunta, perguntas de um questionário em rascunho, respostas de uma partida, prévias de um usuário).
- **Decisões de implementação:** datas sempre em UTC com fuso (`UTCDateTime` recusa `datetime` sem fuso; a migração grava `sa.DateTime(timezone=True)` para ser autossuficiente); convenção de nomes de constraints; `render_as_batch` para o SQLite poder alterar tabelas; UUID nativo no Postgres.
- **Descoberta no teste em Postgres:** string maior que a coluna é recusada nos dois bancos, mas por mecanismos diferentes (CHECK no SQLite, largura do `varchar` no Postgres). Os testes aceitam os dois.
- **Mudança no plano:** `flask seed-dev` é ferramenta de desenvolvimento; o "único comando CLI" da Fase 2 vale para **produção** (`flask redefinir-superadmin`).

### Fase 2 — Autenticação e usuários (**concluída**)
- Setup do 1º acesso (rota existe apenas com a tabela vazia, depois 404): o usuário criado é o **super admin raiz**. Login, logout, `login_required` nas rotas do admin e decorator `superadmin_required` nas rotas restritas.
- Hash de senha (werkzeug), senha com no mínimo 8 caracteres. Qualquer usuário altera a própria senha informando a senha atual.
- CRUD de usuários (só super admin), com as regras da seção 13 (a raiz é intocável; só a raiz promove e revoga super admins; super admin promovido gerencia apenas usuários comuns; ninguém exclui a si mesmo).
- Comando `flask redefinir-superadmin` (único comando CLI do sistema): redefine a senha da raiz, exige acesso ao shell do servidor e pede a senha no prompt. Para recuperação de acesso; não existe equivalente na web.
- **Bloqueio de login:** 5 senhas erradas seguidas travam o usuário por 10 min (contador em `tentativa_falha`, tipo `login`); a mensagem de erro é genérica, sem revelar se o login existe. Sessão expira após 8 h de inatividade.
- CSRF nos formulários (Flask-WTF). Cookies de sessão seguros em produção (`Secure`, `HttpOnly`, `SameSite=Lax`).
- **Pronto quando:** fluxo setup → login → CRUD funciona, rotas protegidas redirecionam ao login, e a matriz de permissões da seção 13 passa nos testes.
- **Resultado:** 188 testes no SQLite (a suíte também passou no PostgreSQL 17 antes dos últimos ajustes). Entregues: setup público que se fecha (404), login com bloqueio, logout (POST), troca da própria senha, CRUD de usuários, promover e revogar, `flask redefinir-superadmin`, auditoria, e as telas no gov.br DS com as logos da UFRA e do PROFIAP. Verificado no navegador: setup (erro e sucesso), login, logout, início, lista de usuários como raiz e como super admin promovido.
- **Decisões de implementação:** (1) o modelo ganhou `usuario.sessao_token` (migração `beafbd7d3252`, que preenche usuários já existentes); a sessão guarda `id:token`, e trocar o token derruba as sessões de quem teve senha, perfil ou login alterados por outra pessoa. (2) A matriz de permissões vive em `app/permissoes.py` e é imposta nos *services* (403 mesmo com a rota chamada à mão), e a interface só esconde o que o perfil não pode usar. (3) Criar usuário sempre cria *comum*; promover é ação à parte, só da raiz. (4) Login e senha de usuários são validados em um lugar só (service); os formulários apenas exigem preenchimento (DRY). (5) A auditoria vai para o logger `techquiz.auditoria`; a Fase 7 pode direcioná-lo a arquivo. (6) Os logos do painel são caminhos relativos a `app/static/` (`LOGO_INSTITUICAO=img/logo_ufra.png`).
- **Testes de mutação:** quebrei de propósito o token de sessão, a regra de promovido × super admin e o bloqueio de login; os testes detectaram os três. Uma mutação na proteção da raiz passou porque a linha é redundante (a raiz já cai na regra de super admin).
- **Pendências desta fase:** o formulário mostra o primeiro erro de validação de cada vez, e não todos juntos; o confirmar de exclusão usa `confirm()` do navegador, a trocar por modal do DS junto com o resto dos modais.

### Fase 3 — Cadastros, questionários e perguntas (**concluída**)
- CRUD de campus, curso e grupo (inativar em vez de apagar).
- **Questionários:** listagem com o estado derivado (rascunho, em coleta, travado), número de perguntas, de coletas e de respostas. Criar, renomear, editar o texto de orientações e excluir (**só em rascunho**, sem coleta).
- **Perguntas e alternativas** de um questionário, com validações: exatamente 1 correta, letras únicas, grupo obrigatório, número único dentro do questionário.
- **Regras por estado:**
  - *Rascunho:* qualquer alteração (adicionar, remover, reordenar, trocar gabarito).
  - *Em coleta* (tem coleta, sem resposta): estrutura ainda editável, com aviso fixo: "Este questionário tem N coleta(s); a estrutura trava na primeira resposta".
  - *Travado* (a partir da 1ª resposta): **não** adiciona nem remove perguntas ou alternativas; permite corrigir **texto** (enunciado, título, alternativas, feedbacks, autoajuda) e as **orientações**; permite **trocar o gabarito** com recálculo (abaixo). Para mudar a estrutura, **duplicar**.
  - A trava é aplicada no service (e não só escondendo botões); tentativa de violar responde 409.
- **Trocar gabarito de questionário travado (só super admin):** tela de confirmação mostra quantas respostas e partidas serão recalculadas; numa única transação atualiza `acertou` das respostas daquela pergunta, o `total_acertos` das partidas afetadas e o snapshot da letra correta; registra no log de auditoria (quem, quando, pergunta, gabarito antigo e novo, contagens). O dashboard passa a refletir o novo critério imediatamente.
- **Duplicar questionário** (qualquer usuário que edita perguntas): copia perguntas, alternativas e orientações para um novo **rascunho** (sem coletas nem respostas), com `derivado_de_id` apontando para o original e nome sugerido "(cópia)".
- **Importar CSV** (**só super admin**; não há comando CLI; o item de menu nem aparece para usuários comuns e a rota responde 403). **Cria um novo questionário e não apaga nada:**
  1. O admin informa o nome (e descrição) e envia `perguntas.csv` e `alternativas.csv`. Upload: até 2 MB por arquivo (configurável), extensão `.csv`, UTF-8 com ou sem BOM, delimitador `;` ou `,` detectado na primeira linha. Outra codificação é rejeitada com mensagem clara.
  2. O sistema valida tudo **sem gravar** e mostra a prévia: total de perguntas, alternativas e grupos novos, e erros por linha (número duplicado, mais de uma correta, letra repetida, pergunta sem alternativas etc.). Com erro, a importação fica bloqueada. A prévia gera um token de uso único, válido por ~15 minutos, com o conteúdo validado em `importacao_previa` (no banco, porque pode haver vários workers).
  3. Ao confirmar, numa única transação, cria o questionário (em rascunho) com o texto de orientações padrão, cria os grupos que faltarem e insere as perguntas e alternativas. Se algo falhar, nada é criado. Token reutilizado ou expirado é recusado.
  - O antigo `data/orientacoes.txt` serviu de modelo para o texto de orientações padrão (hoje em `app/textos/`; o arquivo foi removido).
  - Registrar no log quem importou, quando e o questionário criado.
- **Pronto quando:** os 2 CSVs atuais viram um questionário pela tela, as perguntas aparecem no admin, o estado do questionário muda conforme as regras (rascunho → em coleta → travado), a estrutura travada é recusada no service, a troca de gabarito recalcula corretamente e duplicar gera um rascunho editável.
- **Resultado:** 357 testes no SQLite e 362 no PostgreSQL 17 (1 é específico do SQLite). Entregues: cadastros de campus/curso/grupo; questionários (criar, editar, orientações, duplicar, excluir só rascunho, estado derivado); perguntas e alternativas com as travas; troca de gabarito com recálculo; importação de CSV com prévia e confirmação; `csv_import.py` (analisador puro). Os CSVs atuais de `data/` importam sem erro: 8 perguntas, 28 alternativas, 3 grupos, com os mesmos gabaritos do protótipo. Verificado no navegador: importação completa, edição de pergunta, estado travado e a troca de gabarito (acertos por partida de `[2,2,2,3,2]` para `[3,1,3,3,1]`, sem nenhuma partida incoerente).
- **Decisões de implementação:** (1) o jogo suporta **2 a 4 alternativas (A a D)**; o limite vale no formulário, no serviço e na importação. (2) Com respostas gravadas, além de adicionar/remover, **número e grupo da pergunta também travam**: trocar o grupo separaria a mesma pergunta em dois grupos no dashboard (o snapshot das respostas antigas guarda o grupo antigo). (3) O gabarito de questionário travado só muda pela ação “Trocar gabarito” (super admin), nunca pelo formulário de edição. (4) Em rascunho e “em coleta” o gabarito se troca no próprio formulário, sem recálculo (não há respostas). (5) Grupo existente mas **inativo** no CSV é erro (reative-o ou renomeie), em vez de reaproveitado em silêncio. (6) Grupos são comparados sem diferenciar maiúsculas. (7) O consumo do token da prévia é um `UPDATE` condicional atômico (uma só chamada vence, mesmo com duas simultâneas); se a criação falhar, o “usada” também é desfeito. (8) O banco é a segunda camada de proteção: `RESTRICT` impede apagar pergunta com resposta ou questionário com coleta, mesmo que uma regra do serviço falhe. (9) `aplica_erro` passou a devolver o status HTTP: erro de campo = 422, erro geral = o status do erro (409, 403…).
- **Teste de mutação:** quebrei de propósito a trava de estrutura, o recálculo das respostas, o recálculo dos totais das partidas, a permissão de super admin, o uso único do token, a expiração, o rollback e o dono da prévia: todos detectados. Duas mutações sobreviveram por serem defesa em dobro (a regra do serviço e o `RESTRICT`/checagem do repositório); ganharam testes próprios em cada camada.
- **Pendências desta fase:** o formulário de pergunta mostra um erro de validação por vez; a confirmação de excluir/duplicar usa `confirm()` do navegador (trocar por modal do DS); o `scripts/convert_csv.py` e seu teste foram **substituídos pela tela de importação** e podem ser removidos (mantidos por enquanto como referência do formato).

### Fase 4 — Coletas (**concluída**)
- CRUD de coletas, com geração automática do código (alfabeto sem 0/O/1/I/L, tentativas até não colidir).
- A coleta **vincula um questionário** (lista dos questionários existentes). O vínculo não muda depois da primeira partida. Ao vincular a um rascunho, o questionário passa a "em coleta" e o formulário mostra o aviso de que a estrutura trava na primeira resposta.
- Formulário com datas (sem hora). A coleta vale de 00:00 do `data_inicio` até 23:59:59 do `data_fim`, no fuso do ENV.
- **Ano:** lista com 3 opções: ano atual − 1, ano atual e ano atual + 1 (calculado no servidor, no fuso do ENV).
- **Aviso de duplicidade:** se já existe coleta com o mesmo questionário, campus, curso, ano e período, o formulário avisa e pede confirmação; não bloqueia.
- Listas de seleção de campus e curso carregadas do banco; apenas registros ativos.
- Botão para copiar o código, e ativar/desativar. Edição não altera o código.
- **Pronto quando:** o professor cria uma coleta vinculada a um questionário, vê o código na listagem e recebe os avisos de duplicidade e de trava.
- **Resultado:** 430 testes no SQLite e 435 no PostgreSQL 17 (1 é específico do SQLite). Entregues: `ColetaService` (código, situação, ano, duplicidade, travas), lista com filtros (questionário e situação), formulário com os avisos, detalhe com o código em destaque e botão de copiar, ativar/desativar, `painel.js` (cópia com plano B). Verificado no navegador com um usuário comum: criar coleta, avisos, duplicidade (código existente listado e “Criar mesmo assim”), lista e cópia do código.
- **Decisão do usuário:** depois da primeira partida **trava a identidade da turma** (questionário, campus, curso, ano e período); prazo e ativar/desativar seguem editáveis. Antes da primeira partida tudo é editável (dá para corrigir um campus errado), exceto o código.
- **Decisões de implementação:** (1) O alfabeto do código tem 23 letras (sem I, L e O): 6,4 milhões de combinações. (2) A geração confere colisão antes e tem o `UNIQUE` do banco como segunda camada, com nova tentativa se duas criações simultâneas sortearem o mesmo código. (3) “Hoje” é o dia **no fuso configurado**, e não em UTC (às 23h30 de Belém já é o dia seguinte em UTC); o fim do prazo é inclusivo. (4) `situacao()` é uma função pura em `services/coletas.py`, para a API do jogo (Fase 5) usar a mesma regra. (5) Só entram na escolha campus e curso ativos e questionários com pelo menos uma pergunta; o valor atual de uma coleta existente continua aparecendo mesmo se depois foi inativado (e a coleta segue editável). (6) O ano de uma coleta existente fora da janela atual só é aceito se não mudar. (7) A duplicidade usa uma exceção própria (`Duplicidade`), tratada na tela como aviso com botão de confirmação, e não como erro. (8) Coletas não têm exclusão (decisão de retenção): só desativar. (9) O botão de copiar usa a API de área de transferência e, se ela for recusada, o `execCommand`; o código também é selecionável com um clique.
- **Teste de mutação:** quebrei o fuso, o fim inclusivo, a trava da identidade, o aviso de duplicidade, a validação do ano, a edição do código, o questionário sem perguntas e os campus/curso inativos: todos detectados. A checagem prévia de colisão de código sobreviveu por ser redundante com o `UNIQUE` do banco (o teste da corrida cobre a camada de baixo).
- **Pendências desta fase:** o botão “Copiar” só pôde ser verificado no navegador do app, que recusou a API de área de transferência (o plano B funcionou); vale conferir num navegador comum em HTTPS na Fase 7.

### Fase 5 — API e integração do jogo (**concluída**)
- Endpoints da seção 5 (`/api/coleta/iniciar` e `/api/partidas`). Rate limit próprio (`services/ratelimit`): conta tentativas **falhas** de validação por IP na tabela `tentativa_falha` (limite e janela por ENV, ex.: 10 falhas/min); código válido não conta; limpeza das linhas antigas.
- Jogo: calcula o token da alternativa escolhida e compara com `token_correta` para o feedback imediato (esquema da seção 5).
- Ajustes no jogo: tela inicial com campo de código; ao validar, o jogo recebe orientações e perguntas do questionário da coleta (`/api/coleta/iniciar`) e deixa de ler `questions_data.js` e `orientacoes.txt`; a tela de orientações usa o texto do banco (com o aviso de privacidade); UUID da partida; medição do tempo por resposta; envio no fim, antes do relatório (sem XP); e tratamento de falha de rede e de `coleta_encerrada`.
- Mover os arquivos do jogo para `app/static/game/` e servi-los pela rota `/`.
- **Pronto quando:** uma partida completa de ponta a ponta grava os dados corretos, vinculados ao código.
- **Resultado:** `POST /api/coleta/iniciar` e `POST /api/partidas` (idempotente por UUID), jogo servido em `/` com tela de código, perguntas e orientações do servidor, gabarito por token, tempo por pergunta e envio antes do pódio (3 tentativas, botão de reenviar, aviso de coleta encerrada). 515 testes no SQLite (inclui 20 de Node) / 435 passam no Postgres (1 ignorado); `teste.html` com 38 verificações. Partida real no navegador do app: UUID, letras, ordem e tempos bateram com o banco.
- **Decisões de implementação:** (1) O limitador é uma janela deslizante (`services/ratelimit`) reutilizada pelo login; pedidos durante o bloqueio não contam. (2) O jogo converte a resposta para o formato interno em memória (`montaQuiz`), então o resto do jogo segue usando `alt.correct`. (3) SHA-256 em JS puro como reserva quando não há `crypto.subtle` (HTTP fora de localhost). (4) Um único input oculto serve ao código e ao nome. (5) Um UUID já usado em outra coleta dá 409 `uuid_em_uso`; corrida resolvida por `IntegrityError`. (6) Mutação (11 casos em `jogo.py` e `ratelimit.py`): todas detectadas, exceto uma defesa em dobro.
- **Pendências:** (o antigo conversor `scripts/convert_csv.py`, seu teste e `data/questions_data.js` foram removidos depois da fase); conferir o envio em HTTPS real e num celular na Fase 7.

### Fase 6 — Dashboard
Especificação completa (métricas, layout, filtros, visual e acessibilidade) na **seção 11**. Etapas:
- **6a — Protótipo visual com dados fictícios** (HTML estático, sem backend) para aprovação do layout, das cores e da leitura dos gráficos, antes de ligar ao banco. **Feito e atualizado com o seletor de questionário:** o protótipo `prototipo_dashboard/` (removido do repositório depois que a 6c o substituiu). Tem 4 questionários fictícios, um por estado (travado, travado derivado, em coleta, rascunho).
- **6b (**feito**) — Serviço de agregação e endpoints JSON** protegidos, com filtros combináveis e testes sobre dataset fixo.
  - **Resultado:** `repositories/dashboard.py` (agregações no SQL a partir de `resposta`, mediana do tempo em Python), `services/dashboard.py` (filtros, métricas, CSV) e `blueprints/admin/dashboard.py` com os endpoints `resumo`, `questoes`, `grupos`, `comparativo`, `heatmap`, `questao/<n>`, `evolucao`, `tabela`, `export.csv`, mais `questionarios` (cartões) e `opcoes` (valores da barra de filtros). 565 testes no SQLite (49 deles do dashboard, também verificados no PostgreSQL); 14 mutações, todas detectadas depois de reforçar os limites de data.
  - **Decisões:** (1) `questionario` é obrigatório em toda chamada (422 sem ele, 404 se não existir). (2) Filtro cruzado no servidor: cada endpoint ignora o filtro da própria dimensão (`questoes` ignora `questao`, `grupos` ignora `grupo`, `comparativo` a `dim`, `heatmap` `grupo` e `dim`); KPIs, evolução e tabela aplicam tudo, então os totais sempre conferem. (3) `resumo` devolve também o `geral` do questionário sem filtros, para o KPI mostrar a diferença. (4) Datas são dias no fuso `TIMEZONE`, fim inclusivo; `dias=N` conta o dia de hoje. (5) Valores de filtro aceitos repetidos ou separados por vírgula, até 200 por filtro; valor inválido é 422, nunca ignorado. (6) Sem login: 401 em JSON (sem redirecionar); `Cache-Control: no-store`. (7) CSV com BOM, `;` e vírgula decimal, e rótulos que começam com `= + - @` ganham um apóstrofo (injeção de fórmula no Excel). (8) Evolução semanal começa na segunda-feira, com lacunas preenchidas por zero.
  - **Pendência:** o desempenho foi pensado para milhares de partidas (agregação no SQL); medir com volume maior na Fase 7.
- **6c (**feito**) — Páginas e gráficos ECharts** ligados aos endpoints, tabelas com totais, exportação CSV e acessibilidade (tema claro). O **seletor de questionário** é obrigatório, sem padrão e vem antes de todo o resto (ver 11.4); o protótipo 6a já reflete isso.
  - **Resultado:** página `/admin/dashboard` (`templates/admin/dashboard.html`, `static/js/dashboard.js`, `static/css/dashboard.css`, ECharts 6.1.0 local em `static/vendor/echarts`), portada do protótipo 6a com a camada de dados trocada pelos endpoints da 6b. Verificada no navegador do app com dados de exemplo (102 partidas, 816 respostas): KPIs, ranking, grupos, comparativo, mapa de calor, detalhe da questão, evolução, tabela com totais e abas, busca, ordenação, exportação CSV pelo servidor, PNG de cada gráfico, estados vazios, filtro cruzado por clique, URL compartilhável e celular sem rolagem horizontal. Paleta azul/laranja revalidada (todas as verificações passam). 575 testes no SQLite (10 da página: acesso, arquivos servidos, JS sem `innerHTML`, tooltips com `esc()`, sintaxe, rotas chamadas existem).
  - **Decisões:** (1) Seletor de questionário obrigatório e sem padrão; trocar de questionário limpa os filtros. (2) O ranking busca todas as questões (`limite=500`) e o navegador só ordena e corta o top 10, então "mais acertos" não faz nova consulta; a questão do detalhe é a clicada ou a de maior erro do recorte. (3) Respostas antigas de uma consulta anterior são descartadas (contador de requisições) para uma resposta lenta nunca sobrescrever uma mais nova. (4) A exportação CSV é a do servidor (`export.csv`), respeitando os filtros; busca e ordenação da tabela na tela não entram no arquivo. (5) Opção "padrões nas barras" liga os `decal` do ECharts (daltonismo e impressão); a descrição automática em inglês do ECharts é desligada para não trocar o `aria-label` em português. (6) Datas: 7, 30 e 90 dias ou intervalo personalizado (`de`/`ate`).
  - **Pendências:** (a) os filtros de categoria são de seleção **única** (como no protótipo aprovado); a seleção múltipla da seção 11.4 só existe na API (valores separados por vírgula). (b) Os gráficos não têm navegação por teclado ponto a ponto: a alternativa acessível é o botão **Tabela** de cada cartão (mesmos dados). (c) Falta o teste da seção 11.8 (item 4) com um usuário real e dados da turma-piloto; a captura de tela em celular foi feita num painel pequeno, vale revisar num aparelho.
- **Pronto quando:** os números batem com uma contagem manual sobre dados de teste, a paleta passa no validador e o dashboard responde às perguntas-guia da seção 11.1.

### Fase 7 — Endurecimento e entrega (**concluída no código; falta a homologação**)
- Testes de integração, revisão de segurança (CSRF, cabeçalhos, rate limit, mensagens de erro), logging.
- **Deploy no servidor da instituição, sem Docker:** gunicorn (várias workers) como serviço **systemd**, **Nginx** como proxy reverso com **HTTPS** (certificado da instituição; repassar o IP real do cliente por `X-Forwarded-For` confiável, para o rate limit, R6), **Postgres** instalado no servidor. Entregar no repositório um `deploy/` com modelos revisáveis: unit file do systemd, site do Nginx, arquivo de ENV de exemplo e rotina de `pg_dump` **semanal** (systemd timer, compactado, retenção de **8 semanas**, cópia fora do servidor definida pela TI). O README inclui o teste de restauração e o comando de backup **manual**, para rodar antes de trocar um gabarito e ao fim de cada coleta.
- README de operação (para o setor de TI): ENV, `flask db upgrade`, **setup do super admin logo após o deploy**, `flask redefinir-superadmin`, importação de questionários e restauração do backup do banco.
- **Pronto quando:** deploy em ambiente de homologação com uma turma-piloto.
- **Resultado (feito aqui):**
  - **Revisão de segurança** (`tests/test_seguranca.py`, 14 testes que varrem **todas** as rotas, então uma rota nova esquecida falha): toda rota de escrita fora da API pública exige token CSRF; toda rota do painel exige login (302 ou 401 em JSON); só `/`, `/saude`, `/entrar`, `/setup` e a API do jogo são públicas. Cabeçalhos novos: `Content-Security-Policy` (scripts só do próprio site; sem script inline), `Permissions-Policy`, `Cross-Origin-Opener-Policy`, `X-Frame-Options: DENY`, HSTS em produção e `Cache-Control: no-store` nas páginas e no JSON do painel. Os `onsubmit` inline dos templates viraram `data-confirmar` (tratado em `painel.js`). Conferido: erro 500 sem detalhes (só no log), senha nunca no log, login sem revelar se o usuário existe, `next` só para o próprio site.
  - **Desempenho (R7):** com 160 mil respostas no PostgreSQL 17, cada consulta do dashboard leva de 0,07 a 0,57 s (a mais lenta é a tabela por questão). Ganho extra: grupos, comparativo, mapa de calor e o "geral" do resumo deixaram de ler os tempos, que só servem à mediana.
  - **`deploy/`** validado: unidade do systemd (`systemd-analyze verify`), site do Nginx (`nginx -t`), `gunicorn.conf.py`, `techquiz.env.example` (testado contra `Settings`), backup `pg_dump` semanal com retenção de 56 dias, cópia externa opcional e teste de restauração, `smoke-test.sh`. Ensaiado de ponta a ponta numa máquina de teste: gunicorn em modo produção atrás do Nginx com HTTPS, contra o PostgreSQL: login com cookie `Secure`/`HttpOnly`, dashboard, 429 do rate limit **mesmo com `X-Forwarded-For` forjado** (o Nginx sobrescreve o cabeçalho), backup de 160 mil respostas restaurado com as contagens idênticas, arquivo corrompido recusado, retenção removendo só os antigos.
  - **`README_OPERACAO.md`** para a TI: instalação passo a passo, rotina, atualização, recuperação da raiz, backup e restauração, eliminação de dados, solução de problemas, IP real e checklist da homologação. 602 testes no SQLite.
- **Decisões:** (1) A configuração do `techquiz.env` é lida pelo systemd (`EnvironmentFile`) e, para os comandos `flask` manuais, por um link simbólico `.env` (o `python-dotenv` entende valores com espaço). (2) Os scripts de backup **não** fazem `source` do arquivo de ambiente (um teste achou o defeito: `INSTITUICAO_NOME` tem espaços e o texto seria executado como comando): leem só as 4 chaves de que precisam. (3) Nginx e gunicorn escutam em `127.0.0.1`; os modelos assumem Debian/Ubuntu e `/opt/techquiz`. (4) CSP mantém `style-src 'unsafe-inline'` (gov.br DS e ECharts usam estilo inline); scripts não.
- **Pendências:** (a) **homologação com a turma-piloto** no servidor da instituição (o critério "pronto quando"): só a TI e os professores podem fazer; seguir o checklist da seção 11 do README_OPERACAO. (b) Os modelos foram ensaiados em Docker, não no sistema operacional real do servidor da instituição; ajustar caminhos, nome do certificado e a versão do Nginx se diferirem. (c) Conferir o IP real do cliente atrás da infraestrutura de rede real (balanceador, NAT). (d) Rever com o comitê de ética o prazo de guarda dos dados (R18). (e) O envio do jogo em HTTPS real e num celular ainda não foi conferido.

## 7. Estratégia de testes

- **Unitários:** services e regras (geração de código, validação de coleta, cálculo de acerto, travas de usuário, parser e validador de CSV).
- **Importação:** prévia sem efeito colateral, bloqueio com erro, upload fora dos limites (tamanho, extensão, codificação), token expirado ou reutilizado, duplo clique que não cria dois questionários, rollback quando a inserção falha no meio, **nenhum dado existente alterado ou apagado**, criação de grupos faltantes, só super admin.
- **Questionário:** transições de estado (rascunho → em coleta → travado), trava de estrutura recusada com 409 no service, correção de texto permitida depois de travado, duplicação gera rascunho independente, exclusão só de rascunho.
- **Troca de gabarito:** recálculo de `acertou` e `total_acertos`, transação (rollback em falha), só super admin, auditoria registrada, dashboard reflete o novo critério.
- **Coleta:** ano limitado às 3 opções, aviso de duplicidade sem bloqueio, questionário imutável após a 1ª partida, partida com pergunta de outro questionário rejeitada.
- **Permissões:** matriz completa da seção 13 por perfil (comum, promovido, raiz), com 403 em rota restrita e botões ocultos. Casos: raiz intocável por promovidos, promovido não promove nem revoga, ninguém exclui a si mesmo, revogado perde poderes e sessões, importação e troca de gabarito bloqueadas para comuns, CSV do recorte liberado.
- **Rate limit:** falhas contam e válidos não; limite por IP; compartilhamento do contador entre processos (teste com dois clientes sobre o mesmo banco).
- **Gabarito:** o JSON de `/api/coleta/iniciar` não contém campo `correta`; o token calculado no cliente confere com `token_correta`.
- **Integração:** blueprints com `test_client` e SQLite em memória. Uma amostra roda também contra Postgres (CI ou Docker).
- **API:** casos de código inexistente, inativo, expirado, UUID repetido e payload inválido.
- **Dashboard:** dataset fixo com resultados esperados conhecidos.
- **Jogo:** roteiro manual de fluxo completo, mais a verificação do envio no navegador.

## 8. Riscos e pontos de atenção

| # | Risco | Mitigação |
|---|---|---|
| R1 | Setup público: o primeiro a acessar em produção vira **super admin raiz**, único dono de usuários e da importação de questionários, e ninguém o remove pela interface (risco aceito, sem token) | Procedimento obrigatório no README: fazer o setup logo após o deploy e antes de divulgar a URL; a rota some depois do primeiro cadastro. Se alguém assumir antes: apagar o banco e refazer, ou usar `flask redefinir-superadmin` para retomar a conta raiz. |
| R20 | O bloqueio de login permite que alguém trave a conta de outra pessoa errando a senha de propósito (negação de serviço, sem acesso aos dados) | Aceito: o bloqueio dura 10 min e só vale para aquele login; a raiz ou um super admin redefine a senha para destravar na hora (e o `flask redefinir-superadmin` destrava a raiz). Rever se virar problema real. |
| R13 | Perda do acesso do super admin raiz (senha esquecida) | `flask redefinir-superadmin` no servidor. Documentar no README. Super admins promovidos mantêm a gestão de usuários comuns e a importação enquanto isso, mas não alteram a raiz. |
| R14 | Identidade visual: o gov.br DS pode passar a impressão de um site oficial do governo | Usar os componentes e tokens do DS, mas identificar claramente a instituição e o projeto (nome, logo da universidade). Não usar brasão, assinatura "gov.br" nem o cabeçalho institucional do governo federal. |
| R2 | Dados falsos enviados direto à API | Rate limit, validação de código/prazo, recálculo do acerto no servidor, UUID único. Risco residual aceito (anônimo). |
| R3 | `POST /api/coleta/iniciar` entrega o questionário e precisa permitir ao jogo corrigir no cliente (feedback imediato) | **Decidido:** tokens por alternativa (hash com sal) e comparação no JS, sem campo `correta`. Só evita leitura casual e **não é segurança**: o sal vai ao cliente e há apenas 5 letras, então quem ler o JS descobre. Aceito porque o jogo é educativo e anônimo, e o servidor recalcula o acerto na gravação, então a qualidade dos dados não depende do cliente. |
| R9 | `crypto.subtle` indisponível em HTTP (fora de localhost): o feedback do jogo quebraria | Servir produção por HTTPS (também exigido pelo cookie seguro). **Resolvido de outra forma:** o jogo tem um SHA-256 de reserva em JavaScript puro quando não há `crypto.subtle`, então o feedback não quebra; o painel continua exigindo HTTPS (cookie `Secure`). |
| R10 | Sem tratamento de anonimato em amostras pequenas (decisão do usuário): o professor pode inferir respostas de uma turma minúscula | Risco aceito. Mitigação leve: o `n` (partidas e respostas) aparece sempre no dashboard, o que também protege contra conclusões estatísticas sobre bases pequenas. Rever se os dados passarem a ser compartilhados fora do grupo de professores. |
| R4 | Fuso horário nos prazos da coleta | **Decidido:** a coleta guarda só datas; a comparação usa o fuso do ENV (padrão America/Belem) com `data_fim` inclusivo (até 23:59:59). |
| R5 | Diferenças SQLite × Postgres | Evitar SQL específico de dialeto; testar migrações nos dois; ter cuidado com UUID e booleanos. |
| R6 | Alunos em rede de laboratório atrás do mesmo IP (NAT) esgotando o rate limit | **Decidido:** só tentativas falhas contam, por IP; códigos válidos não consomem o limite. Contador na tabela `tentativa_falha`, compartilhado entre workers. Valores por ENV. Atrás de proxy reverso, configurar corretamente o IP real do cliente (`X-Forwarded-For` confiável), senão todos parecem um só IP. |
| R7 | Dashboard lento com muitos dados | Índices, agregação no SQL e, se preciso, cache curto. Hoje o volume esperado é pequeno. |
| R8 | *(Eliminado.)* A importação não apaga mais nada: cria um novo questionário. Saíram o backup obrigatório, as confirmações de perda e os riscos de importar durante a coleta. | — |
| R12 | Duplo clique ou prévia reutilizada na importação criaria dois questionários | **Decidido:** token de uso único com validade; a segunda tentativa é recusada. |
| R15 | Janela entre criar a coleta e receber a primeira resposta: o código já foi distribuído e a estrutura ainda é editável (decisão: trava só na primeira resposta) | O painel mostra aviso fixo no questionário "em coleta" e na tela da coleta; mudanças de estrutura nessa janela só devem ocorrer antes de divulgar o código. Risco aceito. |
| R16 | Trocar o gabarito em questionário travado reescreve o histórico (`acertou` e `total_acertos`) | **Decidido:** permitido, só para super admin, com confirmação mostrando as contagens, transação única e registro de auditoria. Análises já exportadas antes da troca ficam desatualizadas; documentar no README. |
| R18 | Sem retenção automática nem exclusão pela interface: dados de pesquisa ficam indefinidamente | Aceito: os dados são anônimos e agregados (sem nome, e-mail, matrícula, IP ou avatar). A instituição deve confirmar com o comitê de ética o prazo de guarda; o README documenta como excluir coletas diretamente no banco, se exigido. O aviso padrão (seção 14) informa o uso em pesquisa. |
| R19 | Backup semanal: um incidente no servidor pode perder até uma semana de respostas (decisão do usuário) | Aceito. Mitigação: comando de backup manual documentado, a rodar antes de trocar gabarito e no fim de cada coleta; cópia fora do servidor; teste de restauração na homologação. Rever a frequência se as coletas passarem a ser grandes. |
| R17 | Deploy manual sem Docker depende do setor de TI da instituição (HTTPS, proxy, backup do banco) | Entregar modelos revisáveis em `deploy/` e README de operação passo a passo; verificar na homologação o HTTPS (R9), o IP real do cliente (R6) e a restauração de um backup. |

## 9. Itens resolvidos e pendências

Resolvidos nesta revisão:
- Ordem das perguntas: o protótipo mostra todas, em ordem fixa por número, e as alternativas por letra. O plano mantém isso (sem sorteio nem limite).
- Política de senha: mínimo de 8 caracteres.
- Reativação de perguntas inativas: o conceito deixou de existir. Perguntas não têm mais soft delete; só se removem em rascunho, e a importação cria um questionário novo.
- Conversor: o script `scripts/convert_csv.py` e seu teste deixam de ser necessários após a Fase 3 (a importação passa a ser pela tela). (Removidos depois da Fase 5; o formato dos CSVs segue documentado no README.)

Resolvidos na revisão de pendências:
- ~~Backup antes de zerar~~ e ~~importação com coleta em andamento~~: superados, porque a importação não apaga mais nada.
- Rate limit com vários workers: tabela no banco (e o token de prévia da importação também fica no banco, pelo mesmo motivo).
- Importações concorrentes: prévia com validade e revalidação.
- Anonimato em amostras pequenas: sem tratamento (R10).
- Upload de CSV: 2 MB, UTF-8 com/sem BOM, `;` ou `,`.
- Bibliotecas: ECharts + Flask-WTF. Sem Flask-Limiter.
- Ofuscação do gabarito: hash com sal, comparado no cliente (seção 5).

Resolvidos na revisão de perfis e visual:
- Perfis: raiz, super admin promovido e comum (seção 13). Substitui o "sem papéis".
- Usuário comum: operação completa, exceto gerir usuários, importar CSV e trocar gabarito de questionário travado.
- Exportações: a importação é restrita a super admin; CSV do recorte e PNG liberados a todos os logados.
- Recuperação da senha da raiz: `flask redefinir-superadmin` no servidor.
- Hierarquia: só a raiz promove e revoga; promovido gerencia só usuários comuns.
- Setup público: mantido sem proteção, mitigado por procedimento (R1).
- Visual do painel: gov.br DS local, com gráficos baseados nos tokens do DS (seção 12).
- A trava "não excluir o último usuário" foi substituída pela proteção da raiz.

Verificado no protótipo (6a): o gov.br DS 3.7.0 (MIT) não tem tema escuro global, então o painel é só claro; a fonte Rawline e os ícones não vêm no pacote.

Resolvidos na revisão das lacunas finais:
- **Entidade questionário** (ideia do usuário): perguntas e orientações pertencem a um questionário; a coleta vincula um questionário; o dashboard exige a escolha do questionário antes de tudo, sem padrão.
- Importação de CSV passou a **criar um novo questionário** e não apaga nada (substitui o "zerar tudo" e elimina R8, R11 e a obrigação de backup).
- Trava de estrutura na **primeira resposta**; depois disso só texto e gabarito (com recálculo, só super admin). Duplicar questionário cria um rascunho editável.
- Orientações e aviso de privacidade: texto por questionário, editado no admin.
- Coleta: duplicidade permitida com aviso; ano limitado a atual−1, atual e atual+1.
- Produção: servidor da instituição, sem Docker (gunicorn + systemd + Nginx + Postgres).
- XP: não é gravado.

Resolvidos na revisão de riscos e pendências:
- Fonte: Raleway local (a alternativa do próprio DS); Rawline só se a instituição fornecer os arquivos.
- Identidade: nome, subtítulo e logos configuráveis por ENV; padrão do projeto = UFRA e PROFIAP.
- Retenção: sem expiração automática; aviso padrão redigido (seção 14), a validar com a instituição e o comitê de ética (R18).
- Backup: `pg_dump` semanal, 8 semanas (R19).
- Valores padrão aprovados: rate limit, sessão, bloqueio de login, prévia, upload, fuso e idioma.

Nenhuma pendência bloqueia a Fase 0. Ficam para a implementação apenas detalhes de redação (textos de mensagens) e nomes exatos de endpoints. Nenhuma pendência bloqueia a Fase 0. Detalhes menores (nome exato dos endpoints, textos de mensagens, valores padrão do rate limit) serão definidos na implementação.

## 10. Ordem de execução sugerida

Fase 0 → 1 → 2 → 3 → 4 → 5 → 6 → 7. As fases 2, 3 e 4 podem ser entregues em sequência curta. A Fase 5 só começa com 1, 3 e 4 prontas, e a Fase 6 só com dados reais ou de teste da Fase 5. O protótipo visual do dashboard (6a) não depende do backend e pode ser feito em paralelo, a qualquer momento, para validar o design cedo.

### Revisão final (2026-11-06)

Conferido com o projeto pronto: 602 testes no SQLite e 607 no PostgreSQL (1 ignorado), 20 testes de Node, `flask db check` sem diferenças entre modelos e migrações, nenhum `TODO`/`print` esquecido, imports sem uso removidos. Corrigidos nesta revisão: seções 3, 4, 5 e R9 deste plano (estrutura de pastas, tokens do gabarito, SHA-256 de reserva, código 422, tentativas de envio); trechos de `ESCOPO.md`, `README.md`, `teste.html` e de um comentário do jogo que ainda falavam em duplo clique, `orientacoes.txt` e conversor; e o passo de cópia do `README_OPERACAO.md`, que levaria o `.env` de desenvolvimento para o servidor.

O protótipo visual `prototipo_dashboard/` e o `data/orientacoes.txt` foram removidos depois da revisão; o projeto passou a ter repositório git. **Não verificado e que vale registrar:** compatibilidade com Python 3.12 e 3.13 (só 3.14 foi usada); varredura de vulnerabilidades das dependências (`pip-audit`); teste de acessibilidade com leitor de tela e auditor automático; jogo em celular real; o ensaio de deploy foi em Docker, não no sistema do servidor da instituição.

## 11. Especificação do dashboard

O dashboard é a entrega de maior valor do projeto. Esta seção segue a diretriz de visualização de dados (forma antes da cor, paleta validada por script, marcas finas, tooltip por padrão, acessibilidade).

### 11.1 Perguntas-guia

O dashboard precisa responder, em poucos cliques:

1. Quais questões têm maior e menor % de erro, e qual o `n` por trás?
2. Qual grupo (tema) concentra mais erros?
3. Como se comparam campus, cursos, anos e períodos?
4. Numa questão com erro alto, **qual alternativa errada** os alunos escolheram (a deficiência)?
5. Qual o total de respondentes, acertos e erros, em qualquer recorte filtrado?
6. Como a coleta evolui no tempo (quando os alunos jogaram)?

Critério de usabilidade: "qual a questão com maior erro no curso X do campus Y?" se responde em até 3 interações.

### 11.2 Definições de métricas

- Todas as métricas valem **dentro do questionário escolhido**.
- **Respondente** = uma partida finalizada. Como o jogo é anônimo, uma pessoa que joga duas vezes conta duas vezes; isso é dito no rodapé do dashboard.
- **Resposta** = uma linha de `resposta`. **Erro/acerto** = campo `acertou`, calculado pelo servidor.
- **% de erro** = erros ÷ respostas do recorte, **ponderado** (nunca média de médias). **% de acerto** = 100% − % de erro.
- **Tempo** = mediana de `tempo_ms` (resistente a quem deixa a tela aberta); a média pode ser oferecida como opção.
- Agregação por snapshot (`pergunta_numero`, `grupo_nome`), nunca pelo texto atual da pergunta.
- O `n` (respondentes e respostas) aparece sempre: nos KPIs, no tooltip e em cada linha da tabela.

### 11.3 Layout (da esquerda para a direita, de cima para baixo)

1. **Seletor de questionário** (obrigatório, sem padrão) e, abaixo dele, a **barra de filtros** em uma única linha (ver 11.4). Sem questionário escolhido, a página mostra apenas a escolha, em cartões (nome, estado, nº de perguntas, coletas e partidas, e "derivado de"), e o painel fica oculto. Questionário sem respostas (rascunho ou em coleta) abre o painel com o estado vazio "Este questionário ainda não tem respostas" e a dica do estado.
2. **Linha de KPIs** (stat tiles): Respondentes · Respostas · Acertos · Erros · **% de acerto (figura de destaque)** · Tempo mediano. Cada tile mostra o valor e, quando houver comparação, a diferença para o geral sem filtro.
3. **Questões com maior % de erro:** barras horizontais, top 10 (alternável para menor erro / maior acerto). Cada barra mostra `n` e % em rótulo direto. Clicar numa barra seleciona a questão (filtro cruzado).
4. **% de erro por grupo:** barras horizontais ordenadas, com `n` por grupo.
5. **Comparativo:** seletor "Comparar por: campus | curso | ano | período". Barras horizontais de % de erro por categoria, com linha de referência da média do recorte. Ao lado, **mapa de calor grupo × dimensão escolhida** (% de erro, escala sequencial de uma só cor, `n` no tooltip).
6. **Detalhe da questão** (aparece ao selecionar uma questão): enunciado, grupo/tema, % de erro, tempo mediano e **distribuição das alternativas escolhidas** em barras horizontais, com a correta identificada por rótulo e ícone (não só por cor). É o principal gráfico para ver deficiências.
7. **Evolução da coleta:** partidas por dia (linha/área de série única) com tooltip e crosshair.
8. **Tabela de dados (obrigatória)** em abas:
   - **Por questão:** nº, título, grupo, respostas, acertos, erros, % acerto, % erro, tempo mediano; ordenável e com busca; **linha de totais** no rodapé (total de respondentes, de acertos e de erros).
   - **Por grupo** e **por dimensão de comparação** (campus/curso/ano/período), com as mesmas colunas e totais.
   - Botão **Exportar CSV** do recorte filtrado, disponível a qualquer usuário logado. A tabela também é a alternativa acessível aos gráficos.

Desktop primeiro, com grade que se reorganiza em tablet e celular (filtros recolhem num painel; gráficos em coluna única; sem rolagem horizontal da página).

### 11.4 Filtros

- **Questionário primeiro:** o seletor de questionário vem antes de qualquer filtro, é **obrigatório e não tem valor padrão** (a página abre pedindo a escolha), e fica na URL. Todo o dashboard descreve **um** questionário; nada é agregado entre questionários, porque as perguntas diferem. Trocar o questionário limpa os demais filtros.
- Campos: **coleta (código)**, campus, curso, ano, período, grupo, questão e intervalo de datas (predefinidos: 7, 30, 90 dias e personalizado). As listas mostram apenas valores que existem nas coletas do questionário escolhido.
- Seleção múltipla nos campos de categoria; chips dos filtros ativos com "limpar tudo".
- **Os filtros valem para tudo abaixo deles:** KPIs, gráficos e tabelas sempre concordam entre si.
- **Filtro cruzado com destaque:** clicar numa barra ou célula aplica o filtro (aparece como chip e pode ser removido; clicar de novo desfaz). O gráfico que originou o filtro **não ignora o próprio item**: ele continua mostrando todas as categorias da sua dimensão e destaca a selecionada (as demais ficam em tom de contexto), como no Power BI. KPIs, evolução e tabelas aplicam o filtro por inteiro, então os totais sempre conferem.
- O estado dos filtros vai na URL (query string, sem dados pessoais), para compartilhar um recorte entre professores.
- Ao recarregar, os gráficos mantêm o quadro anterior com opacidade reduzida (sem esqueleto nem salto de layout).
- Estado vazio claro: "Nenhuma resposta para este filtro", com ação de limpar.

### 11.5 Formas e cores

- **Forma antes da cor.** Magnitudes e rankings usam barras horizontais; tendência no tempo usa linha/área; relação grupo × dimensão usa mapa de calor. **Sem pizza/donut, sem eixo duplo, sem 3D.** Número único vira stat tile.
- **Cor pelo trabalho que faz:**
  - **Significado fixo em todo o dashboard:** **azul = acerto**, **laranja = erro** (`#1351b4` e `#e66f0e`, tokens do gov.br DS, par validado no script). Barras de % de erro são laranja; o mapa de calor de % de erro usa rampa sequencial laranja do DS; o KPI de % de acerto é azul. Nunca vermelho/verde, e sempre com rótulo e ícone (✓/✗), nunca só cor.
  - Comparativos entre categorias (campus, cursos): cada entidade mantém a **mesma cor** em todos os gráficos e filtros (a cor segue a entidade, não a posição no ranking). No máximo 4 a 5 séries coloridas; acima disso, barras em uma cor com ênfase na selecionada, ou "Outros".
  - **Ênfase:** em rankings, destaca-se só o item selecionado ou o pior; o resto fica em tom neutro.
  - Cores de status (bom/alerta/crítico) são reservadas e não entram como cor de série.
- **Validação obrigatória:** a paleta categórica e a rampa sequencial passam pelo `validate_palette.js` (modo claro e escuro, na superfície real do dashboard) antes de fechar a Fase 6a. Texto não usa a cor da série (usa os tokens de texto).
- **Marcas finas:** pontas de barra arredondadas em 4 px ancoradas na linha-base; 2 px de vão entre preenchimentos; linhas de 2 px; grade e eixos discretos; rótulo direto seletivo (nunca um número em cada ponto); legenda sempre presente com 2 ou mais séries.
- **Hierarquia tipográfica:** figura de destaque (≥ 48 px) para o % de acerto; títulos de gráfico dizem a conclusão ("Q7 tem o maior erro: 71%"), com subtítulo do recorte e do `n`.
- **Tema:** os tokens de superfície, texto e as cores vêm do gov.br DS (seção 12). **Verificado no protótipo:** o DS 3.7.0 não tem tema escuro global (só a classe `.dark-mode` por componente), então o painel e o dashboard ficam **só no tema claro**. O requisito de modo escuro saiu do escopo. Permanecem o contraste, o foco visível, `forced-colors` e impressão.
- **Evolução:** agregação **por semana** (padrão, a partir da segunda-feira) com opção por dia; a linha diária fica ruidosa por causa dos fins de semana e das lacunas entre coletas.
- **Eixo das barras:** vai até o maior valor + folga, nunca fixo em 100%.
- **Celular:** títulos dos cartões e ações em linhas separadas, rótulos de barra reduzidos ao %, lista textual das alternativas no detalhe da questão, `n` e valores completos no tooltip e na tabela.

### 11.6 Interação e acessibilidade

- Tooltip por padrão em todos os gráficos: valor em destaque, rótulo secundário, `n` sempre; mesma informação no foco do teclado.
- Alvos de clique maiores que a marca; navegação por teclado nos gráficos e nas tabelas; `aria-label` descritivo; contraste mínimo 3:1 nas marcas e 4,5:1 no texto.
- Padrões/texturas (`decal` do ECharts) disponíveis para daltonismo total, impressão e modo de alto contraste.
- Rótulos vindos do banco (nomes de campus, curso, grupo, enunciado) entram no DOM com `textContent`, nunca por `innerHTML`.
- Exportar imagem do gráfico (PNG) além do CSV.

### 11.7 Endpoints (protegidos por login)

`/admin/api/dashboard/` com `resumo`, `questoes`, `grupos`, `comparativo?dim=`, `heatmap?dim=`, `questao/<numero>`, `evolucao`, `tabela?aba=` e `export.csv`. Todos aceitam os mesmos parâmetros de filtro e passam por um único construtor de filtros no service (DRY), com agregações no SQL.

### 11.8 Verificação antes de aceitar

1. Números conferidos contra contagem manual em dataset fixo.
2. Paleta validada nos dois modos.
3. Renderização conferida visualmente (captura de tela) em claro, escuro, tablet e celular: colisão de rótulos, overflow, geometria.
4. Teste das perguntas-guia (11.1) com um usuário real, usando dados da turma-piloto.

## 12. Interface do painel (design system do governo federal)

- **Escopo:** todo o painel admin (login, setup, menus, formulários, tabelas, modais, avisos e o dashboard). O jogo mantém a identidade visual própria do protótipo.
- **Entrega:** pacote `@govbr-ds/core` com **versão fixada**, copiado para `app/static/admin/govbr/` (CSS, JS, fontes e ícones). Sem CDN, para funcionar em laboratório/intranet e sem depender de terceiros. Confirmar a licença e a versão atual no início da Fase 0.
- **Componentes previstos:** cabeçalho, menu lateral, breadcrumb, botões, campos e seleções, tabelas, abas, paginação, modais, mensagens/avisos, indicador de carregamento e o fluxo em etapas para a importação (upload → prévia → confirmação).
- **Templates:** `base.html` com o layout do DS e blocos de conteúdo; macros Jinja para campos de formulário, tabelas e avisos, evitando repetição (DRY).
- **Gráficos:** superfície branca, textos e as cores azul (`#1351b4`) e laranja (`#e66f0e`) vêm dos tokens do DS. O par passou nas 5 verificações do `validate_palette.js` sobre a superfície `#ffffff` (CVD ΔE 29,9; visão normal 39,2; contraste ≥ 3:1). As rampas sequenciais (azul e laranja do DS) são monótonas e de uma só matiz; o degrau mais claro fica abaixo de 2:1 por projeto (significa "perto de zero"), e por isso as células do mapa de calor trazem o valor impresso e a tabela gêmea.
- **Fonte e ícones (decidido):** o pacote do DS **não inclui** a fonte Rawline nem os ícones Font Awesome (vêm de CDN no exemplo oficial). Para manter tudo local, usa-se `@fortawesome/fontawesome-free` (CC BY 4.0 / OFL / MIT) e `@fontsource/raleway` (OFL), copiados para `/static`. O **Raleway é a fonte do painel**, porque é a alternativa que o próprio DS declara (`"Rawline", "Raleway", sans-serif`). A Rawline só entra se a instituição fornecer os arquivos oficiais, bastando trocá-los em `/static`.
- **Componentes do DS efetivamente usados no protótipo:** `br-header`, `br-divider`, `br-sign-in`. Filtros, abas, chips, segmentos e a tabela de dados são estilos próprios sobre os tokens do DS. Na implementação real, usar os componentes oficiais de select, tabs e table.
- **Acessibilidade:** o DS já segue práticas de acessibilidade; manter foco visível, rótulos, ordem de tabulação e contraste, e testar por teclado.
- **Tema escuro:** não existe no DS (ver 11.5); só tema claro.
- **Identidade (decidido):** o nome da instituição, o subtítulo e os caminhos dos logos são **configuráveis por ENV** (`INSTITUICAO_NOME`, `INSTITUICAO_SUBTITULO`, `LOGO_INSTITUICAO`, `LOGO_PROGRAMA`), com padrão genérico "TechQuiz" e sem logo se não configurados. O projeto já tem as duas logos (`assets/logos/logo_ufra.png` e `logo_pos.png`, hoje em `config/config.js` do jogo como UFRA / PROFIAP), que passam a ser o valor de implantação do projeto e ficam em `app/static/`. O cabeçalho mostra as duas logos e o nome. Não usar o brasão nem a assinatura "gov.br" (R14). O painel e o jogo leem a mesma configuração, para não divergir.

## 13. Perfis e permissões

Perfis: **raiz** (o primeiro usuário, também super admin), **super admin** (promovido) e **comum**.

| Ação | Comum | Super admin promovido | Raiz |
|---|---|---|---|
| Dashboard (ver, filtrar, exportar CSV do recorte e PNG) | sim | sim | sim |
| Gerir coletas, campus, curso, grupo | sim | sim | sim |
| Criar, editar, duplicar questionários e editar suas perguntas/orientações (respeitando a trava de estrutura) | sim | sim | sim |
| Excluir questionário em rascunho | sim | sim | sim |
| **Trocar o gabarito** de questionário travado (recalcula respostas) | não | sim | sim |
| Alterar a própria senha (exige a senha atual) | sim | sim | sim |
| Gerir usuários comuns (criar, editar, redefinir senha, excluir) | não | sim | sim |
| **Importar CSV** (cria um novo questionário) | não | sim | sim |
| Promover usuário a super admin / revogar super admin promovido | não | **não** | **sim** |
| Alterar ou excluir outro super admin promovido | não | **não** | sim (revogar/excluir) |
| Alterar a senha da raiz, revogar ou excluir a raiz | não | **não** | só a própria senha; revogar/excluir **nunca** |
| Redefinir a senha da raiz | — | — | `flask redefinir-superadmin` (shell do servidor) |

Regras:
- Existe uma única raiz (o 1º usuário do setup), `raiz=true`, que a aplicação nunca altera nem exclui.
- Um super admin promovido, ao ser revogado, volta a usuário comum (mantém o login e perde os poderes).
- Ninguém exclui a si mesmo.
- A autorização é feita no servidor (decorators `superadmin_required` e `raiz_required`) e a interface apenas esconde o que o perfil não pode usar. Rota restrita responde 403.
- Mudança de perfil ou de senha por terceiros invalida as sessões do usuário afetado.
- Eventos sensíveis (promoção, revogação, exclusão, redefinição de senha, importação de questionário, troca de gabarito) vão para o log de auditoria.

## 14. Texto padrão das orientações (rascunho, a revisar pela instituição)

Ponto de partida das orientações de cada questionário novo, no formato atual (`# título`, `- item`, parágrafos, `{{totalPerguntas}}`). Junta-se às orientações de jogo que já existem em `data/orientacoes.txt`. **A redação final deve ser validada pela instituição e pelo comitê de ética**; o texto é editável por questionário.

```
# Sobre a sua participação
- Este jogo faz parte de uma pesquisa da instituição sobre os conhecimentos dos estudantes.
- A participação é voluntária e anônima: você não informa nome, e-mail nem matrícula, e nenhuma resposta é ligada a você.
- As respostas são analisadas apenas em conjunto (por turma, curso e campus) para melhorar o ensino e os materiais de apoio.
- Você pode parar a qualquer momento, fechando o jogo. Partidas que não forem concluídas não são guardadas.
- Ao continuar, você concorda em participar.
```

Observações: o texto não afirma que o jogo "não vale nota"; incluir essa frase apenas se for verdade para a turma. O aviso fica na tela de orientações, que o aluno já vê antes de escolher o personagem.

