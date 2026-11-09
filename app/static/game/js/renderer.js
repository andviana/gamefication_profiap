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

  // ---------- Ambientes (um por fase) ----------
  // O jogo alterna os ambientes a cada grupo de perguntas. O primeiro é o centro de dados; os outros quatro são administrativos.
  const ENVIRONMENTS = ['datacenter', 'escritorio', 'sala', 'laboratorio', 'biblioteca'];
  const ENV_INFO = {
    datacenter: { nome: 'Centro de dados', accent: '#58a6ff' },
    escritorio: { nome: 'Escritório', accent: '#4cc3e0' },
    sala: { nome: 'Sala de aula', accent: '#f2b84b' },
    laboratorio: { nome: 'Laboratório', accent: '#5be3b0' },
    biblioteca: { nome: 'Biblioteca', accent: '#d9a066' }
  };
  const envOf = i => ENVIRONMENTS[((i % ENVIRONMENTS.length) + ENVIRONMENTS.length) % ENVIRONMENTS.length];
  const livre = (x, half, doorXs) => !(doorXs || []).some(d => Math.abs(d - x) < DOOR_W / 2 + half + 12);   // não esconde as portas
  const circ = (ctx, x, y, r, fill) => { ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fillStyle = fill; ctx.fill(); };

  // Pisos dos ambientes novos (o do centro de dados é o drawFloor acima): carpete, tábuas, azulejo e parquet.
  function drawFloorEnv(ctx, t, env) {
    const x0 = ISO.OX, w = ISO.NX * ISO.U, y0 = ISO.OY, rows = 5, rh = ISO.NY * ISO.V / rows, th = 18, yF = y0 + rows * rh;
    ctx.fillStyle = { escritorio: '#18233a', sala: '#33210f', laboratorio: '#22394a', biblioteca: '#2e1d10' }[env] || '#101c2b';
    ctx.fillRect(x0, yF, w, th);
    ctx.strokeStyle = 'rgba(255,255,255,.28)'; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(x0, yF + th); ctx.lineTo(x0 + w, yF + th); ctx.stroke();
    for (let j = 0; j < rows; j++) {
      const ay = y0 + j * rh;
      if (env === 'escritorio') {                                              // carpete em quadrados
        for (let i = 0; i < ISO.NX; i++) {
          const ax = x0 + i * ISO.U, h = hash(i, j);
          ctx.fillStyle = shade('#3a4f6c', 0.84 + h * 0.3); ctx.fillRect(ax, ay, ISO.U, rh);
          ctx.strokeStyle = 'rgba(0,0,0,.3)'; ctx.lineWidth = 1; ctx.strokeRect(ax + 0.5, ay + 0.5, ISO.U - 1, rh - 1);
          if ((i + j) % 2 === 0) { ctx.fillStyle = 'rgba(255,255,255,.04)'; ctx.fillRect(ax + 5, ay + 5, ISO.U - 10, rh - 10); }
        }
        if (j === 2) { ctx.fillStyle = 'rgba(76,195,224,.14)'; ctx.fillRect(x0, ay + rh * 0.35, w, rh * 0.3); }   // faixa de corredor
      } else if (env === 'sala') {                                             // tábuas de madeira
        let x = x0 - hash(j, 1) * ISO.U * 3;
        for (let k = 0; x < x0 + w; k++) {
          const len = ISO.U * (3 + Math.floor(hash(j, k + 5) * 4)), h = hash(j + 9, k);
          ctx.fillStyle = shade('#6b4526', 0.78 + h * 0.36); ctx.fillRect(Math.max(x, x0), ay, Math.min(len, x0 + w - x) + (x < x0 ? x - x0 : 0), rh);
          ctx.fillStyle = 'rgba(0,0,0,.35)'; ctx.fillRect(x, ay, 2, rh);
          ctx.fillStyle = 'rgba(255,230,190,.05)'; ctx.fillRect(Math.max(x, x0), ay + 3, len, 3);
          x += len;
        }
        ctx.fillStyle = 'rgba(0,0,0,.38)'; ctx.fillRect(x0, ay + rh - 2, w, 2);
      } else if (env === 'laboratorio') {                                      // azulejo grande e brilhante
        for (let i = 0; i < ISO.NX; i += 2) {
          const ax = x0 + i * ISO.U, h = hash(i, j);
          ctx.fillStyle = shade('#46687f', 0.86 + h * 0.24); ctx.fillRect(ax, ay, ISO.U * 2, rh);
          ctx.strokeStyle = 'rgba(214,238,252,.42)'; ctx.lineWidth = 2; ctx.strokeRect(ax + 1, ay + 1, ISO.U * 2 - 2, rh - 2);
          poly(ctx, [[ax + 10, ay + rh - 4], [ax + 34, ay + 4], [ax + 46, ay + 4], [ax + 22, ay + rh - 4]], 'rgba(255,255,255,.07)');
        }
      } else {                                                                 // parquet
        for (let i = 0; i < ISO.NX; i++) {
          const ax = x0 + i * ISO.U, h = hash(i, j), horiz = (i + j) % 2 === 0;
          for (let k = 0; k < 3; k++) {
            ctx.fillStyle = shade('#76502d', 0.74 + hash(i * 3 + k, j) * 0.4);
            if (horiz) ctx.fillRect(ax, ay + k * rh / 3, ISO.U, rh / 3 - 1); else ctx.fillRect(ax + k * ISO.U / 3, ay, ISO.U / 3 - 1, rh);
          }
          ctx.fillStyle = 'rgba(0,0,0,.25)'; ctx.fillRect(ax, ay, 1, rh);
          void h;
        }
      }
    }
    const sh = ctx.createLinearGradient(0, y0, 0, yF);
    sh.addColorStop(0, 'rgba(4,10,20,.5)'); sh.addColorStop(0.45, 'rgba(4,10,20,.1)'); sh.addColorStop(1, 'rgba(4,10,20,0)');
    ctx.fillStyle = sh; ctx.fillRect(x0, y0, w, yF - y0);
    ctx.strokeStyle = 'rgba(255,255,255,.35)'; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x0 + w, y0); ctx.stroke();
  }

  // Escritório: janelões com a cidade à noite, luminárias no teto e móveis de escritório (que desviam das portas).
  function wallOffice(ctx, t, doorXs) {
    const w = ISO.NX * ISO.U, y0 = ISO.OY;
    const g = ctx.createLinearGradient(0, 0, 0, y0); g.addColorStop(0, '#1b2a42'); g.addColorStop(1, '#2d4262');
    ctx.fillStyle = g; ctx.fillRect(0, 0, w, y0);
    const sky = ctx.createLinearGradient(0, 96, 0, 300); sky.addColorStop(0, '#08142b'); sky.addColorStop(1, '#1d3d6b');
    ctx.fillStyle = sky; ctx.fillRect(0, 96, w, 204);
    for (let b = 0, x = 0; x < w; b++, x += 38) {                                        // prédios ao fundo
      const bh = 50 + hash(b, 3) * 110;
      ctx.fillStyle = '#0b1a33'; ctx.fillRect(x, 300 - bh, 36, bh);
      for (let r = 0; r < Math.floor(bh / 14); r++) for (let c = 0; c < 2; c++) if (hash(b * 7 + r, c) < 0.34) { ctx.fillStyle = 'rgba(255,212,120,.8)'; ctx.fillRect(x + 6 + c * 14, 300 - bh + 6 + r * 14, 8, 6); }
    }
    ctx.fillStyle = '#18243b'; for (let x = 0; x <= w; x += 94) ctx.fillRect(x - 2, 92, 4, 212);   // montantes
    ctx.fillStyle = '#34496b'; ctx.fillRect(0, 92, w, 6); ctx.fillRect(0, 298, w, 8);
    for (let x = 30; x < w; x += 140) { ctx.fillStyle = 'rgba(255,255,255,.55)'; ctx.fillRect(x, 20, 72, 6); ctx.fillStyle = 'rgba(255,255,255,.08)'; ctx.fillRect(x - 8, 26, 88, 40); }
    ctx.fillStyle = '#18253b'; ctx.fillRect(0, y0 - 34, w, 34); ctx.fillStyle = 'rgba(76,195,224,.4)'; ctx.fillRect(0, y0 - 34, w, 2);
    for (let k = 0, x = 62; x < w - 40; x += 150, k++) {
      if (!livre(x, 52, doorXs)) continue;
      const kind = k % 3;
      if (kind === 0) {                                                                  // planta
        poly(ctx, [[x - 18, y0 - 34], [x + 18, y0 - 34], [x + 13, y0 - 4], [x - 13, y0 - 4]], '#6b4330');
        [[-14, -66], [0, -86], [14, -62], [-6, -54], [8, -76]].forEach(([dx, dy], q) => { ctx.save(); ctx.translate(x + dx, y0 + dy); ctx.rotate((q - 2) * 0.4); ctx.fillStyle = q % 2 ? '#2f9a62' : '#23805a'; ctx.beginPath(); ctx.ellipse(0, 0, 8, 22, 0, 0, Math.PI * 2); ctx.fill(); ctx.restore(); });
      } else if (kind === 1) {                                                           // arquivo
        ctx.fillStyle = '#8091a8'; ctx.fillRect(x - 30, y0 - 104, 60, 100); ctx.fillStyle = '#6a7b92';
        for (let d = 0; d < 3; d++) { ctx.fillRect(x - 27, y0 - 100 + d * 32, 54, 29); ctx.fillStyle = '#cfd8e3'; ctx.fillRect(x - 10, y0 - 88 + d * 32, 20, 4); ctx.fillStyle = '#6a7b92'; }
      } else {                                                                           // mesa com monitor
        ctx.fillStyle = '#8a6a47'; ctx.fillRect(x - 52, y0 - 50, 104, 8); ctx.fillRect(x - 46, y0 - 42, 6, 38); ctx.fillRect(x + 40, y0 - 42, 6, 38);
        ctx.fillStyle = '#10192a'; ctx.fillRect(x - 24, y0 - 92, 48, 34); ctx.fillStyle = 'rgba(88,166,255,.85)'; ctx.fillRect(x - 21, y0 - 89, 42, 28);
        ctx.fillStyle = 'rgba(255,255,255,.7)'; for (let l = 0; l < 3; l++) ctx.fillRect(x - 17, y0 - 84 + l * 7, 14 + l * 5, 3);
        ctx.fillStyle = '#10192a'; ctx.fillRect(x - 4, y0 - 58, 8, 8);
      }
    }
  }

  // Sala de aula: lousa verde com giz, relógio, carteiras, globo e estante.
  function wallClass(ctx, t, doorXs) {
    const w = ISO.NX * ISO.U, y0 = ISO.OY;
    const g = ctx.createLinearGradient(0, 0, 0, y0); g.addColorStop(0, '#26403f'); g.addColorStop(1, '#3a5a56');
    ctx.fillStyle = g; ctx.fillRect(0, 0, w, y0);
    ctx.fillStyle = '#6e4a2c'; ctx.fillRect(56, 96, w - 112, 184);                          // moldura da lousa
    const bd = ctx.createLinearGradient(0, 104, 0, 272); bd.addColorStop(0, '#1d4a39'); bd.addColorStop(1, '#16382c');
    ctx.fillStyle = bd; ctx.fillRect(64, 104, w - 128, 168);
    ctx.fillStyle = 'rgba(255,255,255,.07)'; ctx.fillRect(64, 104, w - 128, 22);
    ctx.fillStyle = 'rgba(245,250,245,.62)'; ctx.font = 'bold 26px "Courier New", monospace'; ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic';
    ['a² + b² = c²', 'E = m·c²', '∑ n = n(n+1)/2', 'π ≈ 3,14159', 'f(x) = ax + b'].forEach((tx, i) => ctx.fillText(tx, 96 + (i % 2) * 400 + (i > 3 ? 120 : 0), 150 + Math.floor(i / 2) * 50));
    ctx.fillStyle = '#8a6038'; ctx.fillRect(56, 276, w - 112, 8);
    [[120, '#ffffff'], [150, '#f2c230'], [178, '#ff8fa3']].forEach(([x, c]) => { ctx.fillStyle = c; ctx.fillRect(x, 270, 18, 6); });
    circ(ctx, w - 70, 56, 24, '#e9eef3'); ctx.strokeStyle = '#4a3220'; ctx.lineWidth = 4; ctx.beginPath(); ctx.arc(w - 70, 56, 24, 0, Math.PI * 2); ctx.stroke();
    const ang = (reduced ? 0 : t) * 0.4;
    ctx.strokeStyle = '#1a2a3a'; ctx.lineWidth = 3; ctx.beginPath(); ctx.moveTo(w - 70, 56); ctx.lineTo(w - 70 + Math.cos(ang) * 16, 56 + Math.sin(ang) * 16); ctx.moveTo(w - 70, 56); ctx.lineTo(w - 70, 42); ctx.stroke();
    ctx.fillStyle = '#2a3c3a'; ctx.fillRect(0, y0 - 34, w, 34); ctx.fillStyle = '#7a5532'; ctx.fillRect(0, y0 - 36, w, 4);
    for (let k = 0, x = 62; x < w - 40; x += 150, k++) {
      if (!livre(x, 50, doorXs)) continue;
      if (k % 3 === 1) {                                                                 // globo
        ctx.fillStyle = '#6a4a2a'; ctx.fillRect(x - 3, y0 - 36, 6, 30); ctx.fillRect(x - 18, y0 - 8, 36, 5);
        circ(ctx, x, y0 - 62, 26, '#2f6f9f'); circ(ctx, x - 8, y0 - 66, 10, '#3f9a5a'); circ(ctx, x + 10, y0 - 54, 8, '#3f9a5a');
        ctx.strokeStyle = '#c9a050'; ctx.lineWidth = 3; ctx.beginPath(); ctx.arc(x, y0 - 62, 29, Math.PI * 0.7, Math.PI * 1.9); ctx.stroke();
      } else {                                                                           // carteira
        ctx.fillStyle = '#b98b52'; ctx.fillRect(x - 36, y0 - 52, 72, 8); ctx.fillStyle = '#4a5666'; ctx.fillRect(x - 32, y0 - 44, 4, 40); ctx.fillRect(x + 28, y0 - 44, 4, 40);
        ctx.fillStyle = '#e8edf2'; ctx.fillRect(x - 22, y0 - 62, 20, 10); ctx.fillStyle = '#d25f5f'; ctx.fillRect(x + 4, y0 - 60, 14, 8);
      }
    }
  }

  // Laboratório: parede de azulejo, prateleiras com vidrarias borbulhantes, monitor de gráficos e bancadas.
  function wallLab(ctx, t, doorXs) {
    const w = ISO.NX * ISO.U, y0 = ISO.OY;
    const g = ctx.createLinearGradient(0, 0, 0, y0); g.addColorStop(0, '#1f3f50'); g.addColorStop(1, '#335f76');
    ctx.fillStyle = g; ctx.fillRect(0, 0, w, y0);
    ctx.fillStyle = 'rgba(255,255,255,.07)'; for (let x = 0; x < w; x += 47) ctx.fillRect(x, 0, 1, y0); for (let y = 0; y < y0; y += 47) ctx.fillRect(0, y, w, 1);
    ctx.fillStyle = 'rgba(190,240,225,.6)'; for (let x = 24; x < w; x += 160) ctx.fillRect(x, 16, 80, 6);                 // luz fluorescente
    ctx.fillStyle = '#c9d6df'; ctx.fillRect(0, 214, w, 6);                                                       // prateleira alta
    const cores = ['#4be3a6', '#58a6ff', '#ffb454', '#ff6f91'];
    for (let k = 0, x = 40; x < w - 20; x += 62, k++) {
      const c = cores[k % 4], hf = 28 + (k % 3) * 8;
      ctx.fillStyle = 'rgba(220,240,250,.55)'; ctx.fillRect(x - 4, 214 - hf - 22, 8, 22);
      circ(ctx, x, 214 - hf / 2 - 2, hf / 2, 'rgba(220,240,250,.28)');
      ctx.save(); ctx.beginPath(); ctx.arc(x, 214 - hf / 2 - 2, hf / 2 - 2, 0, Math.PI * 2); ctx.clip(); ctx.fillStyle = c; ctx.globalAlpha = 0.85; ctx.fillRect(x - hf / 2, 214 - hf * 0.62, hf, hf); ctx.restore();
      if (!reduced) for (let b = 0; b < 2; b++) { const f = ((t * 0.5 + k * 0.3 + b * 0.5) % 1); circ(ctx, x - 3 + b * 6, 214 - 6 - f * (hf - 8), 2, 'rgba(255,255,255,.7)'); }
    }
    ctx.fillStyle = '#0c1c2a'; ctx.fillRect(w - 290, 100, 200, 90); ctx.strokeStyle = 'rgba(91,227,176,.6)'; ctx.lineWidth = 2; ctx.strokeRect(w - 289, 101, 198, 88);
    ctx.strokeStyle = 'rgba(91,227,176,.9)'; ctx.beginPath();
    for (let i = 0; i <= 40; i++) { const px = w - 282 + i * 4.6, py = 146 + Math.sin(i * 0.5 + (reduced ? 0 : t * 2)) * 26; i ? ctx.lineTo(px, py) : ctx.moveTo(px, py); } ctx.stroke();
    poly(ctx, [[64, 120], [90, 168], [38, 168]], '#f2c230'); ctx.fillStyle = '#1a1a1a'; ctx.font = 'bold 26px sans-serif'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText('!', 64, 152);
    ctx.fillStyle = '#1b3243'; ctx.fillRect(0, y0 - 34, w, 34);
    for (let k = 0, x = 70; x < w - 40; x += 150, k++) {
      if (!livre(x, 62, doorXs)) continue;
      ctx.fillStyle = '#54707f'; ctx.fillRect(x - 56, y0 - 46, 112, 42); ctx.fillStyle = '#eef6fb'; ctx.fillRect(x - 60, y0 - 54, 120, 9);        // bancada
      if (k % 2 === 0) {                                                                                                                 // microscópio
        ctx.fillStyle = '#2c3a48'; ctx.fillRect(x - 20, y0 - 60, 40, 6); ctx.fillRect(x - 4, y0 - 100, 8, 42);
        ctx.save(); ctx.translate(x, y0 - 96); ctx.rotate(-0.5); ctx.fillStyle = '#d7dee6'; ctx.fillRect(-6, -26, 12, 34); ctx.restore();
      } else {                                                                                                                           // tubos de ensaio
        ctx.fillStyle = '#2c3a48'; ctx.fillRect(x - 36, y0 - 70, 72, 6);
        for (let q = 0; q < 4; q++) { ctx.fillStyle = 'rgba(220,240,250,.5)'; ctx.fillRect(x - 30 + q * 17, y0 - 100, 10, 32); ctx.fillStyle = cores[q]; ctx.fillRect(x - 29 + q * 17, y0 - 90, 8, 22); }
      }
    }
    ctx.textBaseline = 'alphabetic';
  }

  // Biblioteca: estantes de livros do piso ao teto, luminária de leitura, escada e globo.
  function wallLibrary(ctx, t, doorXs) {
    const w = ISO.NX * ISO.U, y0 = ISO.OY;
    const g = ctx.createLinearGradient(0, 0, 0, y0); g.addColorStop(0, '#24170e'); g.addColorStop(1, '#3a2716');
    ctx.fillStyle = g; ctx.fillRect(0, 0, w, y0);
    const cores = ['#8c2f39', '#2f5d8c', '#c19a3a', '#2e7d5b', '#6a4c93', '#b5651d', '#3b7a8c', '#a34a6b'];
    for (let row = 0; row < 6; row++) {
      const base = 100 + row * 52;
      for (let x = 4; x < w - 4;) {
        const bw = 7 + Math.floor(hash(row, x) * 8), bh = 30 + Math.floor(hash(x, row + 3) * 16);
        ctx.fillStyle = shade(cores[Math.floor(hash(row + 2, x + 1) * cores.length)], 0.7 + hash(x, row) * 0.35);
        ctx.fillRect(x, base - bh, bw, bh);
        ctx.fillStyle = 'rgba(255,230,170,.35)'; ctx.fillRect(x + 1, base - bh + 5, bw - 2, 2);
        x += bw + 1;
      }
      ctx.fillStyle = '#5a3d24'; ctx.fillRect(0, base, w, 7); ctx.fillStyle = 'rgba(255,220,170,.18)'; ctx.fillRect(0, base, w, 2);
    }
    ctx.fillStyle = '#4a3220'; for (let x = 0; x <= w; x += 188) ctx.fillRect(x - 3, 70, 6, y0 - 70);
    const lamp = ctx.createRadialGradient(w * 0.82, 120, 6, w * 0.82, 120, 150); lamp.addColorStop(0, 'rgba(255,214,130,.35)'); lamp.addColorStop(1, 'rgba(255,214,130,0)');
    ctx.fillStyle = lamp; ctx.fillRect(0, 0, w, y0);
    ctx.fillStyle = '#2a1a0e'; ctx.fillRect(0, y0 - 34, w, 34); ctx.fillStyle = '#6a4a2a'; ctx.fillRect(0, y0 - 36, w, 4);
    for (let k = 0, x = 70; x < w - 40; x += 150, k++) {
      if (!livre(x, 52, doorXs)) continue;
      ctx.fillStyle = '#6a4526'; ctx.fillRect(x - 50, y0 - 52, 100, 9); ctx.fillRect(x - 44, y0 - 44, 7, 40); ctx.fillRect(x + 37, y0 - 44, 7, 40);
      if (k % 2 === 0) {                                                                                                                 // luminária verde
        ctx.fillStyle = '#c9a050'; ctx.fillRect(x - 3, y0 - 84, 6, 32); ctx.fillStyle = '#2e8a5e'; ctx.beginPath(); ctx.ellipse(x, y0 - 88, 20, 11, 0, Math.PI, 0); ctx.fill();
        ctx.fillStyle = 'rgba(255,224,150,.28)'; ctx.beginPath(); ctx.moveTo(x - 20, y0 - 86); ctx.lineTo(x + 20, y0 - 86); ctx.lineTo(x + 38, y0 - 52); ctx.lineTo(x - 38, y0 - 52); ctx.fill();
      } else {                                                                                                                           // livros empilhados
        [['#8c2f39', 70], ['#2f5d8c', 62], ['#c19a3a', 56]].forEach(([c, wd], q) => { ctx.fillStyle = c; ctx.fillRect(x - wd / 2, y0 - 52 - (q + 1) * 12, wd, 11); ctx.fillStyle = 'rgba(255,255,255,.4)'; ctx.fillRect(x - wd / 2 + 4, y0 - 52 - (q + 1) * 12 + 4, wd - 8, 2); });
      }
    }
  }

  // Sala completa de um ambiente (env = 'datacenter' | 'escritorio' | 'sala' | 'laboratorio' | 'biblioteca'). doorXs = posições das portas.
  function drawRoom(ctx, t, doorXs, env) {
    const e = env || 'datacenter';
    ({ datacenter: drawWall, escritorio: wallOffice, sala: wallClass, laboratorio: wallLab, biblioteca: wallLibrary }[e] || drawWall)(ctx, t, doorXs);
    if (e === 'datacenter' || !ENV_INFO[e]) drawFloor(ctx, t); else drawFloorEnv(ctx, t, e);
    const v = ctx.createLinearGradient(0, 0, ISO.SW, 0);                         // vinheta lateral discreta
    v.addColorStop(0, 'rgba(2,6,12,.45)'); v.addColorStop(0.08, 'rgba(2,6,12,0)'); v.addColorStop(0.92, 'rgba(2,6,12,0)'); v.addColorStop(1, 'rgba(2,6,12,.35)');
    ctx.fillStyle = v; ctx.fillRect(0, 0, ISO.SW, ISO.OY + ISO.NY * ISO.V + 18);
  }

  // ---------- Prédio da fase (animação de entrada) ----------
  // Fachada frontal de um prédio por ambiente, com porta de correr central. (cx, baseY) = centro e base do prédio; open 0..1 = porta.
  // Devolve a geometria útil: { top, doorW, doorH }.
  function drawBuilding(ctx, env, cx, baseY, open, t) {
    const W = 520, H = 290, x = cx - W / 2, y = baseY - H, DW = 132, DH = 178, ac = (ENV_INFO[env] || ENV_INFO.datacenter).accent;
    const tt = reduced ? 0 : t;
    ctx.save();
    ctx.fillStyle = 'rgba(0,0,0,.42)'; ctx.beginPath(); ctx.ellipse(cx, baseY + 6, W * 0.62, 16, 0, 0, Math.PI * 2); ctx.fill();
    const vidro = (wx, wy, ww, wh, lit) => { ctx.fillStyle = lit ? 'rgba(255,226,150,.9)' : 'rgba(30,60,96,.9)'; ctx.fillRect(wx, wy, ww, wh); ctx.fillStyle = 'rgba(255,255,255,.18)'; ctx.fillRect(wx, wy, ww, 3); };
    if (env === 'escritorio') {                                                         // torre de vidro
      const g = ctx.createLinearGradient(x, y, x + W, baseY); g.addColorStop(0, '#4a8cc4'); g.addColorStop(1, '#1a4570');
      ctx.fillStyle = g; ctx.fillRect(x, y, W, H);
      for (let r = 0; r < 6; r++) for (let c = 0; c < 10; c++) { if (y + 24 + r * 38 > baseY - DH - 6 && Math.abs(x + 26 + c * 48 - cx) < DW) continue; vidro(x + 10 + c * 50, y + 20 + r * 38, 36, 26, hash(r, c) < 0.4); }
      poly(ctx, [[x, y], [x + 170, y], [x + 60, baseY], [x, baseY]], 'rgba(255,255,255,.07)');
      ctx.fillStyle = '#31465f'; ctx.fillRect(cx - 4, y - 46, 8, 46);
      ctx.fillStyle = Math.floor(tt * 2) % 2 ? '#ff4d5e' : '#7a2430'; ctx.beginPath(); ctx.arc(cx, y - 50, 5, 0, Math.PI * 2); ctx.fill();
    } else if (env === 'sala') {                                                        // escola de tijolos
      ctx.fillStyle = '#92503f'; ctx.fillRect(x, y, W, H);
      ctx.fillStyle = 'rgba(0,0,0,.16)'; for (let r = 0; r < H / 14; r++) { ctx.fillRect(x, y + r * 14, W, 1.5); for (let c = (r % 2) * 20; c < W; c += 40) ctx.fillRect(x + c, y + r * 14, 1.5, 14); }
      poly(ctx, [[x - 24, y], [x + W + 24, y], [cx, y - 78]], '#6b3a2e'); poly(ctx, [[x - 24, y], [x + W + 24, y], [x + W + 24, y + 12], [x - 24, y + 12]], '#4a2a22');
      circ(ctx, cx, y - 30, 20, '#f1ead8'); ctx.strokeStyle = '#4a3220'; ctx.lineWidth = 3; ctx.beginPath(); ctx.arc(cx, y - 30, 20, 0, Math.PI * 2); ctx.moveTo(cx, y - 30); ctx.lineTo(cx, y - 44); ctx.moveTo(cx, y - 30); ctx.lineTo(cx + 10, y - 26); ctx.stroke();
      for (let c = 0; c < 6; c++) { if (Math.abs(x + 50 + c * 84 - cx) < DW) continue; ctx.fillStyle = '#eee6d2'; ctx.fillRect(x + 22 + c * 84, y + 110, 56, 70); vidro(x + 27 + c * 84, y + 115, 46, 60, hash(c, 4) < 0.5); ctx.fillStyle = '#eee6d2'; ctx.fillRect(x + 49 + c * 84, y + 115, 3, 60); }
      ctx.fillStyle = '#c9c2b0'; ctx.fillRect(x + W - 40, y - 96, 4, 96);
      const wv = Math.sin(tt * 4) * 4; poly(ctx, [[x + W - 36, y - 94], [x + W + 8, y - 88 + wv], [x + W + 6, y - 66 + wv], [x + W - 36, y - 70]], '#f2b84b');
    } else if (env === 'laboratorio') {                                                 // laboratório moderno
      const g = ctx.createLinearGradient(x, y, x, baseY); g.addColorStop(0, '#eef5fa'); g.addColorStop(1, '#a9bccb');
      ctx.fillStyle = g; ctx.fillRect(x, y, W, H);
      ctx.fillStyle = '#2fb896'; ctx.fillRect(x, y + 104, W, 14);
      for (let c = 0; c < 8; c++) { if (Math.abs(x + 40 + c * 62 - cx) < DW * 0.75) continue; ctx.fillStyle = '#d4e0ea'; ctx.fillRect(x + 14 + c * 62, y + 130, 50, 44); ctx.fillStyle = 'rgba(47,184,150,.65)'; ctx.fillRect(x + 18 + c * 62, y + 134, 42, 36); }
      circ(ctx, x + 70, y + 60, 30, '#d4e0ea'); circ(ctx, x + 70, y + 60, 24, 'rgba(47,184,150,.7)'); circ(ctx, x + W - 70, y + 60, 30, '#d4e0ea'); circ(ctx, x + W - 70, y + 60, 24, 'rgba(47,184,150,.7)');
      [-1, 1].forEach(k => { ctx.fillStyle = '#9fb1bf'; ctx.fillRect(cx + k * 190 - 12, y - 36, 24, 36); ctx.fillStyle = `rgba(91,227,176,${0.25 + 0.2 * Math.sin(tt * 3 + k)})`; ctx.beginPath(); ctx.ellipse(cx + k * 190, y - 48, 16, 20, 0, 0, Math.PI * 2); ctx.fill(); });
    } else if (env === 'biblioteca') {                                                  // biblioteca clássica
      const g = ctx.createLinearGradient(x, y, x, baseY); g.addColorStop(0, '#e2d2ae'); g.addColorStop(1, '#a99468');
      ctx.fillStyle = g; ctx.fillRect(x, y, W, H);
      poly(ctx, [[x - 20, y], [x + W + 20, y], [cx, y - 76]], '#d2bf95'); poly(ctx, [[x - 20, y], [x + W + 20, y], [x + W + 20, y + 14], [x - 20, y + 14]], '#b9a578');
      circ(ctx, cx, y - 30, 17, '#8a7650'); ctx.fillStyle = '#e2d2ae'; ctx.fillRect(cx - 12, y - 36, 11, 14); ctx.fillRect(cx + 1, y - 36, 11, 14);
      [x + 40, x + 120, x + W - 152, x + W - 72].forEach(cxl => { ctx.fillStyle = '#f2e6c8'; ctx.fillRect(cxl, y + 18, 32, H - 38); ctx.fillStyle = 'rgba(0,0,0,.12)'; ctx.fillRect(cxl + 22, y + 18, 10, H - 38); ctx.fillStyle = '#cdb98f'; ctx.fillRect(cxl - 5, y + 14, 42, 10); ctx.fillRect(cxl - 5, baseY - 24, 42, 10); });
      [x + 78, x + W - 110].forEach(wx => { ctx.fillStyle = 'rgba(255,200,110,.85)'; ctx.fillRect(wx - 6, y + 120, 36, 56); ctx.beginPath(); ctx.arc(wx + 12, y + 120, 18, Math.PI, 0); ctx.fill(); });
      ctx.fillStyle = '#b9a578'; ctx.fillRect(x - 14, baseY - 14, W + 28, 8); ctx.fillStyle = '#a58f66'; ctx.fillRect(x - 28, baseY - 6, W + 56, 8);
    } else {                                                                            // centro de dados (bloco escuro com LEDs)
      const g = ctx.createLinearGradient(x, y, x, baseY); g.addColorStop(0, '#16294a'); g.addColorStop(1, '#0b182c');
      ctx.fillStyle = g; ctx.fillRect(x, y, W, H);
      ctx.strokeStyle = 'rgba(88,166,255,.5)'; ctx.lineWidth = 2; ctx.strokeRect(x + 1, y + 1, W - 2, H - 2);
      for (let c = 0; c < 12; c++) for (let r = 0; r < 9; r++) { if (Math.abs(x + 22 + c * 40 - cx) < DW * 0.6 && y + 40 + r * 24 > baseY - DH - 20) continue; ctx.fillStyle = (Math.floor(tt * 2 + c + r * 2) % 3) ? 'rgba(88,166,255,.8)' : '#12315a'; ctx.fillRect(x + 14 + c * 40, y + 38 + r * 24, 24, 5); }
      [-1, 1].forEach(k => { ctx.strokeStyle = '#8fa9c8'; ctx.lineWidth = 3; ctx.beginPath(); ctx.moveTo(cx + k * 205, y); ctx.lineTo(cx + k * 205, y - 24); ctx.stroke(); ctx.fillStyle = '#c9d6e6'; ctx.beginPath(); ctx.ellipse(cx + k * 205, y - 30, 26, 11, k * 0.4, 0, Math.PI * 2); ctx.fill(); });
    }
    // porta de correr central, com luz por dentro
    const dx = cx - DW / 2, dy = baseY - DH;
    ctx.fillStyle = '#0c1522'; ctx.fillRect(dx - 8, dy - 8, DW + 16, DH + 8);
    const luz = ctx.createLinearGradient(0, dy, 0, baseY); luz.addColorStop(0, '#fff3cf'); luz.addColorStop(1, '#ffc766');
    ctx.fillStyle = luz; ctx.globalAlpha = 0.25 + 0.75 * open; ctx.fillRect(dx, dy, DW, DH); ctx.globalAlpha = 1;
    ctx.save(); ctx.beginPath(); ctx.rect(dx, dy, DW, DH); ctx.clip();
    const off = open * (DW / 2 + 2);
    [dx - off, cx + off].forEach(px => {
      const pg = ctx.createLinearGradient(px, dy, px + DW / 2, baseY); pg.addColorStop(0, '#2a6fd0'); pg.addColorStop(1, '#123a72');
      ctx.fillStyle = pg; ctx.fillRect(px, dy, DW / 2, DH); ctx.strokeStyle = 'rgba(140,190,250,.85)'; ctx.lineWidth = 2; ctx.strokeRect(px + 1, dy + 1, DW / 2 - 2, DH - 2);
      ctx.fillStyle = 'rgba(255,255,255,.12)'; ctx.fillRect(px + 8, dy + 10, 6, DH - 20);
    });
    ctx.restore();
    ctx.strokeStyle = ac; ctx.lineWidth = 4; ctx.shadowColor = ac; ctx.shadowBlur = 14; ctx.strokeRect(dx - 8, dy - 8, DW + 16, DH + 8);
    ctx.restore();
    return { top: y, doorW: DW, doorH: DH };
  }

  // Placa grande do prédio: "kicker" (ex.: FASE 2 DE 4) e o nome do grupo, que encolhe/quebra em até 2 linhas para caber.
  function drawSign(ctx, cx, top, w, h, kicker, title, accent, t) {
    const x = cx - w / 2;
    ctx.save();
    ctx.shadowColor = 'rgba(0,0,0,.6)'; ctx.shadowBlur = 26; ctx.shadowOffsetY = 12;
    const g = ctx.createLinearGradient(0, top, 0, top + h); g.addColorStop(0, '#13264a'); g.addColorStop(1, '#09152b');
    rr(ctx, x, top, w, h, 16); ctx.fillStyle = g; ctx.fill();
    ctx.restore();
    ctx.save(); ctx.shadowColor = accent; ctx.shadowBlur = 16 + (reduced ? 0 : 6 * Math.sin(t * 3));
    rr(ctx, x, top, w, h, 16); ctx.strokeStyle = accent; ctx.lineWidth = 4; ctx.stroke(); ctx.restore();
    rr(ctx, x + 9, top + 9, w - 18, h - 18, 10); ctx.strokeStyle = 'rgba(255,255,255,.18)'; ctx.lineWidth = 1.5; ctx.stroke();
    [x + 24, x + w - 24].forEach(bx => { circ(ctx, bx, top + 22, 5, accent); circ(ctx, bx, top + h - 22, 5, accent); });
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.font = `bold 21px ${MONO}`; ctx.fillStyle = accent; ctx.fillText(kicker, cx, top + 31);
    let size = 54, lines = [];
    for (; size >= 26; size -= 2) { ctx.font = `bold ${size}px ${SANS}`; lines = wrap(ctx, title, w - 90); if (lines.length <= 2 && lines.length * Math.round(size * 1.12) <= h - 70 && lines.every(l => ctx.measureText(l).width <= w - 90)) break; }
    const lh = Math.round(size * 1.12), area = h - 58, y0 = top + 52 + (area - lines.length * lh) / 2 + lh / 2;
    ctx.save(); ctx.shadowColor = accent; ctx.shadowBlur = 10; ctx.fillStyle = '#ffffff';
    lines.slice(0, 2).forEach((l, i) => ctx.fillText(l, cx, y0 + i * lh)); ctx.restore();
    ctx.textBaseline = 'alphabetic';
  }

  // Céu, cidade ao fundo e a praça (com o tapete que leva à porta) onde o avatar caminha até o prédio.
  function drawStreet(ctx, env, t, baseY) {
    const W = 1280, H = 720, cx = 640;
    const cores = { datacenter: ['#050c1a', '#0f2748'], escritorio: ['#07142c', '#1d4a7a'], sala: ['#1c1530', '#7a4a52'], laboratorio: ['#06181d', '#12525a'], biblioteca: ['#180f09', '#5a3a22'] }[env] || ['#050c1a', '#0f2748'];
    const sky = ctx.createLinearGradient(0, 0, 0, baseY); sky.addColorStop(0, cores[0]); sky.addColorStop(1, cores[1]);
    ctx.fillStyle = sky; ctx.fillRect(0, 0, W, baseY);
    for (let i = 0; i < 70; i++) { const sx = hash(i, 1) * W, sy = hash(i, 2) * (baseY - 140), a = 0.3 + 0.5 * hash(i, 3) * (reduced ? 1 : (0.6 + 0.4 * Math.sin(t * 2 + i))); ctx.fillStyle = `rgba(255,255,255,${a})`; ctx.fillRect(sx, sy, 2, 2); }
    for (let layer = 0; layer < 2; layer++) {                                          // cidade distante, em duas camadas
      for (let x = -20, k = 0; x < W + 40; k++) {
        const bw = 50 + hash(k, layer + 5) * 70, bh = (layer ? 90 : 150) + hash(k, layer + 9) * (layer ? 90 : 130);
        ctx.fillStyle = layer ? 'rgba(10,22,42,.85)' : 'rgba(6,14,28,.95)'; ctx.fillRect(x, baseY - bh, bw, bh);
        if (!layer) for (let r = 0; r < bh / 22; r++) for (let c = 0; c < bw / 18; c++) if (hash(k * 9 + r, c) < 0.22) { ctx.fillStyle = 'rgba(255,214,130,.6)'; ctx.fillRect(x + 6 + c * 18, baseY - bh + 8 + r * 22, 6, 8); }
        x += bw + 6 + hash(k, 3) * 10;
      }
    }
    const gr = ctx.createLinearGradient(0, baseY, 0, H); gr.addColorStop(0, '#12233b'); gr.addColorStop(1, '#0a1424');
    ctx.fillStyle = gr; ctx.fillRect(0, baseY, W, H - baseY);
    ctx.strokeStyle = 'rgba(88,166,255,.18)'; ctx.lineWidth = 1;                         // piso da praça em perspectiva
    for (let k = -10; k <= 10; k++) { ctx.beginPath(); ctx.moveTo(cx + k * 30, baseY); ctx.lineTo(cx + k * 130, H); ctx.stroke(); }
    for (let k = 1; k < 7; k++) { const yy = baseY + (H - baseY) * Math.pow(k / 7, 1.7); ctx.beginPath(); ctx.moveTo(0, yy); ctx.lineTo(W, yy); ctx.stroke(); }
    poly(ctx, [[cx - 78, baseY], [cx + 78, baseY], [cx + 230, H], [cx - 230, H]], 'rgba(88,166,255,.13)');   // tapete até a porta
    ctx.strokeStyle = 'rgba(120,180,250,.55)'; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(cx - 78, baseY); ctx.lineTo(cx - 230, H); ctx.moveTo(cx + 78, baseY); ctx.lineTo(cx + 230, H); ctx.stroke();
    ctx.fillStyle = 'rgba(120,180,250,.5)'; ctx.fillRect(0, baseY, W, 2);
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
    drawRoom(ctx, t, doorXs, env) { return drawRoom(ctx, t, doorXs, env); }
    drawDoors(ctx, count, doorsData) { return drawDoors(ctx, count, doorsData || []); }
    drawFade(ctx, alpha) { return drawFade(ctx, alpha); }
    loadLogos(config, callback) { return loadLogos(config, callback); }
  }
  // Utilitários de desenho e UI usados pelas telas e pelos avatares.
  Object.assign(IsoRenderer.prototype, {
    project, shade, hash, poly, rr, cube, isoBox, isoFaceLabel, wrap, pixelText, glowText,
    drawBackground, drawPanel, drawButton, wipe, drawLogo,
    drawFloor, drawWall, drawWalkway, layoutDoors, drawDoorBack, drawDoorFront, drawHolo, drawHintBox,
    ENVIRONMENTS, ENV_INFO, envOf, drawBuilding, drawSign, drawStreet
  });

  window.IsoRendererClass = IsoRenderer;
  window.IsoRenderer = new IsoRenderer();
  window.Renderer = window.IsoRenderer;   // alias usado pelos demais módulos
})();
