# TechQuiz Campus — Escopo do Protótipo (versão construída)

Este documento descreve o protótipo **como foi implementado**: os 6 prompts de execução incremental, a rodada que fechou as pendências a rodada de correções de teste (texto legível, avatares, pontuação em XP, tela de reação e pódio) e a rodada das pendências finais (logos reais, cabeçalho, mão do avatar, aviso em retrato, navegação por teclado, tecla R e testes automatizados). Ele substitui os antigos `DESVIOS.md` e `PENDENCIAS.md`: as decisões estão na seção 12 e o que continua em aberto, na seção 13. Para instruções de uso, veja o [README.md](README.md).

## 1. Visão geral

Jogo sério educacional, em ambiente web nativo, para **avaliação formativa gamificada**. Substitui a estética medieval (castelos e calabouços) por um **Campus Universitário Tecnológico / Hub de Inovação Digital**, com visual cúbico/voxel inspirado em Minecraft.

O estudante controla um avatar em **perspectiva isométrica 2.5D** numa sala de centro de dados e escolhe **portas/eclusas digitais**, cada uma representando uma alternativa de múltipla escolha (2 a 4 por pergunta). **Depois de cada resposta**, uma tela de reação mostra o resultado: o avatar comemora se acertou e coça a cabeça, pensativo, se errou. O gabarito e as explicações aparecem na revisão final, no pódio.

Instituição de exemplo: UFRA — Universidade Federal Rural da Amazônia / PROFIAP (configurável).

## 2. Tecnologia

| Aspecto | Implementação |
|---|---|
| Linguagens | HTML5, CSS3 e JavaScript ES6+ Vanilla, sem bibliotecas nem frameworks |
| Renderização | Canvas 2D nativo. Projeção isométrica, piso, portas, avatares, moeda e brasões são desenhados por código |
| Áudio | Web Audio API, sem arquivos de som. Ondas senoidal, quadrada e triangular, mais ruído branco filtrado |
| Persistência | Somente em memória (FSM). Não há `localStorage`, `sessionStorage`, cookies, `fetch` nem `XMLHttpRequest` |
| Execução | Servido pelo Flask na raiz `/` (o jogo precisa do servidor: perguntas e gravação das respostas vêm da API). Ver `README_ADMIN.md` |

### 2.1. Viewport

- Área interna do canvas fixa em **1280 × 720** (16:9).
- `#game-container` usa `aspect-ratio: 16/9` e `width: min(100vw, 100vh × 16/9)`: ocupa o maior retângulo 16:9 que cabe na janela (letterbox/pillarbox), inclusive ampliando em telas grandes.
- A moldura neon é um `::after` decorativo com `pointer-events: none`; não altera a conversão dos cliques.
- Suavização de imagem ligada; só o desenho dos avatares a desliga.

### 2.2. Paleta (azul)

| Uso | Cor |
|---|---|
| Moldura, botão primário, bordas | `#1f6feb` |
| Acento neon, textos de destaque, campo de nome | `#58a6ff` |
| Superfícies (painéis, fundo do input) | `#161b22` |
| Fundos | `#0d1117` |
| Borda do campo de nome | `#30363d` |
| Pontuação (XP) e moeda | dourado `#f6cf55` |

Os verdes de significado (ícone de acerto, borda de nome válido) e o vermelho de erro foram mantidos. A tentativa com o verde `#147A02` foi descartada por má visualização.

### 2.3. Tipografia

- **Títulos** (Abertura, Orientações, Identifique-se, Perfil, Dica, Parabéns, Revisão geral, faixa da reação): texto **nativo em alta resolução**, em negrito monoespaçado, com sombra rígida em degraus (efeito 3D de bloco, estilo "Minecraft") e contorno escuro. Cada título é pré-desenhado uma vez e copiado 1:1, então fica nítido em qualquer tamanho de janela. (A versão anterior ampliava pixels e ficava granulada.)
- **Corpo e interface:** fonte sem serifa do sistema, com mínimo de 16 px.

## 3. Estrutura do projeto

