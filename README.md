# TechQuiz Campus

Jogo educacional de perguntas e respostas em perspectiva isométrica 2.5D, para avaliação formativa. O estudante controla um avatar numa sala de centro de dados e escolhe uma **porta** para responder cada pergunta de múltipla escolha. Depois de cada resposta, o avatar reage (comemora se acertou e coça a cabeça, pensativo, se errou); o gabarito e as explicações aparecem na revisão final.

O jogo roda no navegador e faz parte do sistema de coleta de dados: o aluno entra com o **código da turma**, joga, e as respostas anônimas são gravadas no servidor para análise. O servidor (Flask) também serve o jogo na raiz do site; para instalar e operar, veja [README_ADMIN.md](README_ADMIN.md). Para o escopo técnico completo do jogo, veja [ESCOPO.md](ESCOPO.md) (a parte de dados e de perguntas ali descrita foi substituída pelo sistema web: ver [PLANO_ADMIN.md](PLANO_ADMIN.md)).

## Requisitos

- Um navegador moderno (Chrome, Edge, Firefox ou Safari).
- O sistema web em execução (ver [README_ADMIN.md](README_ADMIN.md)) e **um código de turma**, que o professor cria no painel em *Coletas*.

## Início rápido

```bash
. .venv/bin/activate && flask db upgrade && flask run
```

Abra `http://127.0.0.1:5000/`: o jogo é servido na raiz. O professor cadastra o questionário (ou importa os CSVs) e cria uma coleta no painel (`/entrar`); o código de 5 letras da coleta é o que o aluno digita.

## Como jogar

1. Na abertura, o campo do **código da turma** está sempre vazio e já com o foco (borda verde neon e cursor piscando); o **?** ao lado do rótulo mostra a dica (passe o mouse ou toque). Digite o código (5 letras; o professor informa) e pressione Enter ou clique em **Iniciar**. O código é conferido no servidor: se estiver errado, desativado ou fora do prazo, a tela explica; muitos erros seguidos bloqueiam o computador por alguns minutos.
2. Leia as orientações (incluem o aviso de privacidade) e continue.
3. Na tela **Crie seu avatar** o campo do nome já abre com o foco (borda verde neon e cursor piscando). Digite seu nome (letras e números, sem espaços, acentos ou símbolos, até 15 caracteres), escolha um avatar (clique, setas, ou **Tab** e as teclas **1 a 9**) e confirme. O botão **?** ao lado do **A+** abre a ajuda com todas as explicações. O nome e o avatar ficam só na tela: **nunca são enviados**.
4. Em cada pergunta, leia o enunciado no topo e escolha uma porta. Cada porta é uma alternativa, identificada pela letra no display acima dela e pelo texto no rodapé.
5. A resposta é gravada ao cruzar a porta, e **há uma única tentativa por pergunta**.
6. Uma tela de reação mostra o resultado: o avatar comemora (acerto) ou coça a cabeça, pensativo (erro), e você vê o XP ganho. Enter, Espaço ou clique pulam a animação.
7. Ao terminar, o jogo **envia as respostas ao servidor** (aparece "Salvando suas respostas…", com novas tentativas automáticas se a conexão falhar) e só então mostra o pódio e a revisão de cada pergunta. Se o envio falhar, o pódio avisa e oferece **Tentar enviar de novo**; se a coleta já tiver encerrado, o aviso diz que as respostas não foram salvas. **Jogar Novamente** volta à abertura, **sempre com o campo do código vazio**.

O servidor guarda, por partida, só o código da turma, um identificador aleatório da partida e, para cada pergunta, a alternativa escolhida, o acerto (recalculado pelo servidor), a ordem e o tempo até escolher. **Não** guarda nome, avatar, XP nem IP.

Pontuação padrão: **100 XP** por acerto e **10 XP** por resposta incorreta (participação). O total aparece no canto superior direito, ao lado de um ícone de moeda; é só mecânica do jogo e não é gravado.

### Controles

