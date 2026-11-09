// Projeção isométrica 2.5D, cenário tecnológico, portas, logos (com fallback) e utilitários de UI.
(function () {
  'use strict';

  // Sala alinhada à base (vista frontal, 0°): a parede do fundo é horizontal e o chão é um retângulo. Coordenadas da sala:
  // x = lateral (0 a NX, da esquerda para a direita) e y = profundidade (0 na base da parede das portas, crescendo em
  // direção ao jogador). A sala ocupa a área à esquerda da barra lateral das alternativas (largura SW).
  // OY é a linha da base da parede (onde ficam as portas); o chão vai até o rodapé.
  const ISO = { U: 47, V: 47, VZ: 47, OX: 0, OY: 412, NX: 20, NY: 5.2, SW: 940, cx: 470 };
  const TW = ISO.U, TH = ISO.V;
  let reduced = false;   // movimento reduzido: pulsos e flutuações do cenário ficam estáticos
  const SANS = '"Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif';
  const MONO = '"Courier New", Courier, monospace';
  const CYAN = '#58a6ff';

  // screenX = OX + x * U ;  screenY = OY + y * V - z * VZ
  function project(x, y, z) {
    return [ISO.OX + x * ISO.U, ISO.OY + y * ISO.V - (z || 0) * ISO.VZ];
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

  // ---------- Piso do campus (retângulo alinhado à base) ----------
  function drawFloor(ctx, t) {
    const x0 = ISO.OX, w = ISO.NX * ISO.U, y0 = ISO.OY, rows = 5, rh = ISO.NY * ISO.V / rows, th = 18, yF = y0 + rows * rh;
    ctx.fillStyle = '#0a1420'; ctx.fillRect(x0, yF, w, th);                // espessura da borda frontal
    ctx.fillStyle = '#101c2b'; ctx.fillRect(x0, yF, w, th * 0.55);
    ctx.strokeStyle = 'rgba(88,166,255,.55)'; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(x0, yF + th); ctx.lineTo(x0 + w, yF + th); ctx.stroke();

    for (let i = 0; i < ISO.NX; i++) {
      for (let j = 0; j < rows; j++) {
        const ax = x0 + i * ISO.U, ay = y0 + j * rh;
        const p0 = [ax, ay], p1 = [ax + ISO.U, ay], p2 = [ax + ISO.U, ay + rh], p3 = [ax, ay + rh];
        const h = hash(i, j);
        const kind = h < 0.13 ? 'pcb' : h < 0.24 ? 'acr' : 'metal';
        const cx = ax + ISO.U / 2, cy = ay + rh / 2;
        if (kind === 'metal') {
          poly(ctx, [p0, p1, p2, p3], shade('#2a3748', 0.88 + h * 0.5), 'rgba(130,180,245,.14)', 1);
          poly(ctx, [p0, p1, [cx, cy]], 'rgba(255,255,255,.04)');
        } else if (kind === 'pcb') {
          poly(ctx, [p0, p1, p2, p3], '#0b1e36', 'rgba(120,168,230,.2)', 1);
          const a = [ax, cy], b = [cx, cy], c = [cx, ay + rh];
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
    const sh = ctx.createLinearGradient(0, y0, 0, yF);                      // o fundo do chão fica mais escuro (profundidade)
    sh.addColorStop(0, 'rgba(4,10,20,.55)'); sh.addColorStop(0.45, 'rgba(4,10,20,.12)'); sh.addColorStop(1, 'rgba(4,10,20,0)');
    ctx.fillStyle = sh; ctx.fillRect(x0, y0, w, yF - y0);
    ctx.strokeStyle = 'rgba(88,166,255,.7)'; ctx.lineWidth = 2;             // junção da parede com o chão
    ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x0 + w, y0); ctx.stroke();
  }

  // Parede do fundo: painel de dados com racks de servidores (LEDs piscando), faixa de luz e rodapé. Os racks desviam das portas.
  function drawWall(ctx, t, doorXs) {
    const x0 = ISO.OX, w = ISO.NX * ISO.U, y0 = ISO.OY;
    const g = ctx.createLinearGradient(0, 0, 0, y0);
    g.addColorStop(0, '#07111f'); g.addColorStop(0.55, '#0d2140'); g.addColorStop(1, '#14305a');
    ctx.fillStyle = g; ctx.fillRect(x0, 0, w, y0);
    ctx.fillStyle = 'rgba(88,166,255,.05)';                                   // colunas de painéis
    for (let x = x0; x < x0 + w; x += ISO.U * 2) ctx.fillRect(x, 0, 2, y0);
    ctx.fillStyle = 'rgba(88,166,255,.5)'; ctx.fillRect(x0, 22, w, 2);          // faixa de luz no alto
    ctx.fillStyle = 'rgba(88,166,255,.12)'; ctx.fillRect(x0, 24, w, 26);

    // monitores de dados na parte alta da parede (gráficos de barras animados), visíveis através do cabeçalho translúcido
    for (let px = x0 + 36, k = 0; px + 150 < x0 + w; px += 200, k++) {
      const py = 64, pw = 150, ph = 70;
      ctx.fillStyle = 'rgba(8,26,52,.7)'; ctx.fillRect(px, py, pw, ph);
      ctx.strokeStyle = 'rgba(88,166,255,.4)'; ctx.lineWidth = 1.5; ctx.strokeRect(px + 0.75, py + 0.75, pw - 1.5, ph - 1.5);
      ctx.fillStyle = 'rgba(88,166,255,.35)'; ctx.fillRect(px + 10, py + 9, 44, 3); ctx.fillRect(px + 10, py + 16, 28, 2);
      for (let b = 0; b < 12; b++) {
        const hh = 8 + (0.55 + 0.45 * Math.sin((reduced ? 0 : t) * 1.4 + b * 0.9 + k * 2.1)) * 34 * (0.5 + hash(k, b));
        ctx.fillStyle = b % 4 === 0 ? 'rgba(143,188,246,.75)' : 'rgba(56,139,253,.6)';
        ctx.fillRect(px + 12 + b * 10.5, py + ph - 8 - hh, 6, hh);
      }
    }
    const rw = 70, gapX = 94, rh = 150;
    for (let rx = x0 + 18, k = 0; rx + rw < x0 + w; rx += gapX, k++) {
      const cx = rx + rw / 2;
      if ((doorXs || []).some(d => Math.abs(d - cx) < DOOR_W / 2 + rw / 2 + 16)) continue;     // não esconde as portas
      const top = y0 - rh;
      const body = ctx.createLinearGradient(rx, 0, rx + rw, 0);
      body.addColorStop(0, '#142238'); body.addColorStop(0.5, '#1c2f4c'); body.addColorStop(1, '#101c2e');
      ctx.fillStyle = body; ctx.fillRect(rx, top, rw, rh);
      ctx.strokeStyle = 'rgba(88,166,255,.4)'; ctx.lineWidth = 1.5; ctx.strokeRect(rx + 0.75, top + 0.75, rw - 1.5, rh - 1.5);
      ctx.fillStyle = 'rgba(88,166,255,.35)'; ctx.fillRect(rx, top, rw, 3);
      for (let r = 0; r < 7; r++) {
        const yy = top + 14 + r * 19;
        ctx.fillStyle = 'rgba(0,0,0,.35)'; ctx.fillRect(rx + 8, yy, rw - 16, 11);          // gaveta
        for (let l = 0; l < 3; l++) {
          const on = (Math.floor((reduced ? 0 : t) * 2 + r + k + l) % 3) !== 0;
          ctx.fillStyle = on ? (l % 2 ? '#58a6ff' : '#8fbcf6') : '#14396a';
          ctx.fillRect(rx + 12 + l * 9, yy + 4, 5, 3);
        }
      }
    }
    ctx.fillStyle = '#16263d'; ctx.fillRect(x0, y0 - 9, w, 9);                   // rodapé da parede
    ctx.fillStyle = 'rgba(88,166,255,.35)'; ctx.fillRect(x0, y0 - 9, w, 2);
  }

  // Sala completa: parede do fundo e piso. doorXs = posições (em pixels) das portas, para os racks desviarem delas.
  function drawRoom(ctx, t, doorXs) {
    drawWall(ctx, t, doorXs);
    drawFloor(ctx, t);
    const v = ctx.createLinearGradient(0, 0, ISO.SW, 0);                         // vinheta lateral discreta
    v.addColorStop(0, 'rgba(2,6,12,.45)'); v.addColorStop(0.08, 'rgba(2,6,12,0)'); v.addColorStop(0.92, 'rgba(2,6,12,0)'); v.addColorStop(1, 'rgba(2,6,12,.35)');
    ctx.fillStyle = v; ctx.fillRect(0, 0, ISO.SW, ISO.OY + ISO.NY * ISO.V + 18);
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

  // Distribui `count` portas (2 a 4) equidistantes e centralizadas na parede do fundo (área da sala).
  // Cada item traz a posição (bx, by) e gx (lateral na sala), a área de clique (rect, em pixels) e a zona de ativação do
  // avatar (zone: faixa lateral x0..x1 e profundidade máxima y1, em coordenadas da sala).
  function layoutDoors(count) {
    const n = Math.max(2, Math.min(4, count | 0));
    const sp = n === 2 ? 250 : n === 3 ? 190 : 150;
    return Array.from({ length: n }, (_, i) => {
      const bx = ISO.cx + (i - (n - 1) / 2) * sp, by = ISO.OY, gx = (bx - ISO.OX) / ISO.U;
      return {
        index: i, gx, bx, by,
        rect: { x: bx - DOOR_W / 2, y: by - 190, w: DOOR_W + 12, h: 190 },
        zone: { x0: gx - 1.35, x1: gx + 1.35, y1: 1.5 }
      };
    });
  }

  // Caixa de dica: um cubo com "?" que fica na frente da sala, oposta às portas. (bx, by) = pé da caixa; glow 0..1 = proximidade.
  function drawHintBox(ctx, bx, by, t, glow) {
    const a = 32, h = 46, bob = reduced ? 0 : Math.sin(t * 2.2) * 3;
    const cy = by - h - a / 2;                                              // centro da face de cima
    ctx.save();
    ctx.fillStyle = 'rgba(0,0,0,.4)';
    ctx.beginPath(); ctx.ellipse(bx, by + 4, a * 1.15, 12, 0, 0, Math.PI * 2); ctx.fill();
    if (glow > 0.02) {                                                      // zona de ativação no chão
      ctx.globalAlpha = 0.2 + glow * 0.35; ctx.fillStyle = '#f2c230';
      ctx.beginPath(); ctx.ellipse(bx, by + 6, a * 1.9, 20, 0, 0, Math.PI * 2); ctx.fill();
      ctx.globalAlpha = 1;
    }
    ctx.shadowColor = '#f2c230'; ctx.shadowBlur = 8 + glow * 18;
    isoBox(ctx, bx, cy, a, h, '#2b6fd1', '#1b4a96', '#10346b', glow > 0.05 ? '#ffe58a' : '#f2c230');
    ctx.restore();
    isoFaceLabel(ctx, '?', bx, cy, a, h, 34);                               // "?" na face da esquerda
    const oy = cy - 34 + bob;                                               // medalhão dourado flutuando sobre a caixa
    ctx.save();
    ctx.shadowColor = '#f2c230'; ctx.shadowBlur = 12 + glow * 12;
    ctx.beginPath(); ctx.arc(bx, oy, 15, 0, Math.PI * 2);
    const g = ctx.createLinearGradient(bx - 15, oy - 15, bx + 15, oy + 15);
    g.addColorStop(0, '#ffe58a'); g.addColorStop(1, '#d9a926');
    ctx.fillStyle = g; ctx.fill(); ctx.lineWidth = 2.5; ctx.strokeStyle = '#a97d14'; ctx.stroke();
    ctx.restore();
    ctx.font = `bold 20px ${MONO}`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillStyle = '#5a3b00'; ctx.fillText('?', bx, oy + 1);
    ctx.textBaseline = 'alphabetic';
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
    drawRoom(ctx, t, doorXs) { return drawRoom(ctx, t, doorXs); }
    drawDoors(ctx, count, doorsData) { return drawDoors(ctx, count, doorsData || []); }
    drawFade(ctx, alpha) { return drawFade(ctx, alpha); }
    loadLogos(config, callback) { return loadLogos(config, callback); }
  }
  // Utilitários de desenho e UI usados pelas telas e pelos avatares.
  Object.assign(IsoRenderer.prototype, {
    project, shade, hash, poly, rr, cube, isoBox, isoFaceLabel, wrap, pixelText, glowText,
    drawBackground, drawPanel, drawButton, wipe, drawLogo,
    drawFloor, drawWall, drawWalkway, layoutDoors, drawDoorBack, drawDoorFront, drawHolo, drawHintBox
  });

  window.IsoRendererClass = IsoRenderer;
  window.IsoRenderer = new IsoRenderer();
  window.Renderer = window.IsoRenderer;   // alias usado pelos demais módulos
})();