```
projeto_adam/
├── app/static/game/         # o jogo, servido na raiz `/` pelo Flask (<base href="/static/game/">)
│   ├── index.html           # <main id="game-container"> com canvas#gameCanvas, input#avatarNameInput e regiões ocultas de leitor de tela
│   ├── teste.html           # autoteste do ambiente e da lógica + botões para ouvir os sons
│   ├── css/styles.css       # viewport 16:9, moldura decorativa, estilos do input, classe .sr-only
│   ├── config/config.js     # window.GAME_CONFIG
│   ├── assets/logos/        # logo_ufra.png e logo_pos.png (logos reais da UFRA e do PROFIAP)
│   └── js/                  # api, audio, renderer, avatars, a11y, state, screens, main
├── data/                    # CSVs de exemplo (perguntas e alternativas) para a importação do painel
├── tests/js/api.test.js     # testes em Node do js/api.js
└── README.md                # instruções de uso
```

Ordem dos scripts: `config`, `api`, `audio`, `renderer`, `avatars`, `a11y`, `state`, `screens`, `main`. (Perguntas e orientações não são mais arquivos: vêm do servidor, por questionário.)

## 4. Dados e conversão

> **Atualização (Fase 5):** as perguntas e as orientações agora vivem no banco e chegam por `POST /api/coleta/iniciar`, depois que o aluno digita o código da turma. O conversor `scripts/convert_csv.py` e o `questions_data.js` ficaram obsoletos; os CSVs são importados pela tela do painel (só super admin). O formato dos CSVs abaixo continua valendo. O jogo converte a resposta da API para o formato interno `QUIZ_DATA` em memória, e a alternativa correta é descoberta pelo token do gabarito (sem campo `correta` no tráfego). Detalhes em `PLANO_ADMIN.md`, seções 5 e 6.

### 4.1. Configuração (`config/config.js`)

`window.GAME_CONFIG` define instituição (nome, programa e URLs das logos), economia (100 pontos por acerto, 10 por erro, nome e sigla da pontuação, hoje **"XP"**), validação do nome (`^[a-zA-Z0-9]{1,15}$`, máximo 15) e interface (título "TechQuiz Campus", canvas 1280×720). Nenhum desses valores está fixo no código.

### 4.2. CSVs

- Codificação **UTF-8** (com ou sem BOM). O delimitador é detectado no cabeçalho: `;` (padrão do Excel em português), `,` ou tabulação.
- `perguntas.csv`: `Número da pergunta`, `Pergunta`, `Título`, `Grupo`, `Autoajuda`.
- `alternativas.csv`: `Número da pergunta`, `Letra`, `Texto da alternativa`, `Correta ou incorreta`, `Texto de acerto`, `Texto de erro`.
- A coluna "Correta ou incorreta" aceita `Correta`/`Incorreta` (e variações como certa/errada, sim/não, 1/0).

### 4.3. Conversor (removido; histórico)

> O conversor `scripts/convert_csv.py` e o `questions_data.js` foram removidos: a importação dos CSVs é feita pela tela do painel, com as mesmas validações, e o jogo recebe as perguntas pela API. O texto abaixo descreve as regras, que continuam valendo.

Une as tabelas pelo número da pergunta e gera `data/questions_data.js`, com as perguntas ordenadas por número e as alternativas por letra:

```javascript
window.QUIZ_DATA = [
  { id: 1, title: "...", question: "...", group: "...", hint: "",
    alternatives: [ { letter: "A", text: "...", correct: false, successText: "", errorText: "..." }, ... ] }
];
window.ORIENTACOES = "...";   // texto de orientações do questionário
```

**Validações** (todas listadas com `arquivo:linha`; havendo erro, nada é gerado e o código de saída é 1):
pergunta sem alternativa; menos de 2 ou mais de 4 alternativas; **sem alternativa correta**; **mais de uma correta**; letra fora de A–D ou repetida; valor inválido em "Correta ou incorreta"; alternativa que referencia pergunta inexistente; número de pergunta inválido ou duplicado; enunciado vazio; arquivo ausente, vazio ou fora de UTF-8; colunas ausentes. Avisos (não bloqueiam): pergunta sem título ou sem grupo; letras não sequenciais.

### 4.4. Orientações customizáveis (hoje por questionário, no painel; antes `data/orientacoes.txt`)

