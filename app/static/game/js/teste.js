  (function () {
    'use strict';
    const itens = [];                                  // { grupo, nome, estado: 'ok'|'falha'|'info', detalhe }
    const add = (grupo, nome, estado, detalhe) => itens.push({ grupo, nome, estado, detalhe: detalhe || '' });

    // Executa uma verificação: retorna true / texto de detalhe (ok) ou lança erro (falha).
    function check(grupo, nome, fn) {
      try {
        const r = fn();
        if (r === false) add(grupo, nome, 'falha', 'a verificação retornou falso');
        else add(grupo, nome, 'ok', typeof r === 'string' ? r : '');
      } catch (e) { add(grupo, nome, 'falha', e && e.message ? e.message : String(e)); }
    }
    // Variante assíncrona de check(): espera o resultado de uma função async.
    async function checkA(grupo, nome, fn) {
      try {
        const r = await fn();
        if (r === false) add(grupo, nome, 'falha', 'a verificação retornou falso');
        else add(grupo, nome, 'ok', typeof r === 'string' ? r : '');
      } catch (e) { add(grupo, nome, 'falha', e && e.message ? e.message : String(e)); }
    }
    const espera = ms => new Promise(r => setTimeout(r, ms));
    const igual = (a, b, msg) => { if (JSON.stringify(a) !== JSON.stringify(b)) throw new Error(`${msg || 'valores diferentes'}: esperado ${JSON.stringify(b)}, veio ${JSON.stringify(a)}`); return true; };
    const lanca = (fn, msg) => { try { fn(); } catch (e) { return true; } throw new Error(msg || 'deveria ter lançado erro'); };

    async function verificar() {
      itens.length = 0;
      const CFG = window.GAME_CONFIG;

      // As perguntas não vêm mais de arquivo: chegam do servidor. Aqui simulamos a resposta de /api/coleta/iniciar (com tokens
      // reais, gerados pelo próprio api.js) e substituímos a rede por funções falsas; o jogo e o resto do código são os de verdade.
      const SAL = 'sal-autoteste', QID = 99;
      const alts = (n, certa, total) => 'ABCD'.slice(0, total).split('').map(l => ({ letra: l, texto: `Alternativa ${l} da pergunta ${n}`,
        texto_acerto: l === certa ? 'Correto!' : null, texto_erro: l === certa ? null : 'Não é essa.' }));
      const modelo = [[1, 'C', 4, 'Segurança Digital', 'Uma dica.'], [2, 'B', 3, 'Tecnologia', null], [3, 'A', 2, 'Gestão', null], [4, 'D', 4, 'Tecnologia', null]];
      const servidor = { coleta: { codigo: 'ABCDE' }, questionario: { id: QID, nome: 'Autoteste', sal: SAL,
        orientacoes: '# Orientações\n- São {{totalPerguntas}} perguntas.\n- Boa sorte!',
        perguntas: await Promise.all(modelo.map(async ([n, certa, total, grupo, dica]) => ({ numero: n, titulo: `Tema ${n}`, grupo, texto: `Enunciado ${n}?`,
          autoajuda: dica, token_correta: await TQApi.token(SAL, QID, n, certa), alternativas: alts(n, certa, total) }))) } };
      const FIX = await TQApi.montaQuiz(servidor);
      window.ORIENTACOES = FIX.orientacoes;
      window.__envios = [];
      TQApi.iniciar = async codigo => codigo === 'ABCDE' ? { ok: true, dados: servidor } : { ok: false, motivo: 'inexistente', mensagem: 'Código não encontrado.' };
      TQApi.enviarPartida = async payload => { window.__envios.push(payload); return { ok: true, duplicada: false }; };

      // ---------------- Ambiente ----------------
      add('Ambiente', 'Como a página foi aberta', 'info', location.protocol + '//' + (location.host || '(arquivo local)'));
      add('Ambiente', 'Navegador', 'info', navigator.userAgent);
      check('Ambiente', 'Canvas 2D disponível', () => { const c = document.createElement('canvas').getContext('2d'); if (!c) throw new Error('sem canvas 2d'); return true; });
      check('Ambiente', 'Web Audio API disponível', () => { if (!(window.AudioContext || window.webkitAudioContext)) throw new Error('sem AudioContext'); return true; });
      check('Ambiente', 'matchMedia disponível (movimento reduzido, toque)', () => typeof window.matchMedia === 'function' || (() => { throw new Error('sem matchMedia'); })());
      const snap = () => { const o = {}; try { for (let i = 0; i < localStorage.length; i++) o['L:' + localStorage.key(i)] = localStorage.getItem(localStorage.key(i)); } catch (e) {} try { for (let i = 0; i < sessionStorage.length; i++) o['S:' + sessionStorage.key(i)] = sessionStorage.getItem(sessionStorage.key(i)); } catch (e) {} o.cookie = document.cookie; return JSON.stringify(o); };
      const antesDados = snap();
      add('Ambiente', 'Tela de toque como ponteiro principal', 'info', window.matchMedia && matchMedia('(pointer: coarse)').matches ? 'sim' : 'não');
      add('Ambiente', 'Preferência por movimento reduzido', 'info', window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches ? 'sim' : 'não');

      // ---------------- Arquivos e dados ----------------
      ['GAME_CONFIG', 'TQApi', 'SoundSystem', 'IsoRenderer', 'AvatarManager', 'Player', 'A11y', 'GameState', 'ScreenManager']
        .forEach(n => check('Arquivos', `Carregado: window.${n}`, () => { if (window[n] === undefined) throw new Error('não definido (arquivo ausente ou com erro)'); return true; }));
      check('Arquivos', 'Configuração com todos os grupos', () => ['institution', 'economy', 'userValidation', 'interface'].every(k => CFG && CFG[k]) || (() => { throw new Error('grupo ausente'); })());
      check('Arquivos', 'Perguntas válidas (2 a 4 alternativas, 1 correta)', () => {
        const g = new GameStateClass(); if (!g.boot()) throw new Error(g.bootErrors.join(' | '));
        g.loadQuiz(FIX, 'ABCDE');
        return `${g.totalQuestions} pergunta(s)`;
      });
      check('Servidor', 'Gabarito por token: a correta é descoberta sem campo "correta"', () => {
        const certas = FIX.quiz.map(q => q.alternatives.filter(a => a.correct).map(a => a.letter).join(''));
        igual(certas, ['C', 'B', 'A', 'D'], 'letras corretas'); if (JSON.stringify(servidor).toLowerCase().includes('"correta"')) throw new Error('o JSON do servidor expõe "correta"'); return true;
      });
      await checkA('Servidor', 'SHA-256 do navegador e o puro dão o mesmo resultado', async () => {
        const a = await TQApi.sha256Hex('sal-de-teste73B'), b = await TQApi.sha256Hex('sal-de-teste73B', { forcaPuro: true });
        igual([a, b], ['bb081bac12b82d641a0b581b6a241a80159188fb93a490b9cc80b701c0bc2030', 'bb081bac12b82d641a0b581b6a241a80159188fb93a490b9cc80b701c0bc2030'], 'hash'); return `crypto.subtle: ${!!(window.crypto && window.crypto.subtle)}`;
      });
      check('Servidor', 'Código da turma: só letras, maiúsculas, 5', () => { igual([TQApi.normalizaCodigo(' kmg-1jtx '), TQApi.codigoCompleto('ABCDE'), TQApi.codigoCompleto('ABCD')], ['KMGJT', true, false]); return true; });
      await new Promise(resolve => {
        IsoRenderer.loadLogos(CFG).then(l => {
          add('Arquivos', 'Logo da universidade carregada', l.university ? 'ok' : 'falha', l.university ? `${l.university.naturalWidth}×${l.university.naturalHeight}` : 'não carregou: o jogo usa o brasão de reserva');
          add('Arquivos', 'Logo do programa carregada', l.program ? 'ok' : 'falha', l.program ? `${l.program.naturalWidth}×${l.program.naturalHeight}` : 'não carregou: o jogo usa o brasão de reserva');
          resolve();
        });
      });

      // ---------------- Lógica ----------------
      const novo = () => { const g = new GameStateClass(); g.boot(); g.loadQuiz(FIX, 'ABCDE'); return g; };
      check('Lógica', 'Estados válidos: BOOT → TITLE → ... → PODIUM_REVIEW → TITLE', () => {
        const g = novo(); const S = g.STATES;
        igual(g.current, S.TITLE); g.go(S.INSTRUCTIONS); g.go(S.AVATAR_SELECT); g.startQuiz('Ana', 0);
        igual(g.current, S.QUIZ_PLAYING); g.answer(g.currentQuestion, g.currentQuestion.alternatives[0]); g.go(S.ANSWER_FEEDBACK);
        while (g.advance()) { g.answer(g.currentQuestion, g.currentQuestion.alternatives[0]); g.go(S.ANSWER_FEEDBACK); }
        igual(g.current, S.PODIUM_REVIEW); g.restart(); igual(g.current, S.TITLE); return true;
      });
      check('Lógica', 'Transições inválidas lançam erro', () => {
        const g = novo(); const S = g.STATES;
        lanca(() => g.go(S.QUIZ_PLAYING), 'TITLE → QUIZ_PLAYING deveria falhar');
        g.go(S.INSTRUCTIONS); g.go(S.AVATAR_SELECT); g.startQuiz('Ana', 0);
        lanca(() => g.go(S.QUIZ_PLAYING), 'QUIZ_PLAYING → QUIZ_PLAYING deveria falhar');
        lanca(() => g.go(S.PODIUM_REVIEW), 'QUIZ_PLAYING → PODIUM_REVIEW deveria falhar');
        return true;
      });
      check('Lógica', 'Nome: aceita letras e números (até 15)', () => ['Ana', 'a1', 'Z9', 'x'.repeat(15)].every(n => novo().validName(n)) || (() => { throw new Error('nome válido recusado'); })());
      check('Lógica', 'Nome: recusa vazio, espaço, acento, símbolo, "_" e mais de 15', () => {
        const g = novo(); const ruins = ['', 'Ana Maria', 'José', 'ana_1', 'a-b', 'x'.repeat(16), 'Ana!', ' Ana'];
        const aceitos = ruins.filter(n => g.validName(n)); if (aceitos.length) throw new Error('aceitou: ' + JSON.stringify(aceitos)); return true;
      });
      check('Lógica', 'Perguntas em ordem de número e alternativas em ordem de letra', () => {
        const g = novo(); const ids = g.questions.map(q => q.id);
        igual(ids, ids.slice().sort((a, b) => a - b), 'perguntas fora de ordem');
        g.questions.forEach(q => { const l = q.alternatives.map(a => a.letter); igual(l, l.slice().sort(), 'alternativas fora de ordem na pergunta ' + q.id); }); return true;
      });
      check('Lógica', 'Pontuação: acerto e erro somam os valores da configuração', () => {
        const g = novo(); const E = CFG.economy; g.go(g.STATES.INSTRUCTIONS); g.go(g.STATES.AVATAR_SELECT); g.startQuiz('Ana', 1);
        const q = g.currentQuestion, certa = q.alternatives.find(a => a.correct), errada = q.alternatives.find(a => !a.correct);
        g.answer(q, certa); igual(g.score, E.pointsCorrect, 'acerto'); g.answer(q, errada); igual(g.score, E.pointsCorrect + E.pointsIncorrect, 'erro');
        const h = g.lastAnswer; igual([h.isCorrect, h.points, h.correctLetter], [false, E.pointsIncorrect, certa.letter]); return true;
      });
      check('Lógica', 'Jogar Novamente zera nome, avatar, pontos e histórico', () => {
        const g = novo(); g.go(g.STATES.INSTRUCTIONS); g.go(g.STATES.AVATAR_SELECT); g.startQuiz('Ana', 4);
        g.answer(g.currentQuestion, g.currentQuestion.alternatives[0]); g.go(g.STATES.ANSWER_FEEDBACK);
        while (g.advance()) g.go(g.STATES.ANSWER_FEEDBACK); g.restart();
        igual([g.playerName, g.selectedAvatar, g.score, g.answersHistory.length, g.currentQuestionIndex], ['', null, 0, 0, 0]); return true;
      });
      check('Lógica', 'Avatares: 9 perfis, rótulos numerados e sem estereótipos', () => {
        const c = AvatarManager.catalog; igual(c.length, 9, 'quantidade'); c.forEach((p, i) => igual(p.label, 'Avatar ' + (i + 1), 'rótulo'));
        const texto = c.map(p => p.label + ' ' + p.short + ' ' + p.desc).join(' ');
        if (/negr|branc|asi[aá]tic|ind[ií]gena|transg/i.test(texto)) throw new Error('rótulo com referência a etnia ou gênero'); return true;
      });
      check('Lógica', 'Jogador: anda em linha reta, chega ao alvo e dispara os passos', () => {
        let passos = 0, chegou = 0; const p = new Player('Ana', 0, { gridX: 5, gridY: 5, speed: 2, onStep: () => passos++ });
        p.moveTo(5, 2, { onArrive: () => chegou++ }); for (let i = 0; i < 200 && p.hasTarget; i++) p.update(1 / 60);
        igual([chegou, +p.gridX.toFixed(2), +p.gridY.toFixed(2)], [1, 5, 2]); if (passos < 3) throw new Error('poucos passos: ' + passos); return `${passos} passos`;
      });
      check('Lógica', 'Jogador: limites impedem sair da sala', () => {
        const p = new Player('Ana', 0, { gridX: 1, gridY: 1, speed: 5, bounds: q => { q.gridX = Math.max(0.4, q.gridX); q.gridY = Math.max(0.4, q.gridY); } });
        for (let i = 0; i < 120; i++) { p.moveBy(-1, -1, 1 / 60); p.update(1 / 60); } igual([p.gridX, p.gridY], [0.4, 0.4]); return true;
      });
      check('Lógica', 'Portas: 2, 3 e 4 portas equidistantes e centralizadas', () => {
        [2, 3, 4].forEach(n => {
          const d = IsoRenderer.layoutDoors(n); igual(d.length, n, 'quantidade');
          const xs = d.map(x => Math.round(x.bx)); const passo = xs[1] - xs[0];
          xs.forEach((x, i) => { if (i && Math.abs(x - xs[i - 1] - passo) > 1) throw new Error(`${n} portas fora de passo: ${xs}`); });
          const centro = (xs[0] + xs[n - 1]) / 2; if (Math.abs(centro - IsoRenderer.ISO.cx) > 1) throw new Error(`${n} portas fora do centro: ${centro}`);
        }); return true;
      });

      // ---------------- Telas e fluxo completo (sem tela: usa um canvas fora da página) ----------------
      const cv = document.createElement('canvas'); cv.width = 1280; cv.height = 720;
      const campo = document.createElement('input');
      const SM = ScreenManager, GS = window.GameState; GS.boot(); SM.init(cv.getContext('2d'), campo);
      const ateQue = async (cond, msg) => { const t0 = Date.now(); while (!cond()) { if (Date.now() - t0 > 4000) throw new Error('tempo esgotado: ' + msg); ff(0.05); await espera(15); } };
      const kd = (k, extra) => SM.keyDown(Object.assign({ key: k, repeat: false }, extra));
      const ff = s => { for (let i = 0; i < Math.round(s * 30); i++) { SM.update(1 / 30); if (i % 6 === 0) SM.draw(1 / 5); } SM.draw(1 / 30); };
      const vivo = () => document.getElementById('a11y-live').textContent.replace(/​/g, '');
      await checkA('Telas', 'Todas as telas desenham sem erro e o fluxo completo termina no pódio', async () => {
        const S = GS.STATES, vistos = new Set(), trilha = []; ff(0.2); vistos.add(GS.current); trilha.push(GS.current);
        // TITLE: o código errado é recusado e fica na tela; o certo valida no servidor, carrega as perguntas e segue
        campo.value = 'zzzzz'; SM.onNameInput(); kd('Enter'); await espera(50); ff(0.3);
        igual(GS.current, S.TITLE, 'código inexistente não pode avançar');
        campo.value = 'abc'; SM.onNameInput(); kd('Enter'); ff(0.2); igual(GS.current, S.TITLE, 'código incompleto não pode avançar');
        campo.value = 'abcde'; SM.onNameInput(); igual(campo.value, 'ABCDE', 'o campo converte para maiúsculas');
        kd('Enter'); await ateQue(() => GS.current === S.INSTRUCTIONS && !SM.inTransition, 'validar o código'); ff(0.5);
        igual([GS.quizMeta.codigo, GS.totalQuestions], ['ABCDE', 4], 'questionário carregado'); vistos.add(GS.current); trilha.push(GS.current);
        kd('Enter'); ff(2); vistos.add(GS.current); trilha.push(GS.current);
        campo.value = 'Autoteste'; SM.onNameInput(); kd('4'); kd('Enter'); ff(2); vistos.add(GS.current); trilha.push(GS.current);
        igual([GS.current, GS.playerName, GS.selectedAvatar], [S.QUIZ_PLAYING, 'Autoteste', 3], 'cadastro (trilha de estados: ' + trilha.join(' > ') + ')');
        const n = GS.totalQuestions; let guard = 0;
        while (GS.current !== S.PODIUM_REVIEW && guard++ < 4000) {
          vistos.add(GS.current);
          if (SM.inTransition) { ff(0.1); continue; }
          if (GS.current === S.QUIZ_PLAYING && SM.Q.phase === 'play') { const dr = SM.Q.doors.find(d => d.alt.correct); SM.Q.a.gridX = dr.gx; SM.Q.a.gridY = 0.9; kd('Enter'); ff(0.2); }
          else ff(0.2);
        }
        vistos.add(GS.current);
        igual([GS.current, GS.answersHistory.length, GS.score], [S.PODIUM_REVIEW, n, n * CFG.economy.pointsCorrect], 'resultado final');
        await ateQue(() => GS.saveStatus.estado === 'salvo', 'gravar a partida'); ff(1);         // o relatório só aparece depois de gravar
        Object.values(S).filter(s => s !== S.BOOT).forEach(s => { if (!vistos.has(s)) throw new Error('tela não visitada: ' + s); });
        return `${n} perguntas, ${GS.score} ${CFG.economy.currencySymbol}`;
      });
      check('Servidor', 'A partida enviada leva só o necessário (sem XP, nome nem avatar) e os tempos', () => {
        igual(window.__envios.length, 1, 'um único envio'); const p = window.__envios[0];
        igual(Object.keys(p).sort(), ['codigo', 'respostas', 'uuid'], 'campos do envio'); igual(p.codigo, 'ABCDE');
        if (!/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(p.uuid)) throw new Error('uuid inválido: ' + p.uuid);
        igual(p.respostas.map(r => r.pergunta), [1, 2, 3, 4], 'perguntas'); igual(p.respostas.map(r => r.ordem), [1, 2, 3, 4], 'ordem');
        igual(p.respostas.map(r => r.alternativa), ['C', 'B', 'A', 'D'], 'letras escolhidas (o teste acerta todas)');
        p.respostas.forEach(r => { igual(Object.keys(r).sort(), ['alternativa', 'ordem', 'pergunta', 'tempo_ms'], 'campos de uma resposta'); if (!(Number.isInteger(r.tempo_ms) && r.tempo_ms >= 0)) throw new Error('tempo inválido ' + r.tempo_ms); });
        return true;
      });
      check('Acessibilidade', 'Avisos de leitor de tela e tecla R (repetir)', () => {
        ff(1);                                                   // espera a transição do pódio terminar (as teclas são ignoradas durante ela)
        if (!vivo()) throw new Error('a região aria-live está vazia'); const antes = vivo();
        document.getElementById('a11y-live').textContent = ''; kd('r'); if (vivo() !== antes) throw new Error('R não repetiu o último aviso'); return true;
      });
      check('Acessibilidade', 'Revisão final disponível em lista oculta', () => { const n = document.querySelectorAll('#a11y-review li').length; if (n !== GS.totalQuestions) throw new Error(`${n} itens, esperado ${GS.totalQuestions}`); return `${n} itens`; });
      check('Acessibilidade', 'Tab percorre os botões (e Enter ativa o som)', () => {
        ff(1); kd('Tab'); ff(0.05); kd('Tab'); ff(0.05); const mudo = SoundSystem.isMuted; kd('Tab'); ff(0.05); const alvo = vivo();
        if (!/^Botão /.test(alvo)) throw new Error('sem anúncio de botão: ' + alvo); return alvo;
      });
      check('Acessibilidade', 'Tamanho do texto: níveis 100%, 125% e 150%', () => {
        SM.setFontLevel(0); SM.setFontLevel(1); igual(SM.fontLevel, 1); SM.setFontLevel(2); ff(0.1); igual(SM.fontLevel, 2); SM.setFontLevel(0); return true;
      });
      check('Acessibilidade', 'Som: alternar mudo', () => { const a = SoundSystem.isMuted; SM.toggleMute(); const b = SoundSystem.isMuted; SM.toggleMute(); if (a === b || SoundSystem.isMuted !== a) throw new Error('mudo não alternou'); return true; });
      check('Acessibilidade', 'O jogo não grava dados no navegador (localStorage, sessionStorage, cookies)', () => { if (snap() !== antesDados) throw new Error('os dados do navegador mudaram durante o teste'); return true; });

      mostrar();
    }

    function mostrar() {
      const ok = itens.filter(i => i.estado === 'ok').length, falhas = itens.filter(i => i.estado === 'falha').length;
      const resumo = document.getElementById('resumo');
      resumo.className = falhas ? 'falha' : 'ok';
      resumo.textContent = falhas ? `${falhas} verificação(ões) falharam, ${ok} passaram.` : `Tudo certo: ${ok} verificações passaram.`;
      const grupos = {}; itens.forEach(i => (grupos[i.grupo] = grupos[i.grupo] || []).push(i));
      const alvo = document.getElementById('resultados'); alvo.textContent = '';
      Object.keys(grupos).forEach(g => {
        const h = document.createElement('h2'); h.textContent = g; alvo.appendChild(h);
        const ul = document.createElement('ul');
        grupos[g].forEach(i => {
          const li = document.createElement('li'); li.className = i.estado;
          const tag = document.createElement('span'); tag.className = 'tag'; tag.textContent = i.estado === 'ok' ? 'OK' : i.estado === 'falha' ? 'FALHA' : 'INFO';
          const corpo = document.createElement('div'); corpo.textContent = i.nome;
          if (i.detalhe) { const d = document.createElement('div'); d.className = 'detalhe'; d.textContent = i.detalhe; corpo.appendChild(d); }
          li.appendChild(tag); li.appendChild(corpo); ul.appendChild(li);
        });
        alvo.appendChild(ul);
      });
    }

    function relatorio() {
      return ['Autoteste TechQuiz Campus', new Date().toLocaleString(), ''].concat(itens.map(i => `[${i.estado.toUpperCase()}] ${i.grupo} - ${i.nome}${i.detalhe ? ' (' + i.detalhe + ')' : ''}`)).join('\n');
    }

    // Sons para ouvir
    const sons = [['Passo', 'playStep'], ['Porta abrindo', 'playDoorOpen'], ['Clique', 'playHintClick'], ['Acerto', 'playCorrect'], ['Erro', 'playWrong'], ['Fanfarra do pódio', 'playSuccessFanfare']];
    const caixa = document.getElementById('sons');
    sons.forEach(([nome, metodo]) => {
      const b = document.createElement('button'); b.textContent = nome;
      b.addEventListener('click', () => { SoundSystem.unlock(); setTimeout(() => SoundSystem[metodo](), 60); });
      caixa.appendChild(b);
    });

    // Recarrega a página: o jogo guarda estado (foco, tela atual), então só uma página nova garante uma rodada limpa.
    document.getElementById('rodar').addEventListener('click', () => { document.getElementById('resumo').textContent = 'Executando as verificações…'; location.reload(); });
    document.getElementById('copiar').addEventListener('click', () => {
      const t = relatorio();
      (navigator.clipboard ? navigator.clipboard.writeText(t) : Promise.reject()).then(() => { document.getElementById('resumo').textContent += ' (relatório copiado)'; }, () => { window.prompt('Copie o relatório:', t); });
    });
    verificar();
  })();
