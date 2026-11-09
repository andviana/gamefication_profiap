// Projeção isométrica 2.5D, cenário tecnológico, portas, logos (com fallback) e utilitários de UI.
(function () {
  'use strict';

  const TW = 96, TH = 48;
  // Sala NX x NY (12 x 10). A origem (OX, OY) coloca o centro do losango no centro da tela (cx) e a ponta
  // inferior no início do rodapé; o fundo da sala passa por trás do cabeçalho.
  // doorS: linha das portas (x + y constante). front: início da área jogável.
  const ISO = { TW, TH, OX: 592, OY: 124, NX: 12, NY: 10, cx: 640, doorS: 12, front: 12.75 };
  let reduced = false;   // movimento reduzido: pulsos e flutuações do cenário ficam estáticos
  const SANS = '"Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif';
  const MONO = '"Courier New", Courier, monospace';
  const CYAN = '#58a6ff';

  // screenX = (x - y) * TW/2 + OX ;  screenY = (x + y) * TH/2 - z*TH + OY
  function project(x, y, z) {
    return [(x - y) * TW / 2 + ISO.OX, (x + y) * TH / 2 - (z || 0) * TH + ISO.OY];
  }

  // f < 1 escurece, f > 1 clareia (em direção ao branco). Entrada e saída: '#rrggbb'.
  function shade(hex, f) {
    const n = parseInt(hex.slice(1), 16);
    let r = n >> 16 & 255, g = n >> 8 & 255, b = n & 255;
    if (f >= 1) {
      const k = f - 1;
      r += (255 - r) * k; g += (255 - g) * k; b += (255 - b) * k;
    } else {
      r *= f; g *= f; b *= f;
    }
    return '#' + [r, g, b].map(v => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, '0')).join('');
  }

  function hash(i, j) {
    let h = Math.imul(i + 1, 374761393) ^ Math.imul(j + 7, 668265263);
    h = Math.imul(h ^ (h >>> 13), 1274126177);
    return ((h ^ (h >>> 16)) >>> 0) / 4294967295;
  }

  function poly(ctx, pts, fill, stroke, lw) {
    ctx.beginPath();
    pts.forEach((p, i) => (i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])));
    ctx.closePath();
    if (fill) { ctx.fillStyle = fill; ctx.fill(); }
    if (stroke) { ctx.strokeStyle = stroke; ctx.lineWidth = lw || 1; ctx.stroke(); }
  }

  function rr(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }

  // Prisma em coordenadas de grid (x,y,z). Faces visíveis: topo, esquerda (+y) e direita (+x).
  function cube(ctx, x, y, z, w, d, h, col) {
    const P = project;
    poly(ctx, [P(x + w, y, z + h), P(x + w, y + d, z + h), P(x + w, y + d, z), P(x + w, y, z)], shade(col, 0.7));
    poly(ctx, [P(x, y + d, z + h), P(x + w, y + d, z + h), P(x + w, y + d, z), P(x, y + d, z)], col);
    poly(ctx, [P(x, y, z + h), P(x + w, y, z + h), P(x + w, y + d, z + h), P(x, y + d, z + h)], shade(col, 1.2));
  }

  // Bloco unitário (1x1x1) com faces definidas por colors { top, left, right } e traço sutil de 1px.
  function drawVoxel(ctx, gx, gy, gz, colors) {
    const P = project, edge = 'rgba(0,0,0,.35)';
    poly(ctx, [P(gx + 1, gy, gz + 1), P(gx + 1, gy + 1, gz + 1), P(gx + 1, gy + 1, gz), P(gx + 1, gy, gz)], colors.right, edge, 1);
    poly(ctx, [P(gx, gy + 1, gz + 1), P(gx + 1, gy + 1, gz + 1), P(gx + 1, gy + 1, gz), P(gx, gy + 1, gz)], colors.left, edge, 1);
    poly(ctx, [P(gx, gy, gz + 1), P(gx + 1, gy, gz + 1), P(gx + 1, gy + 1, gz + 1), P(gx, gy + 1, gz + 1)], colors.top, edge, 1);
  }

  // Prisma em pixels de tela: (cx,cy) = centro do topo, a = meia-largura, h = altura lateral.
  function isoBox(ctx, cx, cy, a, h, colTop, colL, colR, edge) {
    const hh = a / 2;
    const top = [[cx, cy - hh], [cx + a, cy], [cx, cy + hh], [cx - a, cy]];
    const left = [[cx - a, cy], [cx, cy + hh], [cx, cy + hh + h], [cx - a, cy + h]];
    const right = [[cx, cy + hh], [cx + a, cy], [cx + a, cy + h], [cx, cy + hh + h]];
    poly(ctx, left, colL, edge, 1.5);
    poly(ctx, right, colR, edge, 1.5);
    poly(ctx, top, colTop, edge, 1.5);
  }

  // ---------- Texto ----------
  function wrap(ctx, text, maxW) {
    const out = [];
    for (const para of String(text).split('\n')) {
      let line = '';
      for (const w of para.split(/\s+/)) {
        const test = line ? line + ' ' + w : w;
        if (ctx.measureText(test).width > maxW && line) { out.push(line); line = w; } else line = test;
      }
      out.push(line);
    }
    return out;
  }

  const ptCache = new Map();
  // Título em "blocos": texto nativo em alta resolução (nítido em qualquer escala), com extrusão rígida em
  // degraus (efeito 3D de bloco) e contorno escuro. Cada texto é pré-desenhado uma vez e copiado 1:1.
  function pixelText(ctx, text, x, y, size, color, align) {
    const key = text + '|' + size + '|' + color;
    let e = ptCache.get(key);
    if (!e) {
      const depth = Math.max(2, Math.round(size / 11));
      const lw = Math.max(2, Math.round(size / 9));
      const ls = Math.round(size * 0.04);                    // espaçamento entre letras
      const pad = depth + lw + 2;
      const m = document.createElement('canvas').getContext('2d');
      m.font = `bold ${size}px ${MONO}`;
      const chars = Array.from(text);
      const widths = chars.map(c => m.measureText(c).width);
      const total = Math.ceil(widths.reduce((s, w) => s + w, 0) + ls * (chars.length - 1));
      const c = document.createElement('canvas');
      c.width = total + pad * 2; c.height = Math.ceil(size * 1.3) + pad * 2;
      const g = c.getContext('2d');
      g.font = m.font; g.textBaseline = 'top'; g.lineJoin = 'round'; g.lineWidth = lw;
      const run = (ox, oy, fn) => { let cx = pad + ox; chars.forEach((ch, i) => { fn(ch, cx, pad + oy); cx += widths[i] + ls; }); };
      const side = shade(color, 0.38);
      for (let d = depth; d >= 1; d--) {                      // extrusão, de trás para a frente
        g.strokeStyle = '#04070c'; run(d, d, (ch, px, py) => g.strokeText(ch, px, py));
        g.fillStyle = side; run(d, d, (ch, px, py) => g.fillText(ch, px, py));
      }
      g.strokeStyle = '#04070c'; run(0, 0, (ch, px, py) => g.strokeText(ch, px, py));
      g.fillStyle = color; run(0, 0, (ch, px, py) => g.fillText(ch, px, py));
      e = { c, pad, w: total };
      ptCache.set(key, e);
    }
    const dx = align === 'center' ? x - e.w / 2 : align === 'right' ? x - e.w : x;
    ctx.drawImage(e.c, Math.round(dx - e.pad), Math.round(y - e.pad));
    return e;
  }

  // Rótulo na face frontal-esquerda de um bloco isométrico (isoBox), alinhado ao plano da face.
  // (cx, cy) = centro do topo; a = meia-largura; h = altura lateral. Texto branco com contorno escuro.
  function isoFaceLabel(ctx, text, cx, cy, a, h, size) {
    const fx = cx - a / 2, fy = cy + a / 4 + h / 2;           // centro da face esquerda
    ctx.save();
    ctx.translate(fx, fy);
    ctx.transform(0.894, 0.447, 0, 1, 0, 0);                   // eixo x acompanha a aresta (1, 0,5)
    ctx.font = `bold ${size}px ${MONO}`;
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.lineJoin = 'round'; ctx.lineWidth = Math.max(3, size / 6);
    ctx.strokeStyle = '#04070c'; ctx.strokeText(text, 0, 1);
    ctx.fillStyle = '#ffffff'; ctx.fillText(text, 0, 1);
    ctx.restore();
  }

  function glowText(ctx, text, x, y, font, color, blur, align) {
    ctx.save();
    ctx.font = font; ctx.fillStyle = color; ctx.textAlign = align || 'left';
    ctx.shadowColor = color; ctx.shadowBlur = blur;
    ctx.fillText(text, x, y);
    ctx.restore();
  }

  // ---------- Fundo e UI ----------
  function drawBackground(ctx, t) {
    const W = ctx.canvas.width, H = ctx.canvas.height;
    const g = ctx.createLinearGradient(0, 0, 0, H);
    g.addColorStop(0, '#0d1117');
    g.addColorStop(1, '#161b22');
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, W, H);
    ctx.strokeStyle = 'rgba(88,166,255,.05)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (let x = 0; x <= W; x += 64) { ctx.moveTo(x + .5, 0); ctx.lineTo(x + .5, H); }
    const off = (t * 14) % 64;
    for (let y = -64; y <= H; y += 64) { ctx.moveTo(0, y + off + .5); ctx.lineTo(W, y + off + .5); }
    ctx.stroke();
    // bits de dados flutuando
    for (let i = 0; i < 26; i++) {
      const h = hash(i, 3);
      const x = h * W;
      const y = ((hash(i, 9) * H + t * (10 + h * 18)) % (H + 40)) - 20;
      ctx.fillStyle = `rgba(88,166,255,${0.06 + h * 0.1})`;
      ctx.fillRect(x, y, 6 + h * 8, 6 + h * 8);
    }
  }

  function drawPanel(ctx, x, y, w, h, o) {
    o = o || {};
    ctx.save();
    rr(ctx, x, y, w, h, o.radius == null ? 14 : o.radius);
    ctx.fillStyle = o.fill || 'rgba(22,27,34,.9)';
    ctx.fill();
    ctx.strokeStyle = o.stroke || 'rgba(88,166,255,.65)';
    ctx.lineWidth = o.lw || 2;
    if (o.glow) { ctx.shadowColor = o.stroke || CYAN; ctx.shadowBlur = o.glow; }
    ctx.stroke();
    ctx.restore();
  }

  function drawButton(ctx, label, x, y, w, h, o) {
    o = o || {};
    const en = o.enabled !== false;
    ctx.save();
    rr(ctx, x, y, w, h, 10);
    const g = ctx.createLinearGradient(0, y, 0, y + h);
    if (!en) { g.addColorStop(0, '#2a3442'); g.addColorStop(1, '#1d2631'); }
    else if (o.primary) { g.addColorStop(0, o.hover ? '#1f6feb' : '#1a5fcf'); g.addColorStop(1, o.hover ? '#1a5fcf' : '#164fb0'); }   // texto branco >= 4,5:1
    else { g.addColorStop(0, o.hover ? '#2b4f7e' : '#1f3b5f'); g.addColorStop(1, o.hover ? '#1f3e66' : '#162d4a'); }
    ctx.fillStyle = g;
    ctx.fill();
    ctx.strokeStyle = en ? CYAN : '#3a4757';
    ctx.lineWidth = 2;
    if (en && o.hover) { ctx.shadowColor = CYAN; ctx.shadowBlur = 14; }
    ctx.stroke();
    ctx.shadowBlur = 0;
    ctx.fillStyle = en ? '#ffffff' : '#6b7786';
    ctx.font = `bold ${o.fontSize || 22}px ${SANS}`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(label, x + w / 2, y + h / 2 + 1);
    ctx.restore();
  }

  // Transição digital: blocos que "ligam" da esquerda para a direita. p: 0 (limpo) -> 1 (coberto)
  function wipe(ctx, p) {
    const cols = 32, rows = 18, cw = 40, ch = 40;
    ctx.save();
    ctx.font = `bold 16px ${MONO}`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const th = (c / cols) * 0.6 + hash(c, r) * 0.4;
        const a = Math.max(0, Math.min(1, (p - th) * 6));
        if (a <= 0) continue;
        ctx.globalAlpha = a;
        ctx.fillStyle = '#050e1a';
        ctx.fillRect(c * cw, r * ch, cw, ch);
        ctx.strokeStyle = 'rgba(88,166,255,.45)';
        ctx.strokeRect(c * cw + .5, r * ch + .5, cw - 1, ch - 1);
        if (a < 0.95) {
          ctx.fillStyle = CYAN;
          ctx.fillText(hash(c + 5, r) > 0.5 ? '1' : '0', c * cw + cw / 2, r * ch + ch / 2);
        }
      }
    }
    ctx.restore();
  }

  // ---------- Logos e brasão procedural ----------
  const logos = { university: null, program: null };

  // Carrega as logos de config.institution. Falhas (404, bloqueio de file:///, arquivo ausente) deixam
  // a entrada nula e drawLogo desenha o brasão procedural. Chama callback ao terminar e devolve uma Promise.
  function loadLogos(config, callback) {
    const inst = (config || window.GAME_CONFIG).institution;
    logos.university = null; logos.program = null;
    const jobs = [['university', inst.logoUniversityUrl], ['program', inst.logoProgramUrl]].map(([k, url]) =>
      new Promise(resolve => {
        if (!url) return resolve();
        const im = new Image();
        im.onload = () => { if (im.naturalWidth > 0) logos[k] = im; resolve(); };
        im.onerror = () => resolve();
        im.src = url;
      }));
    return Promise.all(jobs).then(() => { if (typeof callback === 'function') callback({ ...logos }); return { ...logos }; });
  }

  function initials(s) {
    return s.split(/\s+/).filter(w => w.length > 2).map(w => w[0].toUpperCase()).join('').slice(0, 6) || '?';
  }

  function drawCrest(ctx, kind, x, y, w, h) {
    const inst = window.GAME_CONFIG.institution;
    const full = kind === 'university' ? inst.name : inst.department;
    const parts = full.split(' - ');
    const acr = parts.length > 1 ? (kind === 'university' ? parts[0] : parts[parts.length - 1]) : initials(full);
    const name = parts.length > 1
      ? (kind === 'university' ? parts.slice(1).join(' - ') : parts.slice(0, -1).join(' - '))
      : full;
    const sw = Math.min(w * 0.8, h * 0.6), sh = sw * 1.15, cx = x + w / 2;
    const top = y;
    const shield = [[cx - sw / 2, top], [cx + sw / 2, top], [cx + sw / 2, top + sh * 0.55], [cx, top + sh], [cx - sw / 2, top + sh * 0.55]];
    ctx.save();
    ctx.shadowColor = CYAN; ctx.shadowBlur = 16;
    poly(ctx, shield, '#0a192c', CYAN, 4);
    ctx.shadowBlur = 0;
    const inner = shield.map(p => [cx + (p[0] - cx) * 0.82, top + sh * 0.5 + (p[1] - top - sh * 0.5) * 0.82]);
    poly(ctx, inner, null, 'rgba(88,166,255,.4)', 1.5);
    isoBox(ctx, cx, top + sh * 0.2, sw * 0.16, sw * 0.12, '#58a6ff', '#1b5cb0', '#0f3d7a');
    ctx.restore();
    pixelText(ctx, acr.slice(0, 8), cx, top + sh * 0.42, Math.min(34, sw * 0.9 / Math.max(3, acr.length) * 1.6), '#eaf2fd', 'center');
    // nome da instituição/programa, em tipografia pixelada
    const perLine = Math.max(10, Math.floor(w / 10));
    const words = name.split(' ');
    const lines = [];
    let cur = '';
    words.forEach(wd => {
      if ((cur + ' ' + wd).trim().length > perLine && cur) { lines.push(cur); cur = wd; } else cur = (cur + ' ' + wd).trim();
    });
    lines.push(cur);
    lines.slice(0, 4).forEach((ln, i) => pixelText(ctx, ln, cx, top + sh + 10 + i * 20, 16, '#89b8f5', 'center'));
  }

  // Logo em um cartão plano (sem inclinação), de cantos arredondados, com sombra projetada, brilho azul e borda.
  // A proporção da imagem é sempre preservada. As duas logos usam a MESMA altura de cartão; a largura acompanha cada imagem
  // (e, se não couber na área, a logo é reduzida mantendo a proporção). Flutua de leve, como o resto da abertura.
  function drawLogo(ctx, kind, x, y, w, h) {
    const im = logos[kind];
    if (!im) { drawCrest(ctx, kind, x, y, w, h); return; }
    const m = 14, r = 20, CH = Math.round(h * 0.62);                     // margem interna, raio dos cantos, altura do cartão
    let ih = CH - 2 * m, iw = im.naturalWidth * ih / im.naturalHeight;
    if (iw + 2 * m > w) { iw = w - 2 * m; ih = im.naturalHeight * iw / im.naturalWidth; }
    const cw = iw + 2 * m, ch = ih + 2 * m;
    const bob = reduced ? 0 : Math.sin(Date.now() / 700 + (kind === 'university' ? 0 : 1.5)) * 3;
    const cx0 = x + (w - cw) / 2, cy0 = y + (h - ch) / 2 + bob;
    ctx.save();
    ctx.shadowColor = 'rgba(0,0,0,.5)'; ctx.shadowBlur = 26; ctx.shadowOffsetY = 12;     // sombra projetada
    const g = ctx.createLinearGradient(0, cy0, 0, cy0 + ch);
    g.addColorStop(0, '#ffffff'); g.addColorStop(1, '#e8f0fb');
    rr(ctx, cx0, cy0, cw, ch, r); ctx.fillStyle = g; ctx.fill();
    ctx.restore();
    ctx.save();                                                          // a logo, recortada dentro do cartão
    rr(ctx, cx0, cy0, cw, ch, r); ctx.clip();
    ctx.drawImage(im, cx0 + m, cy0 + m, iw, ih);
    const brilho = ctx.createLinearGradient(0, cy0, 0, cy0 + ch * 0.5);  // reflexo suave no topo
    brilho.addColorStop(0, 'rgba(255,255,255,.55)'); brilho.addColorStop(1, 'rgba(255,255,255,0)');
    ctx.fillStyle = brilho; ctx.fillRect(cx0, cy0, cw, ch * 0.5);
    ctx.restore();
    ctx.save();                                                          // borda azul com brilho
    ctx.shadowColor = 'rgba(88,166,255,.65)'; ctx.shadowBlur = 16;
    rr(ctx, cx0, cy0, cw, ch, r); ctx.strokeStyle = 'rgba(120,180,255,.95)'; ctx.lineWidth = 3; ctx.stroke();
    ctx.restore();
  }

  // ---------- Piso do campus ----------
  function drawFloor(ctx, t) {
    const NX = ISO.NX, NY = ISO.NY, th = 18;
    const A = project(0, NY, 0), B = project(NX, NY, 0), C = project(NX, 0, 0);
    poly(ctx, [A, B, [B[0], B[1] + th], [A[0], A[1] + th]], '#101c2b');
    poly(ctx, [B, C, [C[0], C[1] + th], [B[0], B[1] + th]], '#0a1420');
    ctx.strokeStyle = 'rgba(88,166,255,.55)';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(A[0], A[1] + th); ctx.lineTo(B[0], B[1] + th); ctx.lineTo(C[0], C[1] + th);
    ctx.stroke();

    for (let i = 0; i < NX; i++) {
      for (let j = 0; j < NY; j++) {
        const p0 = project(i, j, 0), p1 = project(i + 1, j, 0), p2 = project(i + 1, j + 1, 0), p3 = project(i, j + 1, 0);
        const h = hash(i, j);
        const kind = h < 0.13 ? 'pcb' : h < 0.24 ? 'acr' : 'metal';
        const cx = (p0[0] + p2[0]) / 2, cy = (p0[1] + p2[1]) / 2;
        if (kind === 'metal') {
          poly(ctx, [p0, p1, p2, p3], shade('#2a3748', 0.88 + h * 0.5), 'rgba(130,180,245,.14)', 1);
          poly(ctx, [p0, p1, [cx, cy]], 'rgba(255,255,255,.04)');
        } else if (kind === 'pcb') {
          poly(ctx, [p0, p1, p2, p3], '#0b1e36', 'rgba(120,168,230,.2)', 1);
          const a = [(p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2], b = [cx, cy], c = [(p2[0] + p3[0]) / 2, (p2[1] + p3[1]) / 2];
          const pulse = 0.5 + 0.5 * Math.sin((reduced ? 0 : Date.now()) * 0.003 + h * 6);   // circuitos pulsando levemente
          ctx.strokeStyle = `rgba(56,139,253,${0.4 + pulse * 0.4})`;
          ctx.lineWidth = 2;
          ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.lineTo(c[0], c[1]); ctx.stroke();
          ctx.fillStyle = '#1972e6';
          ctx.fillRect(cx - 3, cy - 2, 6, 4);
          const f = (t * 0.7 + h * 5) % 1;
          const pt = f < 0.5 ? [a[0] + (b[0] - a[0]) * f * 2, a[1] + (b[1] - a[1]) * f * 2]
            : [b[0] + (c[0] - b[0]) * (f - 0.5) * 2, b[1] + (c[1] - b[1]) * (f - 0.5) * 2];
          ctx.fillStyle = '#ecf3fd';
          ctx.fillRect(pt[0] - 2, pt[1] - 2, 4, 4);
        } else {
          poly(ctx, [p0, p1, p2, p3], '#122c4d', 'rgba(149,191,246,.35)', 1);
          poly(ctx, [p0, p1, p2, p3], 'rgba(93,158,242,.18)');
          poly(ctx, [p0, p1, [cx, cy]], 'rgba(204,224,251,.14)');
        }
      }
    }
    const T = project(0, 0, 0);
    ctx.strokeStyle = 'rgba(88,166,255,.7)';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(A[0], A[1]); ctx.lineTo(T[0], T[1]); ctx.lineTo(C[0], C[1]);
    ctx.stroke();
  }

  const RACK = { top: '#354c6a', left: '#1c2838', right: '#101a26' };
  const RACK_HI = { top: '#44628a', left: '#26374d', right: '#162334' };

  // Paredes de dados nas duas bordas do fundo: painéis translúcidos e racks de servidores (2 voxels).
  function drawRacks(ctx, t) {
    // painéis de vidro ao fundo (x = 0 e y = 0)
    ctx.save();
    ctx.globalAlpha = 0.22;
    cube(ctx, -0.12, 0, 0, 0.12, ISO.NY, 2.1, '#4a8be0');
    cube(ctx, 0, -0.12, 0, ISO.NX, 0.12, 2.1, '#4a8be0');
    ctx.restore();
    for (let k = 6; k <= ISO.NX - 1; k++) {
      [[0, k], [k, 0]].forEach(([gx, gy], side) => {
        if (gx + gy >= (side === 0 ? ISO.NY : ISO.NX)) return;     // dentro dos limites da sala
        drawVoxel(ctx, gx, gy, 0, RACK);
        drawVoxel(ctx, gx, gy, 1, RACK_HI);
        for (let r = 0; r < 6; r++) {
          const on = (Math.floor(t * 2 + r + k) % 3) !== 0;
          ctx.fillStyle = on ? (r % 2 ? '#58a6ff' : '#8fbcf6') : '#14396a';
          const lz = 0.12 + r * 0.16, off = 0.15 + (r % 2) * 0.35;
          // LEDs na face voltada para a sala (x+1 para a borda x=0; y+1 para a borda y=0)
          const p = side === 0 ? project(gx + 1, gy + off, lz) : project(gx + off, gy + 1, lz);
          ctx.fillRect(p[0] - 3, p[1] - 2, 6, 3);
        }
      });
    }
  }

  // Sala completa: piso, paredes de dados e racks.
  function drawRoom(ctx, t) {
    drawFloor(ctx, t);
    drawRacks(ctx, t);
  }

  // Faixa de dados (passarela) em perspectiva, da porta até o horizonte, visível pela eclusa aberta.
  function drawWalkway(ctx, bx, by, t, open) {
    const x0 = bx - 48, y0 = by - 124, w = 96, h = 124, hz = y0 + 34;   // hz = linha do horizonte
    ctx.save();
    ctx.beginPath(); ctx.rect(x0, y0, w, h); ctx.clip();
    ctx.globalAlpha = open;
    const sky = ctx.createLinearGradient(0, y0, 0, hz);
    sky.addColorStop(0, '#020810'); sky.addColorStop(1, '#081e3a');
    ctx.fillStyle = sky; ctx.fillRect(x0, y0, w, hz - y0);
    poly(ctx, [[bx - 5, hz], [bx + 5, hz], [bx + 48, by], [bx - 48, by]], '#071d3a');
    // bandas de ladrilhos que correm em direção ao jogador
    for (let i = 0; i < 7; i++) {
      const f = ((i + t * 1.2) % 7) / 7, g = f * f;
      const y = hz + (by - hz) * g, half = 5 + 43 * g;
      ctx.fillStyle = `rgba(88,166,255,${0.25 + 0.5 * g})`;
      ctx.fillRect(bx - half, y, half * 2, 2 + 3 * g);
    }
    ctx.strokeStyle = 'rgba(149,191,246,.7)'; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(bx - 5, hz); ctx.lineTo(bx - 48, by); ctx.moveTo(bx + 5, hz); ctx.lineTo(bx + 48, by); ctx.stroke();
    ctx.fillStyle = '#a6caf8'; ctx.fillRect(bx - 2, hz - 2, 4, 3);
    ctx.restore();
  }

  // ---------- Portas / eclusas ----------
  const DOOR_W = 120, DOOR_H = 136;

  function drawDoorBack(ctx, bx, by, t, open) {
    ctx.fillStyle = 'rgba(0,0,0,.35)';
    ctx.beginPath(); ctx.ellipse(bx + 6, by + 4, 72, 14, 0, 0, Math.PI * 2); ctx.fill();
    const x0 = bx - 48, y0 = by - 124, w = 96, h = 124;
    const g = ctx.createLinearGradient(0, y0, 0, by);
    g.addColorStop(0, '#02070d'); g.addColorStop(1, '#0b2444');
    ctx.fillStyle = g;
    ctx.fillRect(x0, y0, w, h);
    if (open > 0.02) drawWalkway(ctx, bx, by, t, open);
  }

  function drawDoorFront(ctx, bx, by, t, open, glow) {
    const x0 = bx - 48, y0 = by - 124, w = 96, h = 124;
    ctx.save();
    ctx.beginPath(); ctx.rect(x0, y0, w, h); ctx.clip();
    const off = open * (w / 2 + 2);
    const half = (x, wd) => {
      const g = ctx.createLinearGradient(x, y0, x + wd, by);
      g.addColorStop(0, '#1b5eb5'); g.addColorStop(1, '#0c305f');
      ctx.fillStyle = g; ctx.fillRect(x, y0, wd, h);
      ctx.fillStyle = 'rgba(130,180,245,.18)';
      for (let yy = y0 + ((t * 40) % 12) - 12; yy < by; yy += 12) ctx.fillRect(x, yy, wd, 2);
      ctx.strokeStyle = 'rgba(88,166,255,.85)'; ctx.lineWidth = 2;
      ctx.strokeRect(x + 1, y0 + 1, wd - 2, h - 2);
    };
    half(x0 - off, w / 2);
    half(bx + off, w / 2);
    ctx.restore();

    // moldura metálica com profundidade
    const fx = bx - DOOR_W / 2, fy = by - DOOR_H;
    const metal = ctx.createLinearGradient(fx, fy, fx + DOOR_W, fy);
    metal.addColorStop(0, '#5a6b82'); metal.addColorStop(0.5, '#8da0b8'); metal.addColorStop(1, '#4a596c');
    ctx.fillStyle = '#2c3746';
    poly(ctx, [[fx + DOOR_W, fy], [fx + DOOR_W + 12, fy - 6], [fx + DOOR_W + 12, by - 6], [fx + DOOR_W, by]], '#27313e');
    poly(ctx, [[fx, fy], [fx + DOOR_W, fy], [fx + DOOR_W + 12, fy - 6], [fx + 12, fy - 6]], '#a9bad0');
    ctx.fillStyle = metal;
    ctx.fillRect(fx, fy, DOOR_W, 12);
    ctx.fillRect(fx, fy, 12, DOOR_H);
    ctx.fillRect(fx + DOOR_W - 12, fy, 12, DOOR_H);
    ctx.fillStyle = '#1b2430';
    ctx.fillRect(fx, by - 6, DOOR_W, 6);

    // feixe neon
    ctx.save();
    ctx.strokeStyle = glow > 0.05 ? '#a6caf8' : CYAN;
    ctx.lineWidth = 3;
    ctx.shadowColor = CYAN;
    ctx.shadowBlur = 8 + glow * 18;
    ctx.strokeRect(x0 - 1.5, y0 - 1.5, w + 3, h + 3);
    ctx.restore();
    for (let i = 0; i < 3; i++) {
      ctx.fillStyle = (Math.floor(t * 3) + i) % 3 === 0 ? '#ffffff' : '#257beb';
      ctx.fillRect(bx - 14 + i * 10, fy + 4, 6, 4);
    }
    // zona de ativação no chão
    if (glow > 0.02) {
      ctx.save();
      ctx.globalAlpha = 0.25 + glow * 0.35;
      ctx.fillStyle = CYAN;
      ctx.beginPath(); ctx.ellipse(bx, by + 40, 70, 22, 0, 0, Math.PI * 2); ctx.fill();
      ctx.restore();
    }
  }

  // Display holográfico cúbico com a letra da alternativa.
  function drawHolo(ctx, bx, by, letter, t, glow) {
    const e = 20;
    const cy = by - DOOR_H - 34 + Math.sin(t * 2 + bx * 0.02) * 3;
    ctx.save();
    const beam = ctx.createLinearGradient(0, cy + e + 10, 0, by - DOOR_H);
    beam.addColorStop(0, 'rgba(88,166,255,.35)'); beam.addColorStop(1, 'rgba(88,166,255,0)');
    poly(ctx, [[bx - 6, cy + e + 8], [bx + 6, cy + e + 8], [bx + 28, by - DOOR_H], [bx - 28, by - DOOR_H]], beam);
    ctx.globalAlpha = 0.55 + glow * 0.35;
    ctx.shadowColor = CYAN; ctx.shadowBlur = 10 + glow * 12;
    isoBox(ctx, bx, cy, e, e, 'rgba(167,202,248,.55)', 'rgba(53,130,230,.45)', 'rgba(20,85,170,.55)', CYAN);
    ctx.restore();
    glowText(ctx, letter, bx, cy + e * 0.95, `bold 26px ${MONO}`, '#f3f8fe', 10, 'center');
  }

  // Distribui `count` portas (2 a 4) equidistantes e centralizadas na linha de portas.
  // Cada item traz a posição (bx, by), a posição no grid (d = x - y), a área de clique (rect, em pixels)
  // e a zona de colisão/ativação do avatar (zone, em coordenadas de grid: d e s = x + y).
  function layoutDoors(count) {
    const n = Math.max(2, Math.min(4, count | 0));
    const sp = n === 2 ? 250 : n === 3 ? 190 : 150;
    return Array.from({ length: n }, (_, i) => {
      const d = (ISO.cx + (i - (n - 1) / 2) * sp - ISO.OX) / (TW / 2);   // centralizadas na tela
      const [bx, by] = project((ISO.doorS + d) / 2, (ISO.doorS - d) / 2, 0);
      return {
        index: i, d, bx, by,
        rect: { x: bx - DOOR_W / 2, y: by - 190, w: DOOR_W + 12, h: 190 },
        zone: { d0: d - 1.15, d1: d + 1.15, s0: ISO.front, s1: ISO.front + 2.4 }
      };
    });
  }

  // Desenha todas as portas (fundo, folhas, moldura e display holográfico). doorsData[i] = { letter, open, glow }.
  function drawDoors(ctx, count, doorsData) {
    const t = reduced ? 0 : Date.now() / 1000;
    const layout = layoutDoors(count);
    layout.forEach((dr, i) => { drawDoorBack(ctx, dr.bx, dr.by, t, (doorsData[i] || {}).open || 0); });
    layout.forEach((dr, i) => {
      const dd = doorsData[i] || {};
      drawDoorFront(ctx, dr.bx, dr.by, t, dd.open || 0, dd.glow || 0);
      drawHolo(ctx, dr.bx, dr.by, dd.letter || String.fromCharCode(65 + i), t, dd.glow || 0);
    });
    return layout;
  }

  // Véu escuro translúcido sobre todo o canvas (entrada/saída de fase).
  function drawFade(ctx, alpha) {
    ctx.save();
    ctx.fillStyle = `rgba(0,0,0,${Math.max(0, Math.min(1, alpha))})`;
    ctx.fillRect(0, 0, ctx.canvas.width, ctx.canvas.height);
    ctx.restore();
  }

  class IsoRenderer {
    constructor() {
      this.tileWidth = TW;
      this.tileHeight = TH;
      this.originX = ISO.OX;
      this.originY = ISO.OY;
      this.ISO = ISO; this.SANS = SANS; this.MONO = MONO; this.CYAN = CYAN;
      this.DOOR_W = DOOR_W; this.DOOR_H = DOOR_H;
    }
    toScreen(gridX, gridY, gridZ) { return project(gridX, gridY, gridZ); }
    setReducedMotion(v) { reduced = !!v; }
    drawVoxel(ctx, gridX, gridY, gridZ, colors) { return drawVoxel(ctx, gridX, gridY, gridZ, colors); }
    drawRoom(ctx, t) { return drawRoom(ctx, t); }
    drawDoors(ctx, count, doorsData) { return drawDoors(ctx, count, doorsData || []); }
    drawFade(ctx, alpha) { return drawFade(ctx, alpha); }
    loadLogos(config, callback) { return loadLogos(config, callback); }
  }
  // Utilitários de desenho e UI usados pelas telas e pelos avatares.
  Object.assign(IsoRenderer.prototype, {
    project, shade, hash, poly, rr, cube, isoBox, isoFaceLabel, wrap, pixelText, glowText,
    drawBackground, drawPanel, drawButton, wipe, drawLogo,
    drawFloor, drawRacks, drawWalkway, layoutDoors, drawDoorBack, drawDoorFront, drawHolo
  });

  window.IsoRendererClass = IsoRenderer;
  window.IsoRenderer = new IsoRenderer();
  window.Renderer = window.IsoRenderer;   // alias usado pelos demais módulos
})();