Texto simples: `# ` abre um título, `- ` um item de lista, linha em branco separa parágrafos. Variáveis substituídas na hora: `{{titulo}}`, `{{instituicao}}`, `{{totalPerguntas}}`, `{{pontosCorreta}}`, `{{pontosIncorreta}}`, `{{moeda}}`, `{{sigla}}`. Depois de editar, é preciso rodar o conversor. O arquivo de exemplo já descreve a escolha de avatar (Tab e 1–9), a pontuação em XP, as reações e a seção "Acessibilidade" com os atalhos.

### 4.5. Logos e fallback

As logos são pré-carregadas (limite de 3 s). Se alguma falhar (arquivo ausente, 404 ou bloqueio de `file:///`), o jogo desenha um **brasão procedural** em estilo neon, com a sigla e o nome em texto de 16 px (universidade usa `institution.name`; programa usa `institution.department`).

**Logos reais:** `logo_ufra.png` (335×223) e `logo_pos.png` (325×332) foram recortadas e tiveram o fundo claro normalizado para branco. Na abertura, cada logo fica em uma **caixa 3D isométrica**, como os avatares: a logo ocupa a face frontal (inclinada no plano da face, sem inverter o desenho), com topo e lateral visíveis, sombra no chão e uma leve flutuação (parada com movimento reduzido). A caixa da UFRA, à esquerda, é o **espelho horizontal** da caixa do PROFIAP, à direita: as duas ficam simétricas, com as faces voltadas para o centro da tela. As duas caixas têm a **mesma altura de face** (65% da área de 230 px); a largura acompanha a proporção de cada imagem. Para trocar, substitua os PNGs (de preferência com margem pequena e fundo claro).

## 5. Máquina de estados (`state.js`)

```
BOOT → TITLE ⇄ INSTRUCTIONS ⇄ AVATAR_SELECT → QUIZ_PLAYING → ANSWER_FEEDBACK ─┬→ QUIZ_PLAYING (próxima pergunta)
                                                                              └→ PODIUM_REVIEW → TITLE
```

Transições inválidas lançam erro. A cada pergunta, o jogo percorre `QUIZ_PLAYING → ANSWER_FEEDBACK → QUIZ_PLAYING`; depois da última, vai ao pódio.

- **BOOT** (`GameState.boot()`): valida só `GAME_CONFIG` e a presença de `TQApi`. Se falhar, o estado permanece em `BOOT` e aparece a tela vermelha de bloqueio. As perguntas são validadas depois, ao montar o questionário recebido do servidor (2 a 4 alternativas e exatamente 1 correta por pergunta); a tela de abertura pede o código da turma (5 letras).
- **Dados em memória:** `playerName`, `selectedAvatar` (0–8), `currentQuestionIndex`, `score`, `activeModalHint` e `answersHistory`; o acessor `lastAnswer` devolve a resposta mais recente (usada pela tela de reação).
- **`answersHistory`:** `questionId, questionTitle, questionText, selectedLetter, isCorrect, correctLetter, feedbackText`, mais `questionGroup, selectedText, correctText, correctFeedbackText, points`.
- **Jogar Novamente** (`restart()`): zera nome, avatar, pontuação, histórico e a dica, e volta a `TITLE`. O tamanho do texto e o estado do som, que são preferências, permanecem.

## 6. Telas e jogabilidade (`screens.js`)

Entre telas e entre perguntas há um **wipe digital** (blocos que "ligam" da esquerda para a direita, 0,38 s para cobrir e 0,38 s para revelar). Com movimento reduzido, vira um fade simples.

