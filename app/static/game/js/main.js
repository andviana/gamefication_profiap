// Laço principal, eventos de entrada (mouse/toque/teclado) e inicialização.
// O desenho e a lógica de cada tela ficam em screens.js; o estado, em state.js.
(function () {
  'use strict';

  const CFG = window.GAME_CONFIG;
  const W = CFG ? CFG.interface.canvasWidth : 1280;
  const H = CFG ? CFG.interface.canvasHeight : 720;
  const canvas = document.getElementById('gameCanvas');
  canvas.width = W; canvas.height = H;
  const ctx = canvas.getContext('2d');
  ctx.imageSmoothingEnabled = true;           // textos e logos suavizados; só os avatares desligam (ver avatars.js)
  const nameInput = document.getElementById('avatarNameInput');
  const GS = window.GameState, SM = window.ScreenManager;

  SM.init(ctx, nameInput);
  GS.boot();                                  // BOOT: valida configuração e perguntas; falha = tela de bloqueio

  // O limite de 15 caracteres vem do atributo maxlength do HTML; o ScreenManager filtra os caracteres
  // (regex de GAME_CONFIG) e avisa quando o jogador tenta digitar além do limite.
  nameInput.addEventListener('beforeinput', e => SM.onNameBeforeInput(e));
  nameInput.addEventListener('input', () => SM.onNameInput());

  function toCanvas(e) {
    const r = canvas.getBoundingClientRect();
    return [(e.clientX - r.left) * W / r.width, (e.clientY - r.top) * H / r.height];
  }

  canvas.addEventListener('pointerdown', e => {
    SoundSystem.unlock();
    const [x, y] = toCanvas(e);
    if (SM.pointerDown(x, y)) e.preventDefault();
  });
  canvas.addEventListener('pointermove', e => { const [x, y] = toCanvas(e); SM.setPointer(x, y); });
  window.addEventListener('pointerup', () => SM.pointerUp());
  canvas.addEventListener('wheel', e => { if (SM.wheel(e.deltaY)) e.preventDefault(); }, { passive: false });

  window.addEventListener('keydown', e => {
    SoundSystem.unlock();
    if (SM.keyDown(e)) e.preventDefault();
  });
  window.addEventListener('keyup', e => SM.keyUp(e.key));
  window.addEventListener('blur', () => SM.blur());

  // Laço principal: dt variável (em segundos) com teto, para o movimento não "saltar" após quadros lentos
  // nem quando a aba volta a ficar visível.
  const MAX_DT = 0.05;
  let last = performance.now();
  let cursor = 'default';
  document.addEventListener('visibilitychange', () => { last = performance.now(); });

  function frame(now) {
    const dt = Math.min(MAX_DT, Math.max(0, (now - last) / 1000));
    last = now;
    SM.update(dt);
    SM.draw(dt);
    const c = SM.wantsPointer() ? 'pointer' : 'default';
    if (c !== cursor) { cursor = c; canvas.style.cursor = c; }
    requestAnimationFrame(frame);
  }

  // Pré-carrega as logos (com tempo-limite); se falharem, o fallback procedural é usado.
  const ready = CFG ? Promise.race([IsoRenderer.loadLogos(CFG), new Promise(r => setTimeout(r, 3000))]) : Promise.resolve();
  ready.then(() => { last = performance.now(); requestAnimationFrame(frame); });

  window.__techquiz = { GameState: GS, ScreenManager: SM, Q: SM.Q, AVS: SM.AVS, keys: SM.keys, initQuestion: SM.initQuestion };   // depuração
})();