| Ação | Mouse / toque | Teclado |
|---|---|---|
| Andar | — | Setas |
| Escolher porta | Clicar na porta (o avatar vai até ela) | Enter ou Espaço diante da porta, ou a letra **A, B, C ou D** |
| Ver a dica (se houver) | Botão **? DICA** | Tecla **H** (Esc fecha) |
| Escolher avatar | Clicar no cartão | **Tab** leva o foco do nome aos avatares; **1 a 9** ou ← → escolhem; Tab volta ao nome |
| Pular a tela de reação | Clique | Enter, Espaço ou Esc |
| Ligar/desligar o som | Botão de alto-falante | Tecla **M** |
| Aumentar/reduzir o texto | Botão **A+** | Teclas **+** e **−** |
| Rolar textos longos | Roda do mouse ou arrastar | Setas, PageUp, PageDown |
| Percorrer os botões da tela | — | **Tab** e **Shift+Tab** (um contorno amarelo mostra o foco); Enter ou Espaço ativam |
| Repetir o último aviso (leitor de tela) | — | Tecla **R** |

A dica não desconta XP. Na tela do nome, com o campo em foco, as teclas M, + e − e os números são digitação; pressione **Tab** para ir aos avatares (onde M, + e − voltam a ser atalhos) ou use os botões do canto da tela.

## Como criar suas próprias perguntas

Pelo painel do sistema (`/admin/`):

- **Questionários**: criar, editar perguntas e alternativas (de 2 a 4, letras A a D, exatamente uma correta), editar o texto das orientações e duplicar.
- **Importar** (só super admin): envia `perguntas.csv` e `alternativas.csv` e cria um questionário novo, com prévia antes de gravar. O formato é o mesmo de sempre:

**`perguntas.csv`**

| Número da pergunta | Pergunta | Título | Grupo | Autoajuda |
|---|---|---|---|---|
| 1 | Qual ... ? | Phishing | Segurança Digital | Dica opcional |

**`alternativas.csv`**

| Número da pergunta | Letra | Texto da alternativa | Correta ou incorreta | Texto de acerto | Texto de erro |
|---|---|---|---|---|---|
| 1 | A | Clicar no link | Incorreta | | Explique por que está errada |
| 1 | B | Reportar à TI | Correta | Explique por que está certa | |

Os CSVs atuais em `data/` servem de exemplo. Salve como **CSV UTF-8**; o delimitador (`;`, vírgula ou tabulação) é detectado sozinho. **Grupo** vira o selo acima do enunciado; **Autoajuda** vazia esconde o botão de dica; **Texto de acerto/erro** aparecem na revisão final. As perguntas seguem a ordem do número e as alternativas a ordem das letras. Mantenha as alternativas curtas: no rodapé, textos acima de 3 linhas são cortados (na revisão aparecem inteiros).

A importação lista **todos** os problemas, com arquivo e linha, e não grava nada se houver erro. O jogo não lê mais arquivos de perguntas: o antigo conversor de CSV foi removido.

## Personalização

| O que mudar | Onde |
|---|---|
| Nome da instituição e do programa, pontos por acerto e erro, nome e sigla da pontuação (hoje "XP"), regra do nome, título do jogo | `app/static/game/config/config.js` |
| Texto da tela de orientações (e o aviso de privacidade) | Painel: *Questionários* → o questionário → *Orientações* (é por questionário) |
| Logos | `app/static/game/assets/logos/logo_ufra.png` e `logo_pos.png` já trazem as logos reais da UFRA e do PROFIAP. Para trocar, substitua os PNGs (de preferência com margem pequena e fundo claro): o jogo ajusta o tamanho e as desenha em caixas 3D de mesma altura. Se faltarem, aparece um brasão desenhado pelo jogo |

No texto das orientações, uma linha com `# ` é um título, `- ` é um item de lista e linha em branco separa parágrafos. Valores como `{{totalPerguntas}}`, `{{pontosCorreta}}`, `{{pontosIncorreta}}`, `{{moeda}}`, `{{sigla}}`, `{{titulo}}` e `{{instituicao}}` são preenchidos automaticamente.

## Acessibilidade

- Avisos para leitores de tela sobre a pergunta, as portas, a dica e o resultado, além de uma lista da revisão final.
- Botão de som, tecla M e botão **A+** (texto a 100%, 125% e 150%).
- Navegação completa por teclado: **Tab** e **Shift+Tab** percorrem botões e portas, com foco visível; a tecla **R** repete o último aviso falado.
- Letras A–D como alternativa às setas.
- Respeita a preferência do sistema por **movimento reduzido** (sem confete nem transições em blocos).
- Texto de interface com no mínimo 16 px e contraste acima do exigido pelo WCAG AA.

## Solução de problemas