1. **Abertura:** logos em caixas 3D de mesma altura (ou brasões, se faltarem), título em blocos, instituição, elenco dos 9 avatares e botão "Iniciar". Qualquer clique ou tecla avança e destrava o áudio.
2. **Orientações:** texto do questionário da coleta (editado no painel), com rolagem (roda, setas, PageUp/PageDown e arrastar).
3. **Nome e avatar:** campo desenhado no canvas e alimentado por um `<input>` real fora da tela.
   - **Foco inicial:** o campo abre com foco. Só é dispensado em aparelhos cujo ponteiro principal é o toque (`(pointer: coarse)`), para não abrir o teclado virtual; o foco é reaplicado até funcionar.
   - **Avatares:** grade com os 9 avatares, cada cartão identificado **só pelo número** (1 a 9, que também é a tecla de atalho), mais pré-visualização ampliada (2x, estática, de frente) e a ficha do perfil.
   - **Tab:** alterna entre o campo do nome (as teclas digitam) e a grade (a moldura azul mostra o modo ativo; **1 a 9** e as setas escolhem; M, + e − voltam a ser atalhos). Ao voltar ao nome, o cursor vai para o fim do texto.
   - **Confirmar** só habilita com nome válido e avatar escolhido; enquanto desabilitado, um texto diz o que falta.
   - **Validação do nome:** rejeita na hora espaços, acentos, símbolos e `_`, com aviso; limite de 15 caracteres (atributo `maxlength`), também com aviso.
4. **Perguntas:**
   - **Topo:** badge com o **Grupo**, acima do título e do enunciado; no canto superior direito, o **contador de XP** (moeda dourada desenhada por código e "N XP"), com a linha "Pergunta N de T · nome" logo abaixo. O cabeçalho cresce com o tamanho do texto, mas **nunca passa de 224 px**: o enunciado encolhe (até 16 px; só depois é cortado com reticências) e um título muito longo ganha reticências, para que as letras das portas e a linha "Pergunta N de T" fiquem sempre livres.
   - **Contador de XP:** o número sobe até o total real e o chip dá um pequeno "pulso" ao ganhar pontos (sem animação com movimento reduzido).
   - **Dica:** o botão "? DICA" só aparece se houver autoajuda; abre um painel modal translúcido (tecla H ou clique) e **não custa XP**.
   - **Centro:** 2 a 4 portas equidistantes e centralizadas, cada uma com um display holográfico cúbico com a letra.
   - **Rodapé:** texto das alternativas (até 3 linhas cada, com reticências); cresce com o tamanho do texto.
   - **Controles:** setas movem o avatar; diante de uma porta, **Enter/Espaço** confirma. Um clique na porta, ou a **letra da alternativa (A–D)**, faz o avatar caminhar **em linha reta** até ela e escolhê-la (o piso é livre, sem pathfinding). O aviso "Enter / Espaço" aparece quando o avatar está na zona da porta.
   - **Entrada na porta:** a eclusa abre (vê-se uma passarela de dados até o horizonte), o avatar entra e some, a porta fecha e o wipe leva à tela de reação.
   - **Regra:** tentativa única; a resposta é gravada ao cruzar a porta.
5. **Reação à resposta** (`ANSWER_FEEDBACK`, 2,4 s; 1,8 s com movimento reduzido): palco com holofotes, o avatar ampliado e uma faixa com o resultado e os pontos. O contador de XP aparece no canto e é aqui que o número sobe.
   - **Acerto:** faixa "RESPOSTA CORRETA!" e "+100 XP"; o avatar **pula com os braços para cima**, com confete e explosão de estrelas; som de arpejo ascendente.
   - **Erro:** faixa "QUASE!", "+10 XP" e a frase "Sem problemas: a explicação completa aparece na revisão final."; o avatar **coça a cabeça, pensativo**, com "?" flutuando; som suave e descendente.
   - **Pular:** Enter, Espaço, Esc ou clique, depois de 0,4 s. Passado o tempo, a cena segue sozinha para a próxima pergunta (ou o pódio, na última).
6. **Pódio e revisão:** avatar sobre a plataforma de honra, com holofotes, confete e fanfarra sonora; os degraus 1º, 2º e 3º têm o número centralizado na face frontal, alinhado ao plano isométrico. À esquerda, "Pontuação final" e o total em XP. À direita, a revisão geral rolável: para cada questão, número e título, ícone **e rótulo "Acertou"/"Errou"**, pontos ganhos, enunciado, resposta marcada, gabarito e a justificativa (texto de acerto, ou texto de erro do que foi marcado seguido do texto do gabarito).

### 6.1. Economia

Acerto: 100 XP. Erro: 10 XP (incentivo à participação). Os valores e o rótulo vêm de `GAME_CONFIG`. A pontuação é visível durante as perguntas e na tela de reação.

