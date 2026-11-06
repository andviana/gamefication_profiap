// Telas do jogo: desenho, lógica de cada estado da FSM e tratamento de entrada por tela.
// O estado (GameState) fica em state.js; o laço principal e os eventos do navegador ficam em main.js.
(function () {
  'use strict';

  const CFG = window.GAME_CONFIG || { interface: { canvasWidth: 1280, canvasHeight: 720 } };
  const W = CFG.interface.canvasWidth, H = CFG.interface.canvasHeight;
  const R = window.IsoRenderer, AV = window.AvatarManager, GS = window.GameState, S = GS.STATES;
  const SANS = R.SANS, MONO = R.MONO, CYAN = R.CYAN;
  const NX = R.ISO.NX, NY = R.ISO.NY, S0 = R.ISO.doorS, FRONT = R.ISO.front;
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const inRect = (p, x, y, w, h) => p.x >= x && p.x <= x + w && p.y >= y && p.y <= y + h;

  // Cores de texto (todas com contraste >= 4,5:1 sobre #0d1117 e #161b22).
  const C = { txt: '#e6edf3', soft: '#c3d1e4', mute: '#9db1c9', title: '#8cc0ff', warn: '#ff8a94', gold: '#f6cf55', ok: '#7cf0a8', okSoft: '#bff3cf' };

  let ctx = null, nameInput = null;
  let T = 0;                 // tempo (s)
  let VT = 0;                // tempo visual: congelado quando o usuário prefere movimento reduzido
  let reduced = false;
  const mouse = { x: -1, y: -1 };
  let buttons = [];
  let scr = null;            // região rolável ativa: { v, max, x, y, w, h }
  let drag = null;
  const keys = {};
  const KF = { label: null };   // botão em foco pelo teclado (Tab/Shift+Tab); Enter ou Espaço o ativam

  // ---------- Tamanho do texto (botão A+ / teclas + e -) ----------
  const FONT_LEVELS = [1, 1.25, 1.5];
  let fontLevel = 0;
  const F = px => Math.round(px * FONT_LEVELS[fontLevel]);
  const font = (px, bold, fam) => `${bold ? 'bold ' : ''}${F(px)}px ${fam || SANS}`;

  const say = text => { if (window.A11y) window.A11y.announce(text); };

  function button(label, x, y, w, h, fn, o) {
    o = o || {};
    const enabled = o.enabled !== false;
    buttons.push({ x, y, w, h, fn, enabled, focusable: true, label, say: `Botão ${label.replace(/\?/g, '').replace(/\s+/g, ' ').trim()}` });   // sem o "?" do ícone da dica
    R.drawButton(ctx, label, x, y, w, h, { enabled, hover: enabled && inRect(mouse, x, y, w, h), primary: o.primary, fontSize: F(o.fontSize || 22) });
  }
  function hit(x, y, w, h, fn, o) { buttons.push({ x, y, w, h, fn, enabled: true, focusable: !!(o && o.label), label: o && o.label, say: o && o.say }); }

  // ---------- Foco por teclado ----------
  const focusList = () => buttons.filter(b => b.focusable && b.enabled);

  function moveFocus(dir) {
    const list = focusList();
    if (!list.length) return;
    let i = list.findIndex(b => b.label === KF.label);
    i = i < 0 ? (dir > 0 ? 0 : list.length - 1) : (i + dir + list.length) % list.length;
    KF.label = list[i].label;
    SoundSystem.playHintClick();
    say(list[i].say || list[i].label);
  }

  function activateFocus() {
    const b = focusList().find(x => x.label === KF.label);
    if (!b) { KF.label = null; return; }
    SoundSystem.playHintClick();
    b.fn();
  }

  // Contorno amarelo em volta do elemento em foco.
  function drawFocusRing() {
    if (!KF.label) return;
    const b = focusList().find(x => x.label === KF.label);
    if (!b) { KF.label = null; return; }
    ctx.save();
    R.rr(ctx, b.x - 5, b.y - 5, b.w + 10, b.h + 10, 12);
    ctx.lineWidth = 4; ctx.strokeStyle = '#ffd866'; ctx.shadowColor = '#ffd866'; ctx.shadowBlur = 10; ctx.stroke();
    ctx.restore();
  }

  // ---------- Transição digital entre telas e entre perguntas ----------
  const Trans = {
    active: false, phase: 'out', t: 0, dur: 0.38, mid: null,
    start(mid) { if (this.active) return; this.active = true; this.phase = 'out'; this.t = 0; this.mid = mid; },
    update(dt) {
      if (!this.active) return;
      this.t += dt;
      if (this.t >= this.dur) {
        if (this.phase === 'out') { this.phase = 'in'; this.t = 0; if (this.mid) this.mid(); } else this.active = false;
      }
    },
    p() { const k = clamp(this.t / this.dur, 0, 1); return this.phase === 'out' ? k : 1 - k; }
  };

  function goTo(state) {
    Trans.start(() => { GS.go(state); onEnter(state); });
  }

  // ---------- Textos configuráveis (as orientações vêm do questionário da coleta, pela API) ----------
  const DEFAULT_ORIENT = '# Orientações\n- Leia cada pergunta e escolha uma porta.\n- Use o mouse ou as setas e Enter/Espaço.\n- Cada pergunta tem uma única tentativa.';
  function orientText() {
    const raw = (typeof window.ORIENTACOES === 'string' && window.ORIENTACOES.trim()) ? window.ORIENTACOES : DEFAULT_ORIENT;
    const tok = {
      titulo: CFG.interface.gameTitle, instituicao: CFG.institution.name, totalPerguntas: GS.totalQuestions,
      pontosCorreta: CFG.economy.pointsCorrect, pontosIncorreta: CFG.economy.pointsIncorrect,
      moeda: CFG.economy.currencyName, sigla: CFG.economy.currencySymbol
    };
    return raw.replace(/\{\{(\w+)\}\}/g, (m, k) => (k in tok ? tok[k] : m));
  }

  // Maior fonte (entre size e minSize) em que o texto cabe em maxW x maxH.
  function fitText(text, maxW, maxH, size, minSize, bold) {
    let lines = [], lh = 0, s = size;
    for (; s >= minSize; s--) {
      ctx.font = `${bold ? 'bold ' : ''}${s}px ${SANS}`;
      lines = R.wrap(ctx, text, maxW);
      lh = Math.round(s * 1.3);
      if (lines.length * lh <= maxH) break;
    }
    return { size: Math.max(s, minSize), lines, lh };
  }

  function drawScrollbar(s) {
    if (s.max <= 0) return;
    const th = Math.max(36, s.h * s.h / (s.h + s.max));
    const ty = s.y + (s.h - th) * (s.v / s.max);
    ctx.fillStyle = 'rgba(88,166,255,.15)'; ctx.fillRect(s.x + s.w - 8, s.y, 6, s.h);
    ctx.fillStyle = 'rgba(88,166,255,.7)'; R.rr(ctx, s.x + s.w - 8, ty, 6, th, 3); ctx.fill();
  }

  // ---------- Botões de acessibilidade: tamanho do texto (A+) e som ----------
  function a11yAnchor() {
    if (GS.current === S.PODIUM_REVIEW) return { x: 16, y: 16 };
    if (GS.current === S.QUIZ_PLAYING) return { x: W - 112, y: Q.footerTop - 56 };
    return { x: W - 112, y: H - 60 };
  }

  function iconButton(x, y, size, label, fn, drawIcon) {
    buttons.push({ x, y, w: size, h: size, fn, enabled: true, focusable: true, label, say: `Botão ${label}` });
    const hov = inRect(mouse, x, y, size, size);
    R.drawPanel(ctx, x, y, size, size, { fill: hov ? 'rgba(31,111,235,.35)' : 'rgba(22,27,34,.92)', stroke: hov ? '#58a6ff' : '#3b5f94', lw: 2, radius: 10 });
    drawIcon(x + size / 2, y + size / 2);
  }

  function drawA11yButtons() {
    const a = a11yAnchor(), size = 44;
    iconButton(a.x, a.y, size, 'Tamanho do texto', cycleFont, (cx, cy) => {
      ctx.fillStyle = C.txt; ctx.font = `bold 22px ${SANS}`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      ctx.fillText(fontLevel >= FONT_LEVELS.length - 1 ? 'A−' : 'A+', cx, cy + 1);
    });
    iconButton(a.x + size + 8, a.y, size, 'Som', toggleMute, (cx, cy) => {
      ctx.save();
      ctx.fillStyle = C.txt; ctx.strokeStyle = C.txt; ctx.lineWidth = 2.5; ctx.lineCap = 'round';
      ctx.beginPath(); ctx.moveTo(cx - 11, cy - 5); ctx.lineTo(cx - 5, cy - 5); ctx.lineTo(cx + 2, cy - 11); ctx.lineTo(cx + 2, cy + 11); ctx.lineTo(cx - 5, cy + 5); ctx.lineTo(cx - 11, cy + 5); ctx.closePath(); ctx.fill();
      if (SoundSystem.isMuted) {
        ctx.strokeStyle = '#ff8a94';
        ctx.beginPath(); ctx.moveTo(cx + 7, cy - 6); ctx.lineTo(cx + 16, cy + 6); ctx.moveTo(cx + 16, cy - 6); ctx.lineTo(cx + 7, cy + 6); ctx.stroke();
      } else {
        ctx.beginPath(); ctx.arc(cx + 2, cy, 8, -0.9, 0.9); ctx.stroke();
        ctx.beginPath(); ctx.arc(cx + 2, cy, 14, -0.9, 0.9); ctx.stroke();
      }
      ctx.restore();
    });
  }

  function setFontLevel(l) {
    fontLevel = clamp(l, 0, FONT_LEVELS.length - 1);
    if (GS.current === S.INSTRUCTIONS) layoutOrient();
    if (GS.current === S.PODIUM_REVIEW) layoutReview();
    say(`Tamanho do texto: ${Math.round(FONT_LEVELS[fontLevel] * 100)} por cento.`);
  }
  function cycleFont() { setFontLevel(fontLevel >= FONT_LEVELS.length - 1 ? 0 : fontLevel + 1); }
  function toggleMute() {
    const m = SoundSystem.toggleMute();
    say(m ? 'Som desligado.' : 'Som ligado.');
  }

  // =====================================================================
  //  BOOT - bloqueio quando falta configuração ou base de perguntas
  // =====================================================================
  function drawBoot() {
    ctx.fillStyle = '#0a0508'; ctx.fillRect(0, 0, W, H);
    ctx.strokeStyle = '#ff4d5e'; ctx.lineWidth = 4; ctx.strokeRect(40, 40, W - 80, H - 80);
    ctx.fillStyle = '#ff6b78'; ctx.font = `bold 34px ${MONO}`; ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic';
    ctx.fillText('ERRO DE INICIALIZAÇÃO', 80, 120);
    ctx.fillStyle = '#ffd7db'; ctx.font = `20px ${MONO}`;
    let y = 170;
    GS.bootErrors.slice(0, 8).forEach(e => { ctx.fillText('• ' + e, 80, y); y += 30; });
    y += 20;
    ['Confira se os arquivos do jogo foram publicados por inteiro',
      '(config/config.js e js/api.js) e recarregue esta página.',
      '',
      'Se o problema continuar, avise o responsável pelo sistema.'
    ].forEach(l => { ctx.fillText(l, 80, y); y += 30; });
  }

  // =====================================================================
  //  TITLE - abertura e código da turma
  // =====================================================================
  // O aluno não se identifica: digita só o código de 5 letras da turma, que o professor cadastrou no painel. O servidor confere
  // se a coleta existe e está no prazo e devolve o questionário (orientações e perguntas).
  const CODE = { busy: false, erro: '', espera: 0, autoFocus: true };
  const CODE_FIELD = { x: W / 2 - 230, y: 292, w: 460, h: 62 };
  const CODE_LEN = window.TQApi ? window.TQApi.TAMANHO_CODIGO : 5;
  const codigoDigitado = () => window.TQApi.normalizaCodigo(nameInput.value);

  // Só letras, em maiúsculas, até 5. Qualquer outro caractere é descartado na hora.
  function onCodeInput() {
    const raw = nameInput.value, clean = window.TQApi.normalizaCodigo(raw);
    if (clean !== raw) {
      if (/[^A-Za-z]/.test(raw)) { CODE.erro = 'O código tem apenas letras, sem números, espaços ou símbolos.'; say(CODE.erro); SoundSystem.playHintClick(); }
      nameInput.value = clean;
    } else if (CODE.erro) CODE.erro = '';          // digitou de novo: o aviso anterior já não vale
  }

  async function submitCode() {
    if (Trans.active || CODE.busy || CODE.espera > 0) return;
    const api = window.TQApi, codigo = codigoDigitado();
    if (!api.codigoCompleto(codigo)) { CODE.erro = `Digite as ${CODE_LEN} letras do código da turma.`; say(CODE.erro); SoundSystem.playHintClick(); return; }
    CODE.busy = true; CODE.erro = ''; say('Validando o código.');
    try {
      const r = await api.iniciar(codigo);
      if (!r.ok) {
        const bloqueado = r.motivo === 'limite_excedido';
        CODE.erro = bloqueado ? 'Muitas tentativas com código errado.' : r.mensagem;     // no bloqueio, só a contagem regressiva complementa
        CODE.espera = bloqueado ? (r.esperaSeg || 0) : 0;
        say(bloqueado ? `${CODE.erro} Aguarde ${r.esperaSeg || 0} segundos.` : r.mensagem); SoundSystem.playWrong();
        return;
      }
      const montado = await api.montaQuiz(r.dados);          // descobre a alternativa correta pelos tokens
      GS.loadQuiz(montado, codigo);
      window.ORIENTACOES = montado.orientacoes;              // o texto das orientações é do questionário
      nameInput.blur();
      goTo(S.INSTRUCTIONS);
    } catch (e) {
      CODE.erro = 'Não foi possível carregar o questionário. Tente de novo.'; say(CODE.erro);
    } finally { CODE.busy = false; }
  }

  function drawCodeField() {
    const F0 = CODE_FIELD, val = codigoDigitado(), focused = document.activeElement === nameInput, completo = val.length === CODE_LEN;
    ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic'; ctx.fillStyle = C.mute; ctx.font = font(16, true);
    ctx.fillText('CÓDIGO DA TURMA', F0.x, F0.y - 10);
    R.drawPanel(ctx, F0.x, F0.y, F0.w, F0.h, { fill: 'rgba(13,17,23,.95)', stroke: completo ? '#3ddc84' : (focused ? CYAN : '#4b688f'), glow: focused ? 14 : 0, radius: 8 });
    const slot = F0.w / CODE_LEN;
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.font = font(36, true, MONO);
    for (let i = 0; i < CODE_LEN; i++) {
      const cx = F0.x + slot * (i + 0.5), cy = F0.y + F0.h / 2 + 2;
      if (val[i]) { ctx.fillStyle = '#ffffff'; ctx.fillText(val[i], cx, cy); }
      else { ctx.fillStyle = 'rgba(157,177,201,.45)'; ctx.fillRect(cx - 13, F0.y + F0.h - 16, 26, 3); }
      if (i === val.length && focused && !completo && (reduced || Math.floor(T * 2) % 2 === 0)) { ctx.fillStyle = CYAN; ctx.fillRect(cx - 1, F0.y + 12, 3, F0.h - 28); }
    }
    hit(F0.x, F0.y, F0.w, F0.h, () => nameInput.focus());
    // mensagem logo abaixo do campo
    ctx.textBaseline = 'alphabetic'; ctx.textAlign = 'center'; ctx.font = font(17);
    let msg, col = C.mute;
    if (CODE.busy) { msg = 'Validando o código…'; col = CYAN; }
    else if (CODE.espera > 0) { msg = `${CODE.erro} Aguarde ${Math.ceil(CODE.espera)} s para tentar de novo.`; col = C.warn; }
    else if (CODE.erro) { msg = CODE.erro; col = C.warn; }
    else msg = 'Peça o código de 5 letras ao seu professor.';
    ctx.fillStyle = col;
    R.wrap(ctx, msg, 780).slice(0, 2).forEach((l, i) => ctx.fillText(l, W / 2, F0.y + F0.h + 28 + i * Math.round(F(17) * 1.25)));
  }

  function drawTitle() {
    R.drawBackground(ctx, VT);
    R.drawLogo(ctx, 'university', 50, 36, 210, 230);
    R.drawLogo(ctx, 'program', W - 260, 36, 210, 230);
    R.pixelText(ctx, CFG.interface.gameTitle, W / 2, 60, 66, CYAN, 'center');
    const k = FONT_LEVELS[fontLevel] - 1;
    ctx.textAlign = 'center'; ctx.textBaseline = 'alphabetic';
    ctx.fillStyle = C.mute; ctx.font = font(22);
    ctx.fillText('Avaliação formativa gamificada · Campus Tecnológico', W / 2, 168);
    ctx.fillStyle = C.txt; ctx.font = font(21, true);
    ctx.fillText(CFG.institution.name, W / 2, 218 + k * 40);
    ctx.fillStyle = C.mute; ctx.font = font(18);
    ctx.fillText(CFG.institution.department, W / 2, 252 + k * 85);
    for (let i = 0; i < AV.catalog.length; i++) {        // elenco de avatares
      const x = W / 2 + (i - 4) * 112;
      AV.drawAvatar(ctx, x, 540, i, 'idle', 0, { scale: 0.9, t: VT + i * 0.7, face: i % 2 ? 'R' : 'L' });
    }
    ctx.fillStyle = 'rgba(88,166,255,.5)'; ctx.fillRect(W / 2 - 520, 552, 1040, 3);
    drawCodeField();
    const pronto = window.TQApi.codigoCompleto(codigoDigitado()) && !CODE.busy && CODE.espera <= 0;
    button(CODE.busy ? 'Validando…' : 'Iniciar', W / 2 - 150, 598, 300, 62, submitCode, { primary: true, fontSize: 28, enabled: pronto });
    ctx.fillStyle = C.soft; ctx.font = font(16); ctx.textAlign = 'center';
    ctx.fillText('Digite o código e pressione Enter ou clique em Iniciar', W / 2, 692);
  }

  // =====================================================================
  //  INSTRUCTIONS - orientações
  // =====================================================================
  const O = { items: [] };
  const O_RECT = { x: 190, y: 170, w: 900, h: 390 };

  function layoutOrient() {
    O.items = [];
    let y = 0;
    for (const raw of orientText().split(/\r?\n/)) {
      const l = raw.trim();
      if (!l) { y += 12; continue; }
      let kind = 'p', txt = l;
      if (l.startsWith('# ')) { kind = 'h'; txt = l.slice(2); } else if (l.startsWith('- ')) { kind = 'li'; txt = l.slice(2); }
      const fs = F(kind === 'h' ? 27 : 20), lh = Math.round(fs * 1.4), indent = kind === 'li' ? 28 : 0;
      ctx.font = `${kind === 'h' ? 'bold ' : ''}${fs}px ${SANS}`;
      const lines = R.wrap(ctx, txt, O_RECT.w - 40 - indent);
      O.items.push({ kind, lines, fs, lh, indent, y: y + (kind === 'h' && y > 0 ? 10 : 0) });
      y += lines.length * lh + (kind === 'h' ? 10 : 4) + (kind === 'h' && y > 0 ? 10 : 0);
    }
    scr = { v: 0, max: Math.max(0, y - O_RECT.h), ...O_RECT };
  }

  function drawInstructions() {
    R.drawBackground(ctx, VT);
    R.drawPanel(ctx, 140, 70, 1000, 570, { glow: 10 });
    R.pixelText(ctx, 'ORIENTAÇÕES', W / 2, 96, 36, CYAN, 'center');
    ctx.save();
    ctx.beginPath(); ctx.rect(O_RECT.x, O_RECT.y, O_RECT.w, O_RECT.h); ctx.clip();
    ctx.textBaseline = 'top'; ctx.textAlign = 'left';
    for (const it of O.items) {
      ctx.font = `${it.kind === 'h' ? 'bold ' : ''}${it.fs}px ${SANS}`;
      ctx.fillStyle = it.kind === 'h' ? C.title : C.txt;
      it.lines.forEach((ln, i) => {
        const y = O_RECT.y + it.y + i * it.lh - scr.v;
        ctx.fillText(ln, O_RECT.x + it.indent, y);
        if (it.kind === 'li' && i === 0) { ctx.fillStyle = CYAN; ctx.fillRect(O_RECT.x + 6, y + it.fs * 0.45, 10, 10); ctx.fillStyle = C.txt; }
      });
    }
    ctx.restore();
    drawScrollbar(scr);
    button('Voltar', 190, 576, 200, 52, () => goTo(S.TITLE));
    button('Continuar', 890, 576, 200, 52, () => goTo(S.AVATAR_SELECT), { primary: true });
  }

  // =====================================================================
  //  AVATAR_SELECT - nome + avatar
  // =====================================================================
  const AVS = { sel: null, warn: '', warnT: 0, autoFocus: false };   // autoFocus: reaplica o foco no nome ao entrar na tela
  const FIELD = { x: 340, y: 120, w: 600, h: 60 };

  function warnName(msg) { AVS.warn = msg; AVS.warnT = 3; say(msg); }

  // Filtra a digitação conforme allowedPattern: rejeita imediatamente espaços, acentos, símbolos e "_".
  function onNameInput() {
    if (GS.current === S.TITLE) return onCodeInput();      // no título, o mesmo campo recebe o código da turma
    const max = CFG.userValidation.maxNameLength;
    const raw = nameInput.value;
    const ok = ch => new RegExp(CFG.userValidation.allowedPattern).test(ch);
    let clean = Array.from(raw).filter(ok).join('');
    const tooLong = clean.length > max;
    clean = clean.slice(0, max);
    if (clean !== raw || tooLong) {
      warnName(`Use apenas letras (sem acento) e números, sem espaços ou símbolos, até ${max} caracteres.`);
      SoundSystem.playHintClick();
    }
    nameInput.value = clean;
  }

  // Aviso quando o navegador vai descartar um caractere por causa do maxlength.
  function onNameBeforeInput(e) {
    if (GS.current === S.TITLE) return;
    const max = CFG.userValidation.maxNameLength;
    if (e.inputType && e.inputType.startsWith('insert') && nameInput.value.length >= max && nameInput.selectionStart === nameInput.selectionEnd) {
      warnName(`O nome pode ter no máximo ${max} caracteres.`);
    }
  }

  function canStart() { return GS.validName(nameInput.value) && AVS.sel !== null; }
  function missingText() {
    const n = !GS.validName(nameInput.value), a = AVS.sel === null;
    if (n && a) return 'Para confirmar, digite um nome válido e escolha um avatar.';
    if (n) return 'Para confirmar, digite um nome válido (letras e números).';
    return 'Para confirmar, escolha um avatar.';
  }
  function startGame() {
    if (Trans.active) return;
    if (!canStart()) { say(missingText()); return; }
    const nm = nameInput.value, av = AVS.sel;
    nameInput.blur();
    Trans.start(() => { GS.startQuiz(nm, av); onEnter(S.QUIZ_PLAYING); });
  }
  // Tab percorre: campo do nome (as teclas digitam) -> grade de avatares (1 a 9 e setas escolhem) -> botões da tela.
  // Shift+Tab percorre ao contrário.
  function avatarTab(dir) {
    AVS.autoFocus = false;
    const list = focusList(), n = 2 + list.length;
    const bi = list.findIndex(b => b.label === KF.label);
    const cur = document.activeElement === nameInput ? 0 : (bi >= 0 ? 2 + bi : 1);
    const next = (cur + dir + n) % n;
    if (next === 0) {
      KF.label = null; nameInput.focus();
      const len = nameInput.value.length;
      nameInput.setSelectionRange(len, len);   // cursor ao final do nome
      say('Campo do nome.');
    } else if (next === 1) {
      KF.label = null; nameInput.blur();
      say('Escolha do avatar. Use as teclas de 1 a 9 ou as setas.');
    } else {
      nameInput.blur(); KF.label = list[next - 2].label;
      say(list[next - 2].say || list[next - 2].label);
    }
    SoundSystem.playHintClick();
  }

  function selectAvatar(i) {
    AVS.sel = i;
    const p = AV.catalog[i];
    say(`Avatar selecionado: ${p.label}. ${p.desc}`);
  }

  function drawAvatarSelect() {
    R.drawBackground(ctx, VT);
    R.pixelText(ctx, 'IDENTIFIQUE-SE', W / 2, 22, 40, CYAN, 'center');
    ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic';
    ctx.fillStyle = C.mute; ctx.font = font(16, true);
    ctx.fillText('SEU NOME', FIELD.x, FIELD.y - 8);
    const val = nameInput.value, valid = GS.validName(val), focused = document.activeElement === nameInput;
    ctx.textAlign = 'right'; ctx.font = font(16);
    ctx.fillText(focused ? 'Tab: ir aos avatares' : 'Shift+Tab: voltar ao nome', FIELD.x + FIELD.w, FIELD.y - 8);
    ctx.textAlign = 'left';
    R.drawPanel(ctx, FIELD.x, FIELD.y, FIELD.w, FIELD.h, {
      fill: 'rgba(13,17,23,.95)', stroke: valid ? '#3ddc84' : (focused ? CYAN : '#4b688f'), glow: focused ? 14 : 0, radius: 8
    });
    ctx.font = font(30, true, MONO); ctx.textBaseline = 'middle';
    if (val) {
      ctx.fillStyle = '#ffffff'; ctx.fillText(val, FIELD.x + 20, FIELD.y + FIELD.h / 2 + 1);
      if (focused && Math.floor(T * 2) % 2 === 0) {
        ctx.fillStyle = CYAN; ctx.fillRect(FIELD.x + 22 + ctx.measureText(val).width, FIELD.y + 14, 3, 32);
      }
    } else {
      ctx.fillStyle = C.mute; ctx.fillText('digite seu nome', FIELD.x + 20, FIELD.y + FIELD.h / 2 + 1);
    }
    ctx.textAlign = 'right'; ctx.font = `16px ${MONO}`; ctx.fillStyle = C.mute;
    ctx.fillText(`${val.length}/${CFG.userValidation.maxNameLength}`, FIELD.x + FIELD.w - 14, FIELD.y + FIELD.h / 2 + 1);
    hit(FIELD.x, FIELD.y, FIELD.w, FIELD.h, () => nameInput.focus());
    ctx.textBaseline = 'alphabetic'; ctx.textAlign = 'center'; ctx.font = font(16);
    ctx.fillStyle = AVS.warnT > 0 ? C.warn : C.mute;
    const info = AVS.warnT > 0 ? AVS.warn : 'Letras e números, sem espaços, acentos ou símbolos.';
    R.wrap(ctx, info, 640).slice(0, 3).forEach((l, i) => ctx.fillText(l, W / 2, FIELD.y + FIELD.h + 26 + i * Math.round(F(16) * 1.25)));   // entre os painéis laterais

    // pré-visualização ampliada (2x), estática e de frente, do avatar selecionado
    R.drawPanel(ctx, 40, 36, 260, 284, { fill: 'rgba(22,27,34,.7)', radius: 12 });
    ctx.textAlign = 'center';
    if (AVS.sel === null) {
      ctx.fillStyle = C.mute; ctx.font = font(16);
      ctx.fillText('Escolha um avatar', 170, 190);
    } else AV.drawAvatar(ctx, 170, 306, AVS.sel, 'select', 0, { scale: 1 });

    // ficha do perfil selecionado (a fonte diminui, até 16 px, para caber no painel)
    R.drawPanel(ctx, 980, 36, 260, 284, { fill: 'rgba(22,27,34,.7)', radius: 12 });
    ctx.textAlign = 'left';
    R.pixelText(ctx, 'PERFIL', 1000, 52, 24, CYAN);
    if (AVS.sel === null) {
      const f = fitText('Clique em um avatar ou use as setas para escolher.', 220, 190, F(16), 16, false);
      ctx.fillStyle = C.mute; ctx.font = `${f.size}px ${SANS}`;
      f.lines.forEach((l, i) => ctx.fillText(l, 1000, 120 + i * f.lh));
    } else {
      const pf = AV.catalog[AVS.sel];
      const t1 = fitText(String(AVS.sel + 1), 220, 70, F(34), 16, true);   // só o número
      ctx.fillStyle = '#ffffff'; ctx.font = `bold ${t1.size}px ${SANS}`;
      t1.lines.forEach((l, i) => ctx.fillText(l, 1000, 116 + i * t1.lh));
      const top = 116 + t1.lines.length * t1.lh + 14;
      const t2 = fitText(pf.desc, 220, 300 - top, F(16), 16, false);
      ctx.fillStyle = C.soft; ctx.font = `${t2.size}px ${SANS}`;
      t2.lines.forEach((l, i) => ctx.fillText(l, 1000, top + i * t2.lh));
    }

    ctx.textAlign = 'center';
    ctx.fillStyle = C.txt; ctx.font = font(18, true);
    ctx.fillText('ESCOLHA SEU AVATAR', W / 2, 322);
    const cw = 132, gap = 6, x0 = (W - (9 * cw + 8 * gap)) / 2, cy = 336, ch = 224;
    const lift = (FONT_LEVELS[fontLevel] - 1) * 40;
    const gridAtiva = !focused && !KF.label;
    if (gridAtiva) R.drawPanel(ctx, x0 - 6, cy - 6, 9 * cw + 8 * gap + 12, ch + 12, { fill: 'rgba(0,0,0,0)', stroke: CYAN, lw: 2, radius: 14, glow: 12 });   // grade ativa: 1 a 9 e setas escolhem
    AV.catalog.forEach((p, i) => {
      const x = x0 + i * (cw + gap), sel = AVS.sel === i, hov = inRect(mouse, x, cy, cw, ch);
      R.drawPanel(ctx, x, cy, cw, ch, {
        fill: sel ? 'rgba(20,59,110,.9)' : (hov ? 'rgba(18,41,70,.95)' : 'rgba(22,27,34,.9)'),
        stroke: sel ? '#a6caf8' : (hov ? CYAN : 'rgba(88,166,255,.35)'), glow: sel ? 16 : 0, lw: sel ? 3 : 2, radius: 10
      });
      AV.drawAvatar(ctx, x + cw / 2, cy + 165 - lift, i, sel ? 'walking' : 'idle', VT * 8, { scale: 1, t: VT + i, face: sel ? 'R' : 'L' });
      ctx.fillStyle = sel ? '#ffffff' : C.soft; ctx.font = font(28, true); ctx.textAlign = 'center'; ctx.textBaseline = 'alphabetic';   // só o número (também é a tecla de atalho)
      ctx.fillText(String(i + 1), x + cw / 2, cy + ch - 12);
      hit(x, cy, cw, ch, () => selectAvatar(i));
    });
    button('Confirmar', W / 2 - 140, 574, 280, 56, startGame, { primary: true, enabled: canStart(), fontSize: 26 });
    ctx.fillStyle = C.mute; ctx.font = font(16); ctx.textAlign = 'center'; ctx.textBaseline = 'alphabetic';
    const hl = Math.round(F(16) * 1.3);
    const dica = focused ? 'Digite o nome · Tab leva aos avatares (teclas 1 a 9 ou ← →)'
      : KF.label ? 'Enter ou Espaço ativam o botão em foco · Tab segue · Shift+Tab volta'
        : '1 a 9 ou ← → escolhem o avatar · Enter confirma · Tab segue para os botões';
    const dl = R.wrap(ctx, dica, 900).slice(0, 2);
    dl.forEach((l, i) => ctx.fillText(l, W / 2, 654 + F(16) - 16 + i * hl));
    if (!canStart()) { ctx.fillStyle = C.warn; ctx.fillText(missingText(), W / 2, 654 + F(16) - 16 + dl.length * hl); }
    button('Voltar', 40, 640, 150, 48, () => goTo(S.INSTRUCTIONS));
  }

  // =====================================================================
  //  QUIZ_PLAYING - perguntas no cenário isométrico
  // =====================================================================
  const Q = { q: null, doors: [], a: null, phase: 'play', timer: 0, chosen: null, hintBtn: null, near: null, footerTop: 652 };
  const SPEED = 2.3;

  // Contador de XP (canto superior direito): o número sobe até a pontuação real e o chip "pulsa" ao ganhar pontos.
  const XP = { shown: 0, target: 0, pulse: 0 };

  function updateXP(dt) {
    if (GS.score !== XP.target) {
      XP.target = GS.score;
      if (reduced) XP.shown = XP.target; else XP.pulse = 1;
    }
    if (XP.shown < XP.target) XP.shown = Math.min(XP.target, XP.shown + Math.max(40 * dt, (XP.target - XP.shown) * 4 * dt));
    XP.pulse = Math.max(0, XP.pulse - dt * 2.5);
  }

  // Moeda dourada desenhada por código (círculo com aro, brilho e uma estrela).
  function drawCoin(cx, cy, r) {
    const g = ctx.createLinearGradient(cx - r, cy - r, cx + r, cy + r);
    g.addColorStop(0, '#ffe58a'); g.addColorStop(1, '#d9a926');
    ctx.save();
    ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.fillStyle = g; ctx.fill();
    ctx.lineWidth = Math.max(2, r * 0.16); ctx.strokeStyle = '#a97d14'; ctx.stroke();
    ctx.beginPath(); ctx.arc(cx, cy, r * 0.68, 0, Math.PI * 2); ctx.lineWidth = Math.max(1, r * 0.08); ctx.strokeStyle = '#c99a1c'; ctx.stroke();
    ctx.beginPath();                                                    // estrela de 4 pontas
    for (let i = 0; i < 8; i++) { const a = -Math.PI / 2 + i * Math.PI / 4, rr = i % 2 ? r * 0.2 : r * 0.5; ctx[i ? 'lineTo' : 'moveTo'](cx + Math.cos(a) * rr, cy + Math.sin(a) * rr); }
    ctx.closePath(); ctx.fillStyle = '#a97d14'; ctx.fill();
    ctx.beginPath(); ctx.arc(cx - r * 0.45, cy - r * 0.5, r * 0.18, 0, Math.PI * 2); ctx.fillStyle = 'rgba(255,255,255,.55)'; ctx.fill();   // brilho
    ctx.restore();
  }

  // Chip "moeda + N XP" alinhado à direita em x; devolve o retângulo ocupado.
  function drawXPChip(xRight, y, h) {
    const label = `${Math.round(XP.shown)} ${CFG.economy.currencySymbol}`;
    ctx.font = font(18, true);
    const tw = ctx.measureText(label).width, r = h / 2 - 3, w = 14 + r * 2 + 8 + tw + 14, x = xRight - w;
    ctx.save();
    const s = 1 + 0.14 * XP.pulse;                                      // pulso ao ganhar pontos
    ctx.translate(x + w / 2, y + h / 2); ctx.scale(s, s); ctx.translate(-(x + w / 2), -(y + h / 2));
    R.drawPanel(ctx, x, y, w, h, { fill: 'rgba(22,27,34,.95)', stroke: C.gold, lw: 2, radius: h / 2, glow: 6 + 10 * XP.pulse });
    drawCoin(x + 14 + r, y + h / 2, r);
    ctx.fillStyle = C.gold; ctx.textAlign = 'left'; ctx.textBaseline = 'middle';
    ctx.fillText(label, x + 14 + r * 2 + 8, y + h / 2 + 1);
    ctx.restore();
    return { x, y, w, h };
  }

  // Mantém o jogador dentro da sala e atrás da "parede" das portas.
  function roomBounds(p) {
    p.gridX = clamp(p.gridX, 0.4, NX - 0.4); p.gridY = clamp(p.gridY, 0.4, NY - 0.4);
    const s = p.depth;
    if (s < FRONT) { p.gridX += (FRONT - s) / 2; p.gridY += (FRONT - s) / 2; }
  }

  function initQuestion() {
    const q = GS.currentQuestion;
    Q.q = q; Q.phase = 'play'; Q.chosen = null; Q.timer = 0; Q.near = null;
    Q.startedAt = performance.now(); Q.tempoMs = 0;          // o tempo de resposta vai ao servidor junto com a escolha
    if (GS.currentQuestionIndex === 0) { XP.shown = 0; XP.target = 0; XP.pulse = 0; }     // nova partida: contador zerado
    GS.activeModalHint = false;
    const layout = R.layoutDoors(q.alternatives.length);   // portas equidistantes e centralizadas
    Q.doors = q.alternatives.map((alt, i) => ({ alt, ...layout[i], open: 0, hl: 0 }));
    Q.a = new Player(GS.playerName, GS.selectedAvatar, {
      gridX: 8.5, gridY: 7.5, speed: SPEED, bounds: roomBounds,
      onStep: () => SoundSystem.playStep()                 // o Player não conhece o áudio: avisa por callback
    });
    const hasHint = !!(q.hint && q.hint.trim());
    say(`Pergunta ${GS.currentQuestionIndex + 1} de ${GS.totalQuestions}. ${GS.currentQuestionIndex > 0 ? 'Pontuação atual: ' + GS.score + ' ' + CFG.economy.currencySymbol + '. ' : ''}${q.group ? 'Grupo: ' + q.group + '. ' : ''}${q.title ? q.title + '. ' : ''}${q.question} ` +
      'Alternativas: ' + q.alternatives.map(a => `${a.letter}, ${a.text}`).join('; ') + '. ' +
      'Pressione a letra da alternativa para ir até a porta, ou use as setas e Enter. ' + (hasHint ? 'Dica disponível: tecla H.' : ''));
  }

  function nearDoor() {
    const a = Q.a, s = a.depth, d = a.lateral;
    let best = null, bd = Infinity;
    Q.doors.forEach(dr => {                                // zona de colisão/ativação de cada porta
      const z = dr.zone;
      if (s > z.s1 || d < z.d0 || d > z.d1) return;
      const dd = Math.abs(d - dr.d);
      if (dd < bd) { bd = dd; best = dr; }
    });
    return best;
  }

  // Clique (ou letra) em uma porta: o avatar caminha em linha reta até a frente dela e então a escolhe.
  function walkToDoor(dr) {
    if (Q.phase !== 'play' || GS.activeModalHint) return;
    Q.a.moveTo((FRONT + 0.05 + dr.d) / 2, (FRONT + 0.05 - dr.d) / 2, { speed: SPEED * 1.15, onArrive: () => chooseDoor(dr) });
  }

  function chooseDoor(dr) {
    if (Q.phase !== 'play' || GS.activeModalHint) return;
    const a = Q.a;
    Q.tempoMs = Math.round(performance.now() - Q.startedAt);   // até escolher a porta (a caminhada e a animação não contam)
    Q.chosen = dr; Q.phase = 'opening'; Q.timer = 0; a.stop(); a.facing = 'L';
    const s = a.depth;                                     // alinha o avatar ao eixo da porta enquanto ela abre
    a.moveTo((s + dr.d) / 2, (s - dr.d) / 2, { speed: 3.5, bounded: false });
    SoundSystem.playDoorOpen();
    say(`Resposta ${dr.alt.letter} registrada.`);          // sem dizer se está certa ou errada
  }

  function enterDoor(dr) {
    const a = Q.a;
    a.facing = 'L';
    a.moveTo((S0 - 0.6 + dr.d) / 2, (S0 - 0.6 - dr.d) / 2, {
      speed: 2.4, bounded: false,
      onArrive: () => {
        a.alpha = 0;
        GS.answer(Q.q, dr.alt, Q.tempoMs);   // tentativa única: grava ao cruzar a porta, sem feedback
        Q.phase = 'closing'; Q.timer = 0;
      }
    });
  }

  function updateQuestion(dt) {
    const a = Q.a;
    if (Q.phase !== 'closing' && Q.phase !== 'leaving') updateXP(dt);   // a contagem sobe na tela de reação
    Q.doors.forEach(dr => {
      const want = (Q.phase === 'play' && !GS.activeModalHint && (nearDoor() === dr || inRect(mouse, dr.rect.x, dr.rect.y, dr.rect.w, dr.rect.h))) ? 1 : 0;
      dr.hl += (want - dr.hl) * Math.min(1, dt * 10);
    });
    if (GS.activeModalHint) { a.stop(); a.update(dt); return; }

    if (Q.phase === 'play') {
      const ax = (keys.ArrowRight ? 1 : 0) - (keys.ArrowLeft ? 1 : 0);
      const ay = (keys.ArrowDown ? 1 : 0) - (keys.ArrowUp ? 1 : 0);
      if (ax || ay) a.moveBy(ax + ay, -ax + ay, dt);       // teclado cancela o alvo do clique
      a.update(dt);
      const near = nearDoor();                              // avisa o leitor de tela ao chegar numa porta
      if (near !== Q.near) {
        Q.near = near;
        if (near) say(`Porta ${near.alt.letter}: ${near.alt.text}. Pressione Enter para confirmar.`);
      }
    } else if (Q.phase === 'opening') {
      Q.timer += dt;
      const dr = Q.chosen;
      dr.open = Math.min(1, Q.timer / 0.5);
      a.update(dt);
      if (dr.open >= 1 && !a.hasTarget) { Q.phase = 'walkin'; enterDoor(dr); }
    } else if (Q.phase === 'walkin') {
      a.update(dt);
      if (Q.phase === 'walkin') a.alpha = clamp((a.depth - (S0 - 0.5)) / 1.1, 0, 1);
    } else if (Q.phase === 'closing') {
      a.update(dt);
      Q.timer += dt;
      Q.chosen.open = Math.max(0, 1 - Q.timer / 0.35);
      if (Q.timer >= 0.5) {
        Q.phase = 'leaving';
        Trans.start(() => { GS.go(S.ANSWER_FEEDBACK); onEnter(S.ANSWER_FEEDBACK); });   // reação do avatar à resposta
      }
    }
  }

  // Altura máxima do cabeçalho: termina acima dos displays das letras das portas (topo em ~229 px).
  const HEADER_MAX = 224;

  // Escolhe a maior fonte em que o enunciado cabe em maxW x maxH (tamanhos preferidos e depois 1 em 1 px, até 16).
  // Se nem a 16 px couber, corta as linhas que sobram e termina com reticências.
  function fitQuestion(text, maxW, maxH) {
    const sizes = [27, 23, 20, 18].map(F);
    for (let s = F(18) - 1; s >= 16; s--) sizes.push(s);
    let size = 16, lines = [];
    for (const s of sizes) {
      ctx.font = `${s}px ${SANS}`;
      size = s; lines = R.wrap(ctx, text, maxW);
      if (lines.length * Math.round(s * 1.22) <= maxH) return { size, lines };
    }
    const keep = Math.max(1, Math.floor(maxH / Math.round(size * 1.22)));
    if (lines.length > keep) { lines = lines.slice(0, keep); lines[keep - 1] = lines[keep - 1].replace(/\s*\S*$/, '') + '…'; }
    return { size, lines };
  }

  function drawQHeader(q) {
    // medidas primeiro: o cabeçalho cresce com o tamanho do texto
    const bh = F(16) + 14, tSize = F(21);
    const hasHint = !!(q.hint && q.hint.trim());
    const titleY = 12 + bh + 8, qY = titleY + tSize + 12;
    const fit = fitQuestion(q.question, hasHint ? 1000 : 1190, HEADER_MAX - 12 - qY);   // o enunciado encolhe, e não o cenário, quando falta espaço
    const lh = Math.round(fit.size * 1.22);
    const hh = Math.max(202, Math.min(HEADER_MAX, qY + fit.lines.length * lh + 12));

    ctx.fillStyle = 'rgba(13,17,23,.94)'; ctx.fillRect(0, 0, W, hh);
    ctx.fillStyle = CYAN; ctx.fillRect(0, hh, W, 2);
    ctx.textBaseline = 'middle'; ctx.textAlign = 'left';
    if (q.group) {                                                    // badge do Grupo, acima do enunciado
      ctx.font = font(16, true);
      const label = q.group.toUpperCase(), bw = ctx.measureText(label).width + 40;
      R.drawPanel(ctx, 40, 12, bw, bh, { fill: 'rgba(31,111,235,.25)', stroke: CYAN, lw: 2, radius: bh / 2, glow: 6 });
      ctx.fillStyle = CYAN; ctx.fillRect(54, 12 + bh / 2 - 4, 8, 8);
      ctx.fillStyle = '#e1ecfb'; ctx.fillText(label, 70, 12 + bh / 2 + 1);
    }
    drawXPChip(W - 40, 12, bh);                                       // pontuação em XP, com ícone de moeda
    const infoY = 12 + bh + 14 + F(16) / 2;
    ctx.textAlign = 'right'; ctx.textBaseline = 'middle'; ctx.fillStyle = C.mute; ctx.font = font(16, true);
    ctx.fillText(`Pergunta ${GS.currentQuestionIndex + 1} de ${GS.totalQuestions} · ${GS.playerName}`, W - 40, infoY);
    ctx.textAlign = 'left';
    if (q.title) {                                                    // o título não invade a linha "Pergunta N de T · nome"
      ctx.font = font(16, true);
      const infoW = ctx.measureText(`Pergunta ${GS.currentQuestionIndex + 1} de ${GS.totalQuestions} · ${GS.playerName}`).width;
      const maxW = Math.max(240, W - 40 - infoW - 40 - 24);
      ctx.font = font(21, true);
      let title = q.title;
      while (title.length > 1 && ctx.measureText(title).width > maxW) title = title.slice(0, -2).trimEnd() + '…';
      ctx.fillStyle = C.title; ctx.fillText(title, 40, titleY + tSize / 2);
    }
    ctx.font = `${fit.size}px ${SANS}`; ctx.fillStyle = '#ffffff'; ctx.textBaseline = 'top';
    fit.lines.forEach((ln, i) => ctx.fillText(ln, 40, qY + i * lh));
    ctx.textBaseline = 'alphabetic';
    Q.hintBtn = null;
    if (hasHint) {                                                    // botão de dica: só existe se houver autoajuda
      const bx = W - 40 - 160, by = Math.max(70, Math.round(infoY + F(16) / 2 + 12));
      Q.hintBtn = { x: bx, y: by, w: 160, h: 54 };
      button('?  DICA', bx, by, 160, 54, openHint, { fontSize: 22 });
    }
  }

  function openHint() {
    if (Q.phase !== 'play' || GS.activeModalHint) return;
    GS.activeModalHint = true; SoundSystem.playHintClick();
    say(`Dica: ${Q.q.hint}`);
  }
  function closeHint() { if (GS.activeModalHint) { GS.activeModalHint = false; SoundSystem.playHintClick(); say('Dica fechada.'); } }

  // Rodapé com o texto das alternativas; cresce com o tamanho do texto (até 3 linhas, com reticências).
  function drawQFooter(q) {
    const n = q.alternatives.length, colW = (W - 60) / n;
    const chip = F(26), fs = F(16), lh = Math.round(fs * 1.2);
    ctx.font = `${fs}px ${SANS}`;
    let maxL = 1;
    const cols = q.alternatives.map(alt => {
      let lines = R.wrap(ctx, alt.text, colW - chip - 18);
      if (lines.length > 3) { lines = lines.slice(0, 3); lines[2] = lines[2].replace(/\s*\S*$/, '') + '…'; }
      maxL = Math.max(maxL, lines.length);
      return lines;
    });
    const fh = Math.max(68, 18 + maxL * lh + 8, chip + 24), fy = H - fh;
    Q.footerTop = fy;
    ctx.fillStyle = 'rgba(13,17,23,.96)'; ctx.fillRect(0, fy, W, fh);
    ctx.fillStyle = CYAN; ctx.fillRect(0, fy, W, 2);
    q.alternatives.forEach((alt, i) => {
      const x = 30 + i * colW;
      R.drawPanel(ctx, x, fy + 10, chip, chip, { fill: '#0e386e', stroke: CYAN, radius: 5, lw: 1.5 });
      ctx.fillStyle = '#fff'; ctx.font = font(16, true, MONO); ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      ctx.fillText(alt.letter, x + chip / 2, fy + 10 + chip / 2 + 1);
      ctx.textAlign = 'left'; ctx.textBaseline = 'top'; ctx.font = `${fs}px ${SANS}`; ctx.fillStyle = C.soft;
      cols[i].forEach((ln, k) => ctx.fillText(ln, x + chip + 8, fy + 10 + k * lh));
    });
    ctx.textBaseline = 'alphabetic';
  }

  function drawHintModal(q) {
    buttons.length = 0;
    ctx.fillStyle = 'rgba(0,0,0,.6)'; ctx.fillRect(0, 0, W, H);
    hit(0, 0, W, H, closeHint);
    const px = 230, py = 150, pw = 820, ph = 400;
    R.drawPanel(ctx, px, py, pw, ph, { fill: 'rgba(22,27,34,.97)', glow: 18 });
    hit(px, py, pw, ph, () => {});
    ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic';
    R.pixelText(ctx, 'DICA', px + 32, py + 22, 32, CYAN);
    const f = fitText(q.hint, pw - 64, 210, F(23), 16, false);   // a fonte diminui, até 16 px, para caber
    ctx.fillStyle = C.txt; ctx.font = `${f.size}px ${SANS}`; ctx.textBaseline = 'top';
    f.lines.forEach((ln, i) => ctx.fillText(ln, px + 32, py + 96 + i * f.lh));
    ctx.textBaseline = 'alphabetic';
    ctx.fillStyle = C.mute; ctx.font = font(16);
    ctx.fillText('A dica não desconta XP.', px + 32, py + ph - 24);
    button('Fechar', px + pw - 190, py + ph - 70, 160, 48, closeHint, { primary: true });
  }

  function drawQuiz() {
    const q = Q.q, a = Q.a;
    R.drawBackground(ctx, VT);
    R.drawRoom(ctx, VT);
    const zone = (Q.phase === 'play' && !GS.activeModalHint) ? nearDoor() : null;
    const sp = R.project(a.gridX, a.gridY, 0);
    const avatar = () => {
      if (a.alpha > 0.01) AV.drawAvatar(ctx, sp[0], sp[1], a.avatarIndex, a.state, a.walkPhase, { scale: 1.1, t: VT, face: a.facing, alpha: a.alpha });
    };
    if (Q.phase === 'walkin') {                                        // dentro da eclusa, atrás da moldura
      Q.doors.forEach(dr => R.drawDoorBack(ctx, dr.bx, dr.by, VT, dr.open));
      avatar();
      Q.doors.forEach(dr => { R.drawDoorFront(ctx, dr.bx, dr.by, VT, dr.open, dr.hl); R.drawHolo(ctx, dr.bx, dr.by, dr.alt.letter, VT, dr.hl); });
    } else {
      R.drawDoors(ctx, Q.doors.length, Q.doors.map(dr => ({ letter: dr.alt.letter, open: dr.open, glow: dr.hl })));
      avatar();
    }
    if (Q.phase === 'closing') R.drawFade(ctx, Math.min(0.45, Q.timer));
    if (zone) {
      const label = 'Enter / Espaço';
      ctx.font = font(16, true);
      const w = ctx.measureText(label).width + 28, bh = F(16) + 14;
      R.drawPanel(ctx, sp[0] - w / 2, sp[1] - 172, w, bh, { fill: 'rgba(13,17,23,.94)', radius: bh / 2, glow: 8 });
      ctx.fillStyle = '#fff'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      ctx.fillText(label, sp[0], sp[1] - 172 + bh / 2 + 1); ctx.textBaseline = 'alphabetic';
    }
    drawQFooter(q);
    const fy = Q.footerTop;
    ctx.fillStyle = C.mute; ctx.font = font(16); ctx.textAlign = 'left';
    const tips = ['Setas: mover · Enter/Espaço ou letra: escolher porta', 'Clique em uma porta para ir até ela'];
    tips.forEach((tx, i) => ctx.fillText(tx, 30, fy - 12 - (tips.length - 1 - i) * Math.round(F(16) * 1.25)));
    drawQHeader(q);
    if (Q.phase === 'play' && !GS.activeModalHint) {
      Q.doors.forEach(dr => hit(dr.rect.x, dr.rect.y, dr.rect.w, dr.rect.h, () => walkToDoor(dr),
        { label: `Porta ${dr.alt.letter}`, say: `Porta ${dr.alt.letter}: ${dr.alt.text}. Enter para escolher.` }));
    }
    drawA11yButtons();
    if (GS.activeModalHint) drawHintModal(q);
  }

  // =====================================================================
  //  ANSWER_FEEDBACK - reação do avatar à resposta (comemora ou coça a cabeça, pensativo)
  // =====================================================================
  const FB = { t: 0, ok: false, h: null, dur: 2.4, parts: [] };

  function initFeedback() {
    const h = GS.lastAnswer, sym = CFG.economy.currencySymbol;
    FB.h = h; FB.ok = !!(h && h.isCorrect); FB.t = 0; FB.dur = reduced ? 1.8 : 2.4;
    FB.parts = (FB.ok && !reduced) ? Array.from({ length: 90 }, (_, i) => ({
      x: Math.random() * W, y: -Math.random() * H * 0.6, vx: (Math.random() - 0.5) * 60, vy: 120 + Math.random() * 180,
      s: 5 + Math.random() * 8, r: Math.random() * 6, vr: (Math.random() - 0.5) * 10,
      c: ['#58a6ff', '#f2c230', '#ff5d8f', '#72acf8', '#7cf0a8'][i % 5]
    })) : [];
    if (FB.ok) SoundSystem.playCorrect(); else SoundSystem.playWrong();
    say(FB.ok
      ? `Resposta correta! Mais ${h.points} ${sym}. Total: ${GS.score} ${sym}.`
      : `Resposta incorreta, mas você ganhou ${h.points} ${sym} pela participação. Total: ${GS.score} ${sym}.`);
  }

  function updateFeedback(dt) {
    FB.t += dt;
    updateXP(dt);
    FB.parts.forEach(c => { c.x += c.vx * dt; c.y += c.vy * dt; c.r += c.vr * dt; if (c.y > H + 10) { c.y = -10; c.x = Math.random() * W; } });
    if (FB.t >= FB.dur && !Trans.active) finishFeedback();
  }

  function finishFeedback() {
    if (Trans.active || GS.current !== S.ANSWER_FEEDBACK) return;
    Trans.start(() => { GS.advance(); onEnter(GS.current); });      // próxima pergunta ou pódio
  }
  function skipFeedback() { if (FB.t > 0.4) finishFeedback(); }

  // estrela de 4 pontas
  function star(cx, cy, r, col, alpha) {
    ctx.save(); ctx.globalAlpha = alpha; ctx.fillStyle = col; ctx.beginPath();
    for (let i = 0; i < 8; i++) { const a = -Math.PI / 2 + i * Math.PI / 4, rr = i % 2 ? r * 0.32 : r; ctx[i ? 'lineTo' : 'moveTo'](cx + Math.cos(a) * rr, cy + Math.sin(a) * rr); }
    ctx.closePath(); ctx.fill(); ctx.restore();
  }

  function drawFeedback(dt) {
    const ok = FB.ok, h = FB.h, sym = CFG.economy.currencySymbol, cx = 640, cy = 530;
    R.drawBackground(ctx, VT);
    ctx.save();                                                       // holofotes (quentes no acerto, azuis no erro)
    [-1, 1].forEach(s => {
      const g = ctx.createLinearGradient(0, 0, 0, cy);
      g.addColorStop(0, ok ? 'rgba(255,214,102,.30)' : 'rgba(130,180,245,.22)'); g.addColorStop(1, 'rgba(130,180,245,0)');
      R.poly(ctx, [[cx + s * 330, 0], [cx + s * 400, 0], [cx + 40, cy], [cx - 40, cy]], g);
    });
    ctx.restore();
    // palco
    R.isoBox(ctx, cx, cy, 170, 26, '#3a4c64', '#222e3e', '#17212d', ok ? 'rgba(124,240,168,.8)' : 'rgba(88,166,255,.55)');
    ctx.save(); ctx.globalAlpha = 0.35 + (reduced ? 0 : 0.15 * Math.sin(FB.t * 5)); ctx.strokeStyle = ok ? '#7cf0a8' : CYAN; ctx.lineWidth = 3;
    ctx.beginPath(); ctx.ellipse(cx, cy, 110, 55, 0, 0, Math.PI * 2); ctx.stroke(); ctx.restore();
    AV.drawAvatar(ctx, cx, cy, GS.selectedAvatar, ok ? 'cheer' : 'think', 0, { scale: 2.4, t: reduced ? 0.3 : FB.t, still: reduced });

    const head = cy - 235;                                           // altura da cabeça, para efeitos
    if (ok && !reduced) {                                              // explosão de estrelas ao redor do avatar
      for (let i = 0; i < 14; i++) {
        const a = i / 14 * Math.PI * 2 + 0.3, r = 70 + FB.t * 170, al = Math.max(0, 1 - FB.t / 1.7);
        star(cx + Math.cos(a) * r * 1.3, head + 60 + Math.sin(a) * r * 0.8, 10 + (i % 3) * 5, i % 2 ? '#f6cf55' : '#ffffff', al);
      }
    }
    if (!ok) {                                                         // pontos de interrogação flutuando
      [[125, 5, 52], [175, -45, 64], [80, -62, 40]].forEach(([dx, dy, sz], i) => {
        const bob = reduced ? 0 : Math.sin(FB.t * 3 + i * 1.7) * 8;
        const al = reduced ? 1 : Math.min(1, FB.t / 0.4);
        ctx.save(); ctx.globalAlpha = al; ctx.font = `bold ${sz}px ${MONO}`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        ctx.lineJoin = 'round'; ctx.lineWidth = 8; ctx.strokeStyle = '#04070c'; ctx.strokeText('?', cx + dx, head + dy + bob);
        ctx.fillStyle = C.gold; ctx.fillText('?', cx + dx, head + dy + bob); ctx.restore();
      });
    }

    // faixa com o resultado e os pontos
    const k = reduced ? 1 : Math.min(1, FB.t / 0.35), ease = 1 - Math.pow(1 - k, 3) * (1 + 1.6 * (1 - k));   // entra com leve "estouro"
    ctx.save(); ctx.translate(W / 2, 80); ctx.scale(0.6 + 0.4 * ease, 0.6 + 0.4 * ease); ctx.translate(-W / 2, -80);
    R.pixelText(ctx, ok ? 'RESPOSTA CORRETA!' : 'QUASE!', W / 2, 28, 54, ok ? C.ok : '#ffb454', 'center');
    R.glowText(ctx, `+${h.points} ${sym}`, W / 2, 138, `bold 44px ${MONO}`, C.gold, 14, 'center');
    ctx.restore();
    if (!ok) { ctx.fillStyle = C.soft; ctx.font = font(18); ctx.textAlign = 'center'; ctx.textBaseline = 'alphabetic'; ctx.fillText('Sem problemas: a explicação completa aparece na revisão final.', W / 2, 190); }

    FB.parts.forEach(c => {                                            // confete
      ctx.save(); ctx.translate(c.x, c.y); ctx.rotate(c.r); ctx.globalAlpha = 0.9; ctx.fillStyle = c.c; ctx.fillRect(-c.s / 2, -c.s / 2, c.s, c.s * 0.6); ctx.restore();
    });

    const bh = F(16) + 14;                                             // contador de XP, como na pergunta
    drawXPChip(W - 40, 12, bh);
    ctx.fillStyle = C.mute; ctx.font = font(16, true); ctx.textAlign = 'left'; ctx.textBaseline = 'middle';
    ctx.fillText(`Pergunta ${GS.currentQuestionIndex + 1} de ${GS.totalQuestions}`, 40, 12 + bh / 2);
    if (FB.t > 0.6) {
      ctx.textAlign = 'center'; ctx.textBaseline = 'alphabetic'; ctx.fillStyle = C.mute; ctx.font = font(16);
      ctx.fillText('Enter, Espaço ou clique para continuar', W / 2, H - 28);
    }
    drawA11yButtons();
  }

  // =====================================================================
  //  PODIUM_REVIEW - pódio e revisão geral
  // =====================================================================
  const PD = { items: [], confetti: [], pending: false };   // pending: gravando a partida (o relatório só aparece depois)
  const PD_RECT = { x: 486, y: 150, w: 764, h: 520 };

  function layoutReview() {
    const cw = PD_RECT.w - 28, fs = F(16), lh = Math.round(fs * 1.3);
    let y = 0;
    PD.items = GS.answersHistory.map(h => {
      const f = txt => { ctx.font = `${fs}px ${SANS}`; return R.wrap(ctx, txt, cw - 32); };
      const enun = f(h.questionText);
      const resp = f(`Sua resposta: ${h.selectedLetter}) ${h.selectedText}`);
      const gab = f(`Gabarito: ${h.correctLetter}) ${h.correctText}`);
      const just = f(h.feedbackText || '');
      const extra = (!h.isCorrect && h.correctFeedbackText) ? f(h.correctFeedbackText) : [];
      const head = Math.max(28, F(17)) + 14;
      const height = head + 8 + (enun.length + resp.length + gab.length + just.length + extra.length) * lh + 8 + 6 + (extra.length ? 6 : 0) + 14;
      const it = { h, enun, resp, gab, just, extra, y, height, lh, head };
      y += height + 12;
      return it;
    });
    scr = { v: scr ? Math.min(scr.v, Math.max(0, y - PD_RECT.h)) : 0, max: Math.max(0, y - PD_RECT.h), ...PD_RECT };
  }

  // Frase sobre o envio das respostas (aparece no pódio e é falada aos leitores de tela).
  function saveText() {
    const st = GS.saveStatus;
    if (st.estado === 'salvo') return 'Suas respostas foram enviadas.';
    if (st.estado === 'erro') return st.definitivo ? st.mensagem : `${st.mensagem} Suas respostas ainda não foram enviadas.`;
    return '';
  }

  // Grava a partida no servidor (com tentativas automáticas) e só então mostra o relatório. `repeticao`: o jogador pediu
  // para tentar de novo; o relatório já foi montado, então só se atualiza o estado do envio.
  function startSave(repeticao) {
    PD.pending = true;
    if (!repeticao) scr = null;                      // no reenvio o relatório já existe: a região de rolagem precisa continuar
    say('Salvando suas respostas. Aguarde um instante.');
    const fim = () => { PD.pending = false; if (repeticao) say(saveText()); else initPodium(); };
    GS.salvarPartida().then(fim, e => {
      GS.saveStatus = { estado: 'erro', motivo: 'servidor', mensagem: 'Não foi possível enviar as suas respostas.', definitivo: false };
      fim();
    });
  }

  function drawSaving() {
    R.drawBackground(ctx, VT);
    R.drawPanel(ctx, W / 2 - 330, H / 2 - 110, 660, 220, { fill: 'rgba(13,17,23,.95)', glow: 12, radius: 14 });
    const a = reduced ? 0 : T * 5;
    ctx.save(); ctx.translate(W / 2, H / 2 - 40); ctx.lineWidth = 6; ctx.lineCap = 'round';
    ctx.strokeStyle = 'rgba(88,166,255,.25)'; ctx.beginPath(); ctx.arc(0, 0, 26, 0, Math.PI * 2); ctx.stroke();
    ctx.strokeStyle = CYAN; ctx.beginPath(); ctx.arc(0, 0, 26, a, a + 1.6); ctx.stroke();
    ctx.restore();
    ctx.textAlign = 'center'; ctx.textBaseline = 'alphabetic';
    ctx.fillStyle = C.txt; ctx.font = font(30, true);
    ctx.fillText('Salvando suas respostas…', W / 2, H / 2 + 36);
    ctx.fillStyle = C.mute; ctx.font = font(18);
    ctx.fillText('Não feche esta página. Já já você vê o seu resultado.', W / 2, H / 2 + 74);
  }

  function initPodium() {
    layoutReview();
    scr.v = 0;
    PD.confetti = reduced ? [] : Array.from({ length: 110 }, (_, i) => ({
      x: Math.random() * W, y: -Math.random() * H, vx: (Math.random() - 0.5) * 40, vy: 60 + Math.random() * 110,
      s: 5 + Math.random() * 7, r: Math.random() * 6, vr: (Math.random() - 0.5) * 8,
      c: ['#58a6ff', '#f2c230', '#ff5d8f', '#72acf8', '#85b6f5'][i % 5]
    }));
    SoundSystem.playSuccessFanfare();
    const ok = GS.answersHistory.filter(h => h.isCorrect).length;
    say(`Fim do jogo. ${GS.playerName}, você fez ${GS.score} ${CFG.economy.currencySymbol}, com ${ok} de ${GS.answersHistory.length} questões corretas. ${saveText()} A revisão completa está na lista logo abaixo.`);
    if (window.A11y) window.A11y.setReview(GS.answersHistory.map(h =>
      `Questão ${h.questionId}${h.questionTitle ? ', ' + h.questionTitle : ''}. ${h.questionText} Você marcou ${h.selectedLetter}, ${h.selectedText}. ` +
      `Resultado: ${h.isCorrect ? 'acertou' : 'errou'}, ${h.points} ${CFG.economy.currencySymbol}. Gabarito: ${h.correctLetter}, ${h.correctText}. ` +
      `${h.feedbackText || ''} ${(!h.isCorrect && h.correctFeedbackText) ? h.correctFeedbackText : ''}`));
  }

  function drawCheck(x, y, ok) {
    ctx.fillStyle = ok ? '#22c55e' : '#ef4444';
    ctx.beginPath(); ctx.arc(x, y, 13, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = '#fff'; ctx.lineWidth = 3.5; ctx.lineCap = 'round'; ctx.beginPath();
    if (ok) { ctx.moveTo(x - 6, y); ctx.lineTo(x - 2, y + 5); ctx.lineTo(x + 7, y - 5); } else {
      ctx.moveTo(x - 5, y - 5); ctx.lineTo(x + 5, y + 5); ctx.moveTo(x + 5, y - 5); ctx.lineTo(x - 5, y + 5);
    }
    ctx.stroke(); ctx.lineCap = 'butt';
  }

  function drawPodium(dt) {
    if (PD.pending) { drawSaving(); return; }
    R.drawBackground(ctx, VT);
    const cx = 245;
    ctx.save();                                                       // holofotes
    [-1, 1].forEach(s => {
      const g = ctx.createLinearGradient(0, 0, 0, 480);
      g.addColorStop(0, 'rgba(130,180,245,.28)'); g.addColorStop(1, 'rgba(130,180,245,0)');
      R.poly(ctx, [[cx + s * 150, 0], [cx + s * 190, 0], [cx + 20, 480], [cx - 20, 480]], g);
    });
    ctx.restore();
    // plataforma de honra: degraus 2º e 3º mais altos que antes, para caber o número na face frontal
    R.isoBox(ctx, cx, 545, 120, 30, '#3a4c64', '#222e3e', '#17212d', 'rgba(88,166,255,.5)');
    R.isoBox(ctx, cx - 165, 568, 52, 34, '#aab7c8', '#7d8a9b', '#5d6877', 'rgba(255,255,255,.3)');
    R.isoBox(ctx, cx + 165, 574, 52, 28, '#c98a4a', '#9b6934', '#744d25', 'rgba(255,255,255,.25)');
    R.isoBox(ctx, cx, 492, 84, 52, '#f6cf55', '#d9a926', '#a97d14', 'rgba(255,255,255,.5)');
    R.isoFaceLabel(ctx, '1º', cx, 492, 84, 52, 34);
    R.isoFaceLabel(ctx, '2º', cx - 165, 568, 52, 34, 22);
    R.isoFaceLabel(ctx, '3º', cx + 165, 574, 52, 28, 20);
    AV.drawAvatar(ctx, cx, 492, GS.selectedAvatar, 'idle', 0, { scale: 1.75, t: VT, face: 'L' });

    R.pixelText(ctx, 'PARABÉNS!', cx, 22, 38, C.gold, 'center');
    ctx.fillStyle = C.txt; ctx.font = font(26, true); ctx.textAlign = 'center';
    ctx.fillText(GS.playerName, cx, 96 + (F(26) - 26) * 0.5);
    ctx.fillStyle = C.mute; ctx.font = font(16);
    ctx.fillText('Pontuação final', cx, 128 + (F(26) - 26));
    R.glowText(ctx, `${GS.score} ${CFG.economy.currencySymbol}`, cx, 176 + (F(26) - 26), `bold 48px ${MONO}`, C.gold, 14, 'center');

    // situação do envio das respostas ao servidor
    const st = GS.saveStatus, ok = st.estado === 'salvo';
    ctx.textAlign = 'center'; ctx.font = font(16); ctx.fillStyle = ok ? C.ok : C.warn;
    const base = 218 + (F(26) - 26), lh = Math.round(F(16) * 1.3);
    const linhas = R.wrap(ctx, (ok ? '✓ ' : '⚠ ') + saveText(), 400).slice(0, 4);
    linhas.forEach((l, i) => ctx.fillText(l, cx, base + i * lh));
    if (st.estado === 'erro' && !st.definitivo) {
      button('Tentar enviar de novo', 70, base + linhas.length * lh + 6, 350, 46, () => startSave(true), { fontSize: 20 });
    }

    // painel de revisão
    R.drawPanel(ctx, 470, 28, 780, 662, { glow: 8 });
    ctx.textAlign = 'left';
    const acertos = GS.answersHistory.filter(h => h.isCorrect).length;
    R.pixelText(ctx, 'REVISÃO GERAL', 494, 46, 30, CYAN);
    ctx.fillStyle = C.mute; ctx.font = font(17);
    ctx.fillText(`${acertos} de ${GS.answersHistory.length} questões corretas · ${GS.score} ${CFG.economy.currencySymbol}`, 494, 126);
    ctx.save();
    ctx.beginPath(); ctx.rect(PD_RECT.x - 8, PD_RECT.y - 6, PD_RECT.w + 16, PD_RECT.h + 12); ctx.clip();
    PD.items.forEach(it => {
      const top = PD_RECT.y + it.y - scr.v;
      if (top > PD_RECT.y + PD_RECT.h || top + it.height < PD_RECT.y - 10) return;
      const cw = PD_RECT.w - 28, h = it.h, mid = top + it.head / 2 + 4;
      R.drawPanel(ctx, PD_RECT.x, top, cw, it.height, {
        fill: h.isCorrect ? 'rgba(14,50,38,.7)' : 'rgba(58,20,28,.7)', stroke: h.isCorrect ? '#22c55e' : '#ef4444', lw: 1.5, radius: 10
      });
      drawCheck(PD_RECT.x + 28, mid, h.isCorrect);
      ctx.textAlign = 'left'; ctx.textBaseline = 'middle';
      ctx.fillStyle = C.title; ctx.font = font(17, true);
      ctx.fillText(`Questão ${h.questionId}${h.questionTitle ? ' — ' + h.questionTitle : ''}`, PD_RECT.x + 52, mid);
      ctx.textAlign = 'right'; ctx.fillStyle = h.isCorrect ? C.ok : C.warn;
      ctx.fillText(`${h.isCorrect ? 'Acertou' : 'Errou'} · +${h.points} ${CFG.economy.currencySymbol}`, PD_RECT.x + cw - 16, mid);
      ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic';
      const fs = F(16), lh = it.lh;
      let y = top + it.head + 8 + fs;
      ctx.font = `${fs}px ${SANS}`; ctx.fillStyle = '#ffffff';
      it.enun.forEach(l => { ctx.fillText(l, PD_RECT.x + 16, y); y += lh; });
      y += 8;
      ctx.fillStyle = h.isCorrect ? C.ok : C.warn;
      it.resp.forEach(l => { ctx.fillText(l, PD_RECT.x + 16, y); y += lh; });
      ctx.fillStyle = C.okSoft;
      it.gab.forEach(l => { ctx.fillText(l, PD_RECT.x + 16, y); y += lh; });
      y += 6;
      ctx.font = `italic ${fs}px ${SANS}`; ctx.fillStyle = C.soft;
      it.just.forEach(l => { ctx.fillText(l, PD_RECT.x + 16, y); y += lh; });
      if (it.extra.length) { y += 6; ctx.fillStyle = C.mute; it.extra.forEach(l => { ctx.fillText(l, PD_RECT.x + 16, y); y += lh; }); }
    });
    ctx.restore();
    drawScrollbar({ ...scr, x: scr.x + 18 });

    if (!reduced) PD.confetti.forEach(c => {                          // partículas (desligadas com movimento reduzido)
      c.x += c.vx * dt; c.y += c.vy * dt; c.r += c.vr * dt;
      if (c.y > H + 10) { c.y = -10; c.x = Math.random() * W; }
      ctx.save(); ctx.translate(c.x, c.y); ctx.rotate(c.r); ctx.globalAlpha = 0.9;
      ctx.fillStyle = c.c; ctx.fillRect(-c.s / 2, -c.s / 2, c.s, c.s * 0.6);
      ctx.restore();
    });

    button('Jogar Novamente', 70, 640, 350, 52, () => {
      Trans.start(() => {
        PD.pending = false;
        GS.restart(); nameInput.value = ''; AVS.sel = null;
        if (window.A11y) window.A11y.clearReview();
        onEnter(S.TITLE);
      });
    }, { primary: true, fontSize: 24 });
    drawA11yButtons();
  }

  // =====================================================================
  //  Ciclo de vida e entrada
  // =====================================================================
  function onEnter(state) {
    scr = null; drag = null; KF.label = null;
    if (state === S.TITLE) {
      nameInput.maxLength = CODE_LEN; nameInput.setAttribute('aria-label', 'Código da turma');
      nameInput.value = GS.lastCode || '';                 // o mesmo campo recebe o código aqui e o nome na tela seguinte
      CODE.erro = ''; CODE.busy = false; CODE.espera = 0;
      const coarse = !!(window.matchMedia && window.matchMedia('(pointer: coarse)').matches);
      CODE.autoFocus = !coarse;                            // em aparelhos de toque, o teclado virtual só abre quando o jogador tocar no campo
      if (!coarse) nameInput.focus();
      say(`${CFG.interface.gameTitle}. Digite o código da turma, com 5 letras, e pressione Enter. Peça o código ao seu professor. Para ligar o som ou ajustar o texto, use a tecla Tab até os botões.`);
    }
    if (state === S.INSTRUCTIONS) {
      layoutOrient();
      say('Orientações. ' + orientText().split(/\r?\n/).map(l => l.replace(/^(# |- )/, '').trim()).filter(Boolean).join(' '));
    }
    if (state === S.AVATAR_SELECT) {
      nameInput.maxLength = CFG.userValidation.maxNameLength; nameInput.setAttribute('aria-label', 'Nome do jogador');
      nameInput.value = '';                                // saiu o código; entra o nome
      AVS.warnT = 0;
      const coarse = !!(window.matchMedia && window.matchMedia('(pointer: coarse)').matches);
      AVS.autoFocus = !coarse;                 // em aparelhos de toque, o teclado virtual só abre quando o jogador tocar no campo
      if (!coarse) nameInput.focus();
      say('Identifique-se. Digite seu nome, com letras e números, até 15 caracteres. Pressione Tab para ir aos avatares e escolha com as teclas de 1 a 9 ou as setas. Enter confirma.');
    }
    if (state === S.QUIZ_PLAYING) initQuestion();
    if (state === S.ANSWER_FEEDBACK) initFeedback();
    if (state === S.PODIUM_REVIEW) { PD.items = []; startSave(false); }      // grava a partida ANTES de mostrar o relatório
  }

  const ScreenManager = {
    Q, AVS, keys, XP, FB,
    initQuestion,
    get inTransition() { return Trans.active; },
    get fontLevel() { return fontLevel; },
    get reducedMotion() { return reduced; },
    setFontLevel,
    toggleMute,

    init(context, input) { ctx = context; nameInput = input; },
    onNameInput, onNameBeforeInput,

    setPointer(x, y) { mouse.x = x; mouse.y = y; drag && scr && (scr.v = clamp(drag.v - (y - drag.y), 0, scr.max)); },

    pointerDown(x, y) {
      mouse.x = x; mouse.y = y;
      if (Trans.active) return false;
      AVS.autoFocus = false;                  // o jogador assumiu o controle do foco
      KF.label = null;
      for (let i = buttons.length - 1; i >= 0; i--) {
        const b = buttons[i];
        if (b.enabled && inRect(mouse, b.x, b.y, b.w, b.h)) { SoundSystem.playHintClick(); b.fn(); return true; }
      }
      if (GS.current === S.ANSWER_FEEDBACK) { skipFeedback(); return true; }          // clique: pula a reação
      if (scr && inRect(mouse, scr.x, scr.y, scr.w, scr.h)) drag = { y: mouse.y, v: scr.v };
      return false;
    },
    pointerUp() { drag = null; },
    wheel(dy) { if (!scr) return false; scr.v = clamp(scr.v + dy, 0, scr.max); return true; },

    // Retorna true se a tecla foi tratada (o chamador pode então chamar preventDefault).
    keyDown(e) {
      const k = e.key;
      if (Trans.active) return false;
      const st = GS.current;
      const confirm = k === 'Enter' || k === ' ';
      // Setas e Espaço pertencem ao jogo (exceto na tela do nome, onde Espaço é digitação rejeitada pelo filtro);
      // as demais teclas, como Backspace e letras, ficam livres para o campo de texto.
      const prevent = ['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(k) || (k === ' ' && st !== S.AVATAR_SELECT) || (k === 'Tab' && st !== S.BOOT);
      keys[k] = true;
      if (e.repeat && st !== S.INSTRUCTIONS && st !== S.PODIUM_REVIEW) return prevent;

      // Tab / Shift+Tab percorrem os botões; Enter ou Espaço ativam o botão em foco
      if (st !== S.BOOT && k === 'Tab') { if (st === S.AVATAR_SELECT) avatarTab(e.shiftKey ? -1 : 1); else moveFocus(e.shiftKey ? -1 : 1); return true; }
      if (st !== S.BOOT && KF.label && confirm && !(st === S.AVATAR_SELECT && document.activeElement === nameInput)) { activateFocus(); return true; }

      // Atalhos globais (não na tela do nome, onde as teclas são digitação): M = som, + / - = tamanho do texto
      const typing = (st === S.AVATAR_SELECT || st === S.TITLE) && document.activeElement === nameInput;   // com o foco na grade, M, + e − voltam a ser atalhos
      const plain = !e.ctrlKey && !e.metaKey && !e.altKey;
      let handledGlobal = false;
      if (!typing && plain && st !== S.BOOT) {
        if (k === 'm' || k === 'M') { toggleMute(); handledGlobal = true; }
        else if (k === '+' || k === '=') { setFontLevel(fontLevel + 1); handledGlobal = true; }
        else if (k === '-' || k === '_') { setFontLevel(fontLevel - 1); handledGlobal = true; }
        else if (k === 'r' || k === 'R') { if (window.A11y) window.A11y.repeat(); handledGlobal = true; }   // repete o último aviso
      }
      if (handledGlobal) return prevent;

      if (st === S.TITLE) {
        if (k === 'Enter') submitCode();                   // as letras vão para o campo do código
      } else if (st === S.INSTRUCTIONS) {
        if (confirm) goTo(S.AVATAR_SELECT); else if (k === 'Escape') goTo(S.TITLE);
      } else if (st === S.AVATAR_SELECT) {
        const n = AV.catalog.length;
        if (!typing && plain && /^[1-9]$/.test(k) && +k <= n) { selectAvatar(+k - 1); SoundSystem.playHintClick(); }      // atalhos 1 a 9 (só com o foco na grade)
        else if (k === 'ArrowRight') { selectAvatar(AVS.sel === null ? 0 : (AVS.sel + 1) % n); SoundSystem.playHintClick(); }
        else if (k === 'ArrowLeft') { selectAvatar(AVS.sel === null ? n - 1 : (AVS.sel + n - 1) % n); SoundSystem.playHintClick(); }
        else if (k === 'Enter') startGame();
      } else if (st === S.ANSWER_FEEDBACK) {
        if (confirm || k === 'Escape') skipFeedback();
      } else if (st === S.QUIZ_PLAYING) {
        if (k.startsWith('Arrow')) KF.label = null;                      // andar com as setas devolve o Enter à porta próxima
        if (GS.activeModalHint) { if (confirm || k === 'Escape' || k === 'h' || k === 'H') closeHint(); return prevent; }
        if (confirm && Q.phase === 'play') { const dr = nearDoor(); if (dr) chooseDoor(dr); }
        else if ((k === 'h' || k === 'H') && Q.hintBtn) openHint();
        else if (k.length === 1 && plain && Q.phase === 'play') {         // letras A-D: vai até a porta e confirma
          const dr = Q.doors.find(d => d.alt.letter === k.toUpperCase());
          if (dr) { say(`Indo para a porta ${dr.alt.letter}.`); walkToDoor(dr); }
        }
      }
      if (scr) {
        if (k === 'ArrowDown') scr.v = clamp(scr.v + 50, 0, scr.max);
        else if (k === 'ArrowUp') scr.v = clamp(scr.v - 50, 0, scr.max);
        else if (k === 'PageDown') scr.v = clamp(scr.v + scr.h * 0.9, 0, scr.max);
        else if (k === 'PageUp') scr.v = clamp(scr.v - scr.h * 0.9, 0, scr.max);
      }
      return prevent;
    },
    keyUp(k) { keys[k] = false; },
    blur() { for (const k in keys) keys[k] = false; },

    update(dt) {
      T += dt;
      // prefers-reduced-motion é lido a cada quadro (pode mudar com o sistema)
      reduced = !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
      R.setReducedMotion(reduced);
      VT = reduced ? 0 : T;
      if (AVS.warnT > 0) AVS.warnT -= dt;
      Trans.update(dt);
      if (GS.current === S.TITLE && !Trans.active) {
        if (CODE.espera > 0) CODE.espera = Math.max(0, CODE.espera - dt);             // contagem regressiva do bloqueio por tentativas
        if (CODE.autoFocus && !CODE.busy) { if (document.activeElement === nameInput) CODE.autoFocus = false; else nameInput.focus(); }
      }
      if (AVS.autoFocus && GS.current === S.AVATAR_SELECT && !Trans.active) {      // garante o foco inicial no campo do nome
        if (document.activeElement === nameInput) AVS.autoFocus = false; else nameInput.focus();
      }
      if (GS.current === S.QUIZ_PLAYING && !Trans.active) updateQuestion(dt);
      if (GS.current === S.ANSWER_FEEDBACK) updateFeedback(dt);
    },

    draw(dt) {
      buttons = [];
      switch (GS.current) {
        case S.BOOT: drawBoot(); break;
        case S.TITLE: drawTitle(); break;
        case S.INSTRUCTIONS: drawInstructions(); break;
        case S.AVATAR_SELECT: drawAvatarSelect(); break;
        case S.QUIZ_PLAYING: drawQuiz(); break;
        case S.ANSWER_FEEDBACK: drawFeedback(dt); break;
        case S.PODIUM_REVIEW: drawPodium(dt); break;
      }
      if (GS.current === S.TITLE || GS.current === S.INSTRUCTIONS || GS.current === S.AVATAR_SELECT) drawA11yButtons();
      drawFocusRing();
      if (Trans.active) { if (reduced) R.drawFade(ctx, Trans.p()); else R.wipe(ctx, Trans.p()); }   // sem movimento: fade simples
    },

    wantsPointer() { return !Trans.active && buttons.some(b => b.enabled && inRect(mouse, b.x, b.y, b.w, b.h)); }
  };

  window.ScreenManager = ScreenManager;
})();