| Sintoma | Causa e solução |
|---|---|
| Tela vermelha "ERRO DE INICIALIZAÇÃO" | Faltam arquivos do jogo (`config/config.js` ou `js/api.js`) na publicação. Confira a pasta `app/static/game` e recarregue |
| "Código não encontrado" | O código tem 5 letras (sem I, L e O); confira com o professor |
| "Esta coleta está desativada" / "prazo ... terminou" / "ainda não começou" | O professor precisa ativar a coleta ou ajustar o prazo no painel |
| "Muitas tentativas com código errado" | O computador (ou a rede da sala) errou o código muitas vezes seguidas e foi bloqueado por alguns minutos; aguarde a contagem |
| "Sem conexão com o servidor" no pódio | O jogo já tentou 3 vezes. Use **Tentar enviar de novo** quando a conexão voltar; reenviar nunca duplica a partida |
| "Esta coleta foi encerrada; suas respostas não foram salvas" | A coleta fechou antes do envio. Fale com o professor |
| "O questionário mudou durante a partida" | O professor alterou as perguntas enquanto a turma jogava; é preciso jogar de novo |
| Sem som | O navegador só libera o áudio após um clique ou tecla. Confira também o botão de som e a tecla M |
| O campo do nome rejeita caracteres | Só são aceitos letras (sem acento) e números, até 15 |
| O botão "Confirmar" não habilita | É preciso um nome válido e um avatar escolhido; o texto abaixo do botão diz o que falta |
| Logos aparecem como brasões azuis | Os PNGs estão ausentes ou o navegador bloqueou o arquivo; é o comportamento esperado de reserva |
| Jogo pequeno em celular | A tela é 16:9 e encolhe; use o modo paisagem |
| Aparece "Gire o aparelho para a horizontal" | O aviso surge em celulares/tablets em retrato; gire o aparelho |

## Testes

```bash
. .venv/bin/activate && pytest                 # tudo: servidor, API, jogo servido e a suíte de Node do api.js
node --test tests/js/api.test.js               # só o módulo de rede e gabarito do jogo (20 testes)
```

Para o jogo no navegador, abra **`/static/game/teste.html`** com o servidor rodando. Ela roda **38 verificações** de ambiente e de lógica (arquivos carregados, perguntas válidas, gabarito por token, SHA-256, logos, estados, pontuação, nome, avatares, portas, o pacote enviado ao servidor, todas as telas e uma partida completa, acessibilidade) e mostra OK ou FALHA para cada uma; o botão "Copiar relatório" copia o resultado. A página substitui a rede por funções falsas, então **não grava nada** no servidor. Ela também tem botões para **ouvir os 6 sons** do jogo.

### Roteiro de teste de 2 minutos (som e navegadores)

1. Abra `/static/game/teste.html`, no Chrome ou Edge e depois no Firefox (e no Safari, se usar). Confirme "Tudo certo".
2. Na mesma página, clique em cada botão de som e verifique se o volume, o timbre e a duração estão agradáveis.
3. Abra `/`, entre com o código de uma coleta de teste, jogue uma pergunta e confira: logos na abertura, som dos passos e da porta, reação de acerto ou erro e o XP no canto.
4. Se algo falhar, use "Copiar relatório" em `teste.html` e envie o texto.

## Estrutura do projeto

```
app/static/game/            # o jogo (servido na raiz do site pelo Flask)
  index.html                # página do jogo (usa <base href="/static/game/">)
  teste.html                # autoteste do ambiente e da lógica, mais os botões de som
  css/styles.css            # estilos e escala 16:9
  config/config.js          # parâmetros da instituição e do jogo
  assets/logos/             # logos da UFRA e do PROFIAP
  js/                       # api, audio, renderer, avatars, a11y, state, screens, main
tests/js/api.test.js        # testes em Node do js/api.js
data/                       # perguntas.csv e alternativas.csv (exemplo e modelo de formato)
README_ADMIN.md             # instalação e operação do sistema web
README.md  ESCOPO.md        # instruções de uso e especificação do jogo
```

O jogo não grava nada no navegador (sem `localStorage`, `sessionStorage` nem cookies): nome, avatar e pontuação ficam só na memória e somem ao recarregar a página ou ao escolher "Jogar Novamente". Ao final da partida, apenas as respostas anônimas (alternativa, ordem e tempo) são enviadas ao servidor, ligadas ao código da turma.