### 6.2. Atalhos

| Tecla | Efeito |
|---|---|
| Setas | Movem o avatar (perguntas), escolhem o avatar (seleção) e rolam textos |
| Enter / Espaço | Ativam o botão em foco; sem foco, confirmam a porta, avançam telas, confirmam o cadastro e pulam a reação |
| A, B, C, D | Levam o avatar à porta da alternativa e a escolhem |
| Tab / Shift+Tab | Percorrem os botões (e as portas, nas perguntas) com contorno amarelo de foco. Na seleção, o ciclo é: campo do nome → avatares → botões |
| 1 a 9 | Na seleção, com o foco nos avatares, escolhem o avatar |
| H | Abre e fecha a dica |
| Esc | Fecha a dica; volta nas orientações; pula a reação |
| M | Liga/desliga o som |
| R | Repete o último aviso falado (leitor de tela) |
| + e − | Aumentam e reduzem o tamanho do texto |

Com o campo do nome em foco, M, + − e os números são digitação; os botões do canto da tela continuam disponíveis.

## 7. Cenário e renderização (`renderer.js`)

- **Projeção:** `screenX = (x − y)·TW/2 + OX` e `screenY = (x + y)·TH/2 − z·TH + OY`, com tile **96 × 48**.
- **Sala:** grid **12 × 10**, em tamanho real, com origem em (592, 124): o losango fica centralizado e sua ponta inferior toca o início do rodapé. O **fundo da sala passa por trás do cabeçalho**. Piso de ladrilhos metálicos, circuitos (PCB) com trilhos que pulsam (`Math.sin(Date.now()·0.003)`) e blocos de acrílico translúcido. Nas bordas do fundo há painéis de vidro e racks de servidores (voxels com LEDs).
- **Portas:** fileira horizontal na tela (linha `x + y = 12`), centralizada em x = 640, de 120 × 136 px, com moldura metálica, feixe neon, folhas deslizantes e display holográfico. Espaçamento de 250, 190 e 150 px para 2, 3 e 4 portas. Cada porta tem uma **área de clique** e uma **zona de colisão/ativação** para o avatar.
- **Área jogável:** o avatar nasce em (8,5; 7,5), não passa da "parede" das portas (`x + y ≥ 12,75`) nem dos limites da sala.
- **Pódio:** blocos isométricos (`isoBox`) e rótulos projetados na face do bloco (`isoFaceLabel`).
- **API:** `toScreen`, `drawVoxel`, `drawRoom`, `drawDoors`, `drawFade`, `loadLogos(config, callback)`, `setReducedMotion` e utilitários de UI e texto. `window.IsoRenderer` é uma instância (classe em `IsoRendererClass`) com alias `Renderer`.

## 8. Avatares (`avatars.js`)

Nove perfis construídos com prismas isométricos (cabeça cúbica, tronco, braços e pernas articulados por ciclo de passos; ~115 px de altura na escala 1,0). Os perfis são **numerados** (1 a 9; internamente "Avatar 1" a "Avatar 9", usado nos avisos de leitor de tela), e a tela de seleção mostra apenas o número; não há referência a etnia ou gênero, e as descrições falam só de aparência e roupa.

| # | Aparência | Pele |
|---|---|---|
| 1 | Cabelo alto e volumoso, jaqueta tecnológica cinza com detalhes azul neon | `#4A3326` |
| 2 | Tranças com contas azuis, jaleco curto sobre vestido roxo | `#5C3A21` |
| 3 | Cabelo castanho curto, suéter acadêmico com crachá digital | `#F3C99F` |
| 4 | Cabelo castanho longo preso em rabo de cavalo, blusa cinza, saia e headphone | `#F7D5B8` |
| 5 | Corte moderno com mecha rosa, jaqueta techwear lilás | `#E0B088` |
| 6 | Cabelo liso escuro, óculos em neon, camisa social | `#F5DEB3` |
| 7 | Cabelo liso na altura do queixo com franja reta, colete com circuitos azuis, blusa e saia | `#FBE7C6` |
| 8 | Corte tigela, cocar de penas, camiseta preta com grafismos vermelhos e bermuda | `#A0522D` |
| 9 | Cabelo longo e liso, cocar de penas, camisa verde e preta e bermuda | `#B35933` |

- **Construção:** o desenho da cabeça é dividido em três partes (atrás da cabeça, a cabeça, a frente), para que mechas laterais, tranças e fones nunca cubram o rosto. Há tipos de perna (calça, bermuda com sandálias, saia), vestido, cocar de penas e rosto com branco dos olhos, nariz e boca nos perfis em que a pele escura ou a franja dificultavam a leitura.
- **`AvatarManager.drawAvatar(ctx, x, y, index, state, walkFrame, opts)`:** estados `idle`, `walking`, `select` (estático, de frente, 2x), `cheer` (pula com os braços para cima) e `think` (braço dobrado, mão na têmpora, coçando). Em `opts`: `scale`, `t`, `face`, `alpha` e `still` (pose parada, para movimento reduzido). A mão tem **contorno escuro** em todas as poses (necessário em peles escuras); na pose `think`, o antebraço e a mão são desenhados por cima da cabeça, com sombra na lateral.
- **`Player`:** nome, avatar, posição no grid (`gridX`, `gridY`), alvo, velocidade (2,3 unidades/s), estado e direção. `moveTo` (linha reta, com callback de chegada), `moveBy` (teclado contínuo), `update(dt)` e callback `onStep` no ritmo dos passos (o áudio é ligado fora da classe).

## 9. Áudio (`audio.js`)

`window.SoundSystem` (instância; classe em `SoundSystemClass`). O `AudioContext` é criado no primeiro clique, toque ou tecla.

| Método | Som |
|---|---|
| `playStep()` | triangular 120→40 Hz em 0,08 s |
| `playDoorOpen()` | senoides de 440 e 880 Hz (0,15 s cada) com ruído branco modulado |
| `playHintClick()` | senoide de 1200 Hz com fade-out de 0,05 s (também usada nos cliques de interface) |
| `playCorrect()` | arpejo triangular E5, G5, C6 (0,14 s cada) com brilho senoidal de 2093 Hz |
| `playWrong()` | duas senoides descendentes, 392 Hz e 311 Hz, suaves |
| `playSuccessFanfare()` | quadradas C5, E5, G5, C6 (0,12 s cada), no pódio |

`toggleMute()` e `isMuted` alimentam o botão de som e a tecla M.

## 10. Acessibilidade

| Recurso | Como funciona |
|---|---|
| **Leitor de tela** | `A11y.announce` espelha a tela numa região oculta `aria-live` (`#a11y-live`): abertura, orientações, cadastro (inclusive o modo Tab e os avatares escolhidos), pergunta completa (grupo, título, enunciado e alternativas, mais a pontuação atual a partir da 2ª), porta próxima, dica, **resultado da resposta com o XP ganho e o total**, mudo e tamanho do texto. A revisão final vai também para uma lista oculta e navegável (`#a11y-review`) |
| **Contraste** | Os textos de interface usam uma paleta de 10 cores com contraste mínimo de **6,0:1** sobre os fundos usados (medido por cálculo; WCAG AA exige 4,5:1). O texto branco do botão primário tem **4,63:1** a 7,56:1 |
| **Som** | Botão de alto-falante fixo na tela e tecla M |
| **Tamanho do texto** | Botão **A+** (100% → 125% → 150%, e "A−" volta a 100%) e teclas + e −. Os cabeçalhos, rodapés e listas crescem junto; textos em painéis fixos diminuem até 16 px para caber |
| **Fonte e alvos mínimos** | Texto de interface com no mínimo **16 px** e alvos clicáveis de no mínimo **44 px** (em coordenadas do canvas 1280×720) |
| **Movimento reduzido** | Com `prefers-reduced-motion`, o confete é desligado, o wipe vira fade, pulsos e flutuações ficam estáticos, o contador de XP não anima e a reação do avatar usa pose parada |
| **Sem depender só de cor** | A revisão escreve "Acertou"/"Errou" e usa ícones de formas diferentes (✓ e ✕); a reação traz texto ("RESPOSTA CORRETA!" ou "QUASE!"); a porta ativa mostra o rótulo "Enter / Espaço"; o botão "Confirmar" desabilitado explica o motivo |
| **Alternativa às setas** | Letras A–D levam o avatar à porta; cliques e toques também funcionam |
| **Teclado na seleção** | Tab percorre campo do nome → avatares → botões (Shift+Tab ao contrário); com o foco nos avatares, 1 a 9 escolhem |
| **Navegação por teclado** | Tab e Shift+Tab percorrem todos os botões de todas as telas e as portas (Porta A a D), com contorno amarelo visível; Enter ou Espaço ativam. Cada foco é anunciado ao leitor de tela ("Botão Voltar", "Porta C: texto…") |
| **Repetir aviso** | Tecla **R** repete o último anúncio (útil se o leitor de tela perder um aviso) |
| **Celular em retrato** | Em telas de toque, em retrato e estreitas, aparece "Gire o aparelho para a horizontal" no lugar do jogo minúsculo |

## 11. Como executar

Com o servidor Flask no ar (ver `README_ADMIN.md`), abrir `http://127.0.0.1:5000/` e digitar o código de uma coleta criada no painel. Para trocar perguntas, importar os CSVs (UTF-8) pela tela de importação ou editar no painel. Após editar arquivos `.js`, recarregue com Ctrl+F5 para evitar o cache.

### 11.1. Testes automatizados

- `pytest`: suíte do servidor, da API e do jogo servido, incluindo o wrapper de `node --test tests/js/api.test.js` (20 testes do `api.js`: SHA-256 com vetor compartilhado, tokens, montagem do quiz, payload sem dados pessoais, envio com tentativas). O antigo `test_convert.py` está obsoleto.
- `teste.html`: **38 verificações** no navegador, em cinco grupos: ambiente (canvas, áudio, `matchMedia`, nada gravado no navegador), arquivos (scripts, configuração, perguntas, orientações e as duas logos), lógica (estados válidos e inválidos, nome, ordem das perguntas, pontuação, reinício, avatares, jogador, portas) e telas (todas as telas desenhadas e uma partida completa), mais acessibilidade (avisos, tecla R, revisão oculta, Tab, tamanho do texto e mudo). Abre em `/static/game/teste.html` (com o servidor no ar) e traz botões para **ouvir os 6 sons**. O README traz um roteiro de 2 minutos para som e navegadores.

## 12. Decisões de projeto e desvios em relação aos prompts

Decisões tomadas durante a execução (substituem o antigo `DESVIOS.md`):

| Tema | Decisão |
|---|---|
| Base | Código mantido e refinado a cada prompt, sem recomeçar |
| Dados | Chaves do JSON em inglês; CSV com `;`/`,`/tab detectado; 8 perguntas de exemplo; validações extras no conversor; orientações em arquivo; `python3` |
| Telas | Desenho em `screens.js`; `state.js` só FSM e dados; `main.js` só laço e eventos |
| Boot | Boot guard em um único lugar (`GameState.boot()`), com tela de bloqueio |
| Viewport | Letterbox `100vw/100vh`, sem teto de 1280×720; moldura decorativa; sem `image-rendering: pixelated` no canvas |
| Entrada de nome | `<input>` real fora da tela (foco e celular) com o campo desenhado no canvas; `maxlength="15"` mantido; foco inicial garantido |
| Áudio | `SoundSystem` como instância global; destrava também por tecla |
| Cenário | **Tile 96×48**; **sala 12×10 em tamanho real**, portas em linha horizontal, fundo atrás do cabeçalho; portas de 120×136 px |
| Transição | Wipe digital em blocos (e `drawFade` para o fechamento da porta), em vez de só um fade preto |
| Brasão | Programa usa `department`; universidade usa `name` |
| `IsoRenderer` | Instância de classe, com alias `Renderer` |
| Avatares | **Prismas isométricos** (~115 px), em vez de 32×64 achatado; **rótulos numerados** (1 a 9), sem estereótipos; seleção por **Tab + teclas 1–9**; cores azuis do prompt trocadas por `#58a6ff`; cinco perfis redesenhados (roupas femininas, cocar, bermuda, rosto sempre visível) |
| `Player` | Estendido com movimento contínuo por teclado, limites e callback de passo |
| Laço | `dt` variável com teto de 0,05 s (não constante) |
| Suavização | Desligada só nos avatares, não globalmente |
| Texto dos títulos | Texto nativo em blocos, em vez de pixels ampliados (que ficavam granulados) |
| Feedback | **Imediato**, por decisão posterior ao escopo original (que previa feedback só no final): tela de reação a cada resposta (comemora no acerto; coça a cabeça, pensativo, no erro), pontuação visível durante as perguntas; o pódio e a revisão continuam |
| Pontuação | Rótulo **"XP"** em toda parte, com ícone de moeda dourada no canto da tela de perguntas |
| Logos | Logos reais da UFRA e do PROFIAP, em caixas 3D isométricas de mesma altura (seção 4.5) |
| Rodapé | Alternativas com mais de 3 linhas são cortadas com reticências; manter alternativas curtas |
| Acessibilidade | Todos os recursos da seção 10 |
| Teclado | Tab e Shift+Tab em todas as telas, com foco visível; na seleção de avatar, nome → avatares → botões |
| Leitor de tela | Tecla R repete o último aviso |
| Celular | Aviso para girar o aparelho em retrato (sem redesenhar a interface para telas pequenas) |
| Cabeçalho | Altura limitada a 224 px; o texto encolhe em vez do cenário descer |
| Mão do avatar | Contorno escuro em todas as poses |
| Testes | Testes do conversor em Python e autoteste do jogo em `teste.html`; o som é validado por escuta do usuário |

## 13. Estado da verificação e pontos em aberto

**Verificado:**
- (histórico) o conversor tinha 28 testes próprios; as mesmas validações hoje são testadas na suíte `pytest` (importação de CSV).
- `teste.html` no navegador de teste: 36 verificações na época (hoje 38), todas aprovadas (ambiente, arquivos e logos, lógica e partida completa, acessibilidade).
- No navegador de teste, por entradas reais e por script: fluxo completo (abertura, orientações, nome e avatar, 8 perguntas com a tela de reação e pódio com revisão); sala 12×10 com 2, 3 e 4 portas; seleção por Tab e 1–9; Tab entre botões e portas em todas as telas, com o contorno de foco; tecla R; botão de som e tecla M; botão A+ e teclas + e −; movimento reduzido; contraste medido por cálculo; fonte mínima e alvos conferidos no código.
- Cabeçalho a 150% de texto com um enunciado de 400 caracteres e título longo: letras das portas sempre visíveis.
- Os 9 avatares ampliados, as poses de comemorar e de pensativo com a mão em contorno, e as logos reais nas caixas 3D.
- Aviso "Gire o aparelho": aparece em retrato no celular emulado (375×812) e some na horizontal (812×375).
- Boot guard, transições inválidas bloqueadas, reinício por clique, nada gravado no armazenamento do navegador.

**Ainda não verificado** (depende de você ou de outro ambiente; o roteiro está no README):
- **Som audível**: use os botões de `teste.html` e diga se algum som incomoda;
- outros navegadores: com o servidor no ar, abra `/static/game/teste.html` em cada um;
- **toque em celular real**, incluindo o foco inicial no campo do nome em aparelhos com tela de toque;
- uso com **leitor de tela real** (NVDA, JAWS, VoiceOver): só o texto das regiões e dos avisos foi conferido, não a leitura;
- o aviso em retrato em um **computador com mouse** (a regra exige tela de toque como ponteiro principal; o emulador manteve o modo toque do teste anterior).

**Limitações conhecidas:**
- O canvas é 16:9 e **encolhe em telas pequenas** mesmo na horizontal; os 16 px e 44 px valem no canvas de 1280×720, não em pixels físicos. Não há layout próprio para celular;
- com o texto a 150%, o fundo da sala fica atrás do cabeçalho e o enunciado muito longo pode ficar com fonte menor que a escala pedida;
- cada pergunta suporta 2 a 4 alternativas (letras A–D); alternativas com mais de 3 linhas no rodapé são cortadas com reticências, mas aparecem inteiras na revisão;
- a tecla R repete o último aviso, inclusive os de foco (não guarda um histórico).
