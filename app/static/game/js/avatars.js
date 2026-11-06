// Avatares voxel procedurais (9 perfis), classe AvatarManager e classe Player.
// Tudo desenhado com prismas no Canvas, sem imagens.
(function () {
  'use strict';

  const shade = Renderer.shade;
  const NEON = '#58a6ff';   // detalhes neon da paleta azul

  // Campos: skin, hair, style (ver HAIR), outfit, shirt, under, trim, pants, shoes, sleeve ('long'|'short'),
  // sleeveColor, glasses, glassColor, headset, badge, band, streak, armBand, narrow (olhos estreitos),
  // legs ('pants'|'shorts'|'skirt'), skirt (cor da saia/vestido), headdress (cores do cocar), faceBoost (olhos com branco)
  const PROFILES = [
    { id: 0, label: 'Avatar 1', short: 'Avatar 1', skin: '#4A3326', hair: '#15110e', style: 'afro',
      outfit: 'jacket', shirt: '#6b7280', trim: NEON, pants: '#2a3040', shoes: '#14161c', sleeve: 'long',
      desc: 'Cabelo alto e volumoso e jaqueta tecnológica cinza com detalhes em azul neon.' },
    { id: 1, label: 'Avatar 2', short: 'Avatar 2', skin: '#5C3A21', hair: '#120d0b', style: 'braids', faceBoost: true,
      outfit: 'labcoat', shirt: '#f2f5f8', under: '#3b2a5e', trim: NEON, legs: 'skirt', skirt: '#3b2a5e', shoes: '#14161c', sleeve: 'long',
      desc: 'Tranças com contas azuis, jaleco curto sobre vestido roxo e rosto à mostra.' },
    { id: 2, label: 'Avatar 3', short: 'Avatar 3', skin: '#F3C99F', hair: '#5a3a22', style: 'short',
      outfit: 'sweater', shirt: '#7a1f2b', trim: '#e0b13a', pants: '#2d3a55', shoes: '#1b1b22', sleeve: 'long', badge: true,
      desc: 'Cabelo castanho curto e suéter acadêmico com crachá digital.' },
    { id: 3, label: 'Avatar 4', short: 'Avatar 4', skin: '#F7D5B8', hair: '#6b4423', style: 'ponytail', faceBoost: true,
      outfit: 'tee', shirt: '#8b929c', trim: '#c9ced6', legs: 'skirt', skirt: '#2f3c5a', shoes: '#1b1b22', sleeve: 'short', headset: true,
      desc: 'Cabelo castanho longo preso em rabo de cavalo, blusa técnica cinza, saia e headphone.' },
    { id: 4, label: 'Avatar 5', short: 'Avatar 5', skin: '#E0B088', hair: '#2b2b3a', style: 'modern',
      outfit: 'jacket', shirt: '#8e6bd8', trim: NEON, pants: '#262a3a', shoes: '#14161c', sleeve: 'long', streak: '#ff7ad9',
      desc: 'Corte moderno com mecha colorida e jaqueta techwear lilás com azul neon.' },
    { id: 5, label: 'Avatar 6', short: 'Avatar 6', skin: '#F5DEB3', hair: '#15151a', style: 'short',
      outfit: 'social', shirt: '#dfe6ee', trim: NEON, pants: '#20263a', shoes: '#101218', sleeve: 'long',
      glasses: true, glassColor: NEON, narrow: true,
      desc: 'Cabelo liso escuro, óculos estilizados em neon e camisa social casual.' },
    { id: 6, label: 'Avatar 7', short: 'Avatar 7', skin: '#FBE7C6', hair: '#12121a', style: 'straight', faceBoost: true, narrow: true,
      outfit: 'vest', shirt: '#16243a', under: '#e9eef5', sleeveColor: '#e9eef5', trim: NEON, legs: 'skirt', skirt: '#1f2b45', shoes: '#101218',
      sleeve: 'long',
      desc: 'Cabelo liso na altura do queixo com franja reta, colete com circuitos azuis, blusa e saia.' },
    { id: 7, label: 'Avatar 8', short: 'Avatar 8', skin: '#A0522D', hair: '#0f0d0d', style: 'bowl', faceBoost: true,
      outfit: 'techwear', shirt: '#15171a', trim: '#d6322b', legs: 'shorts', pants: '#15171a', shoes: '#2a1d12', sleeve: 'short', armBand: '#d6322b',
      headdress: ['#d6322b', '#f2c230', '#ffffff', '#1d7a5a'],
      desc: 'Corte tigela, cocar de penas, camiseta preta com grafismos vermelhos e bermuda.' },
    { id: 8, label: 'Avatar 9', short: 'Avatar 9', skin: '#B35933', hair: '#0f0d0d', style: 'long', faceBoost: true,
      outfit: 'tee', shirt: '#1f7a3a', trim: '#16181a', sleeveColor: '#16181a', legs: 'shorts', pants: '#16181a', shoes: '#2a1d12', sleeve: 'short',
      headdress: ['#e0a21a', '#d6322b', '#ffffff', '#1d7a5a'],
      desc: 'Cabelo longo e liso, cocar de penas, camisa técnica verde e preta e bermuda.' }
  ];

  // fringe: altura da franja (cobre só a testa); top: volume sobre a cabeça; wide: alarga o volume;
  // sideZ: altura onde terminam as mechas laterais; backZ: altura onde termina o cabelo nas costas
  const HAIR = {
    afro:     { fringe: 30.3, top: 4.2, wide: 1.3 },
    braids:   { fringe: 30.0, top: 1.2, braids: true },
    short:    { fringe: 30.3, top: 1.0 },
    ponytail: { fringe: 29.6, top: 1.2, sideZ: 27, pony: true },
    modern:   { fringe: 29.8, top: 2.0, sweep: true },
    straight: { fringe: 29.9, top: 1.2, sideZ: 21.5, backZ: 20 },
    long:     { fringe: 29.8, top: 1.2, sideZ: 12, backZ: 12 },
    bowl:     { fringe: 29.6, top: 1.0, sideZ: 27.2, backZ: 26.5 }
  };

  // ---- primitivas em "unidades de voxel"; origem = centro dos pés ----
  let C, K;

  function P(x, y, z) { return [(x - y) * K, (x + y) * K / 2 - z * K]; }
  function poly(pts, fill) {
    C.fillStyle = fill;
    C.beginPath();
    pts.forEach((p, i) => (i ? C.lineTo(p[0], p[1]) : C.moveTo(p[0], p[1])));
    C.closePath();
    C.fill();
  }
  function box(x, y, z, w, d, h, col) {
    poly([P(x + w, y, z + h), P(x + w, y + d, z + h), P(x + w, y + d, z), P(x + w, y, z)], shade(col, 0.7));
    poly([P(x, y + d, z + h), P(x + w, y + d, z + h), P(x + w, y + d, z), P(x, y + d, z)], col);
    poly([P(x, y, z + h), P(x + w, y, z + h), P(x + w, y + d, z + h), P(x, y + d, z + h)], shade(col, 1.2));
  }
  // retângulo sobre a face frontal-esquerda (+y); u ao longo de x, v de cima (0) para baixo (1)
  function faceL(x, y, z, w, d, h, u0, v0, u1, v1, col) {
    const X0 = x + w * u0, X1 = x + w * u1, Z0 = z + h * (1 - v0), Z1 = z + h * (1 - v1), Y = y + d;
    poly([P(X0, Y, Z0), P(X1, Y, Z0), P(X1, Y, Z1), P(X0, Y, Z1)], col);
  }
  // retângulo sobre a face lateral-direita (+x); u ao longo de y
  function faceR(x, y, z, w, d, h, u0, v0, u1, v1, col) {
    const Y0 = y + d * u0, Y1 = y + d * u1, Z0 = z + h * (1 - v0), Z1 = z + h * (1 - v1), X = x + w;
    poly([P(X, Y0, Z0), P(X, Y1, Z0), P(X, Y1, Z1), P(X, Y0, Z1)], shade(col, 0.7));
  }

  function torso(p, zb) {
    const base = (p.outfit === 'labcoat' || p.outfit === 'vest') ? p.under : p.shirt;
    box(-4, -2, 12 + zb, 8, 4, 12, base);
    const f = (u0, v0, u1, v1, c) => faceL(-4, -2, 12 + zb, 8, 4, 12, u0, v0, u1, v1, c);
    const dark = shade(p.shirt, 0.78);
    switch (p.outfit) {
      case 'jacket':
        f(0, 0, 1, 0.12, dark);
        f(0.47, 0, 0.53, 1, p.trim);
        f(0.12, 0.6, 0.32, 0.66, dark);
        f(0.68, 0.6, 0.88, 0.66, dark);
        break;
      case 'labcoat':
        f(0, 0, 0.36, 1, p.shirt); f(0.64, 0, 1, 1, p.shirt);
        f(0.36, 0, 0.4, 1, shade(p.shirt, 0.85)); f(0.6, 0, 0.64, 1, shade(p.shirt, 0.85));
        f(0.7, 0.3, 0.9, 0.4, p.trim);
        break;
      case 'sweater':
        f(0, 0, 1, 0.1, shade(p.shirt, 1.25));
        f(0, 0.62, 1, 0.7, p.trim);
        break;
      case 'tee':
        f(0.36, 0.18, 0.64, 0.4, p.trim);
        f(0.42, 0.24, 0.58, 0.34, shade(p.shirt, 0.8));
        break;
      case 'social':
        f(0, 0, 1, 0.1, shade(p.shirt, 0.86));
        f(0.48, 0.1, 0.52, 1, shade(p.shirt, 0.8));
        [0.25, 0.45, 0.65, 0.85].forEach(v => f(0.455, v, 0.545, v + 0.05, '#9aa6b2'));
        f(0.64, 0.28, 0.88, 0.46, shade(p.shirt, 0.92));
        break;
      case 'vest':
        f(0, 0, 0.3, 1, p.shirt); f(0.7, 0, 1, 1, p.shirt);
        [0.2, 0.5, 0.78].forEach((v, i) => {
          f(0.04, v, 0.24, v + 0.04, p.trim); f(0.74, v + 0.03, 0.94, v + 0.07, p.trim);
          f(i % 2 ? 0.2 : 0.06, v - 0.04, i % 2 ? 0.26 : 0.12, v + 0.08, p.trim);
        });
        break;
      case 'techwear':
        f(0, 0.62, 1, 0.74, p.trim);
        for (let i = 0; i < 8; i++) f(i / 8, 0.74, (i + 1) / 8, 0.86, i % 2 ? shade(p.trim, 0.6) : p.trim);
        f(0, 0.86, 1, 0.9, p.trim);
        f(0.14, 0.12, 0.34, 0.22, '#2a2e33');
        break;
    }
    if (p.badge) {
      f(0.64, 0.2, 0.86, 0.44, '#f4f7fb');
      f(0.68, 0.26, 0.82, 0.3, '#1f6feb');
      f(0.68, 0.34, 0.8, 0.37, NEON);
    }
  }

  function arm(p, x, sw, zb) {
    const yy = -2 + sw;
    const hand = p.sleeve === 'short' ? 7 : 3;
    const sleeve = p.sleeveColor || p.shirt;
    box(x, yy, 12 + zb, 4, 4, hand, p.skin);
    box(x, yy, 12 + zb + hand, 4, 4, 12 - hand, sleeve);
    if (p.armBand && x > 0) faceR(x, yy, 12 + zb + hand, 4, 4, 12 - hand, 0, 0.3, 1, 0.55, p.armBand);
  }

  // Mão com contorno escuro: uma caixa maior e escura por trás cria a borda, mesmo em pele escura.
  function hand(p, x, y, z, w, d, h) {
    box(x - 0.4, y - 0.4, z - 0.25, w + 0.8, d + 0.8, h + 0.5, shade(p.skin, 0.38));
    box(x, y, z, w, d, h, p.skin);
  }

  // Braço levantado (comemorar ou coçar a cabeça): manga embaixo e mão em cima, ao longo de z.
  function armUp(p, x, y, z, len) {
    const sleeve = p.sleeveColor || p.shirt;
    const sl = p.sleeve === 'short' ? 5 : len - 3.5;
    box(x, y, z, 4, 4, sl, sleeve);
    hand(p, x, y, z + sl, 4, 4, len - sl);
  }

  // Pose "pensativo", em duas partes: o braço (desenhado com o corpo) e o antebraço com a mão, que ficam À FRENTE da cabeça.
  function armThinkBack(p, zb) {
    const sleeve = p.sleeveColor || p.shirt, bare = p.sleeve === 'short';
    box(5.5, -0.5, 19.5 + zb, 3.5, 3.5, 5, sleeve);
    box(5.5, -0.5, 24.5 + zb, 3.5, 3.5, 4, bare ? p.skin : sleeve);
  }
  function armThinkFront(p, zb, scr) {
    const sleeve = p.sleeveColor || p.shirt, bare = p.sleeve === 'short', z0 = 24 + zb;
    faceR(-4, -4, z0, 8, 8, 8, (3.6 + scr) / 8 + 0.03, 0.3, (6.4 + scr) / 8 + 0.03, 0.7, shade(p.skin, 0.4));   // sombra na lateral da cabeça
    box(4.6, -0.5 + scr, 27 + zb, 4.4, 3, 3, bare ? p.skin : sleeve);                                           // antebraço
    hand(p, 4.05, -0.4 + scr, 27.2 + zb, 1.7, 2.6, 2.8);                                                         // mão
  }

  function leg(p, x, sw, zb) {
    const y = -2 + sw;
    if (p.legs === 'shorts') {                              // bermuda, pernas à mostra e sandálias
      box(x, y, 0, 4, 4, 1.6, p.shoes);
      box(x, y, 1.6, 4, 4, 5.6, p.skin);
      box(x, y, 7.2, 4, 4, 4.8 + zb, p.pants);
    } else if (p.legs === 'skirt') {                        // pernas à mostra sob a saia
      box(x, y, 0, 4, 4, 2, p.shoes);
      box(x, y, 2, 4, 4, 10 + zb, p.skin);
    } else {
      box(x, y, 0, 4, 4, 2, p.shoes);
      box(x, y, 2, 4, 4, 10 + zb, p.pants);
    }
  }

  // Saia ou vestido: bloco levemente mais largo que o tronco, com a barra mais clara.
  function skirt(p, zb) {
    if (p.legs !== 'skirt') return;
    box(-4.7, -2.7, 8, 9.4, 5.4, 6 + zb, p.skirt);
    faceL(-4.7, -2.7, 8, 9.4, 5.4, 6 + zb, 0, 0.84, 1, 1, shade(p.skirt, 1.35));
  }

  // Medidas comuns da cabeça: z0 = base; zf = base da franja; top = topo do cabelo.
  function hg(p, zb) {
    const H = HAIR[p.style], z0 = 24 + zb, w = H.wide || 0;
    return { H, z0, zf: z0 + (H.fringe - 24), top: 32 + zb + H.top, x0: -4.4 - w, y0: -4.4 - w, ww: 8.8 + 2 * w, dd: 4.25 + 4.4 + w };
  }

  // Peças do lado esquerdo e das costas: ficam ATRÁS da cabeça, então são desenhadas antes dela.
  function headBehind(p, zb) {
    const { H, z0, zf } = hg(p, zb);
    if (H.sideZ != null) box(-4.6, -1, z0 + (H.sideZ - 24), 0.6, 5.3, zf + 0.2 - (z0 + (H.sideZ - 24)), p.hair);   // mecha lateral esquerda
    if (H.braids) {
      for (let i = 0; i < 3; i++) {
        box(-5.2, -0.5 + i * 1.5, z0 - 7, 1.0, 1.1, 14, p.hair);
        box(-5.2, -0.5 + i * 1.5, z0 - 7, 1.0, 1.1, 1.2, p.trim);       // conta
      }
    }
    if (p.headset) box(-5.4, -1.5, z0 + 2, 1.4, 3, 3.6, '#2a2f3a');     // concha esquerda do headphone
  }

  // A cabeça e o rosto.
  function head(p, zb) {
    const z0 = 24 + zb;
    box(-4, -4, z0, 8, 8, 8, p.skin);
    const f = (u0, v0, u1, v1, c) => faceL(-4, -4, z0, 8, 8, 8, u0, v0, u1, v1, c);
    const eyeTop = p.narrow ? 0.47 : 0.42, eyeBot = p.narrow ? 0.57 : 0.6;
    if (p.glasses) {
      const fr = p.glassColor || '#1c2230';
      f(0.13, 0.35, 0.44, 0.66, fr); f(0.56, 0.35, 0.87, 0.66, fr);
      f(0.44, 0.42, 0.56, 0.47, fr);
      f(0.17, 0.4, 0.4, 0.62, '#dbeafe'); f(0.6, 0.4, 0.83, 0.62, '#dbeafe');
    }
    if (p.faceBoost) {                                       // olhos com branco e nariz: o rosto fica legível mesmo em pele escura
      f(0.17, eyeTop - 0.03, 0.41, eyeBot + 0.03, '#f4f7fb'); f(0.59, eyeTop - 0.03, 0.83, eyeBot + 0.03, '#f4f7fb');
      f(0.27, eyeTop, 0.37, eyeBot, '#1b1b26'); f(0.65, eyeTop, 0.75, eyeBot, '#1b1b26');
      f(0.46, 0.62, 0.54, 0.72, shade(p.skin, 0.8));
      f(0.38, 0.8, 0.62, 0.86, shade(p.skin, 0.5));
    } else {
      f(0.22, eyeTop, 0.36, eyeBot, '#1b1b26'); f(0.64, eyeTop, 0.78, eyeBot, '#1b1b26');
      f(0.4, 0.78, 0.6, 0.84, shade(p.skin, 0.62));
    }
  }

  // Cabelo do topo e da frente, lado direito e acessórios: ficam À FRENTE da cabeça.
  function headFront(p, zb) {
    const { H, z0, zf, top, x0, y0, ww, dd } = hg(p, zb);
    if (H.sideZ != null) box(4.0, -4.4, z0 + (H.sideZ - 24), 0.6, 6.8, zf + 0.2 - (z0 + (H.sideZ - 24)), p.hair);   // mecha lateral direita
    box(x0, y0, zf, ww, dd, top - zf, p.hair);                                                                      // volume do topo e franja
    if (H.sweep) {
      box(-4.4, y0, z0 + 3.2, 4.9, dd, 2.9, p.hair);
      if (p.streak) box(0.6, y0, z0 + 8 + H.top - 0.5, 1.6, dd, 0.7, p.streak);
    }
    if (H.braids) {
      for (let i = 0; i < 3; i++) {
        box(4.2, -3 + i * 1.7, z0 - 7, 1.0, 1.1, 14, p.hair);
        box(4.2, -3 + i * 1.7, z0 - 7, 1.0, 1.1, 1.2, p.trim);
      }
    }
    if (p.band) {
      for (let i = 0; i < 8; i++) faceL(x0, y0, zf, ww, dd, top - zf, i / 8, 0.62, (i + 1) / 8, 0.94, p.band[i % p.band.length]);
    }
    if (p.headdress) {                                       // cocar: faixa na testa e penas em leque
      const cols = p.headdress;
      for (let i = 0; i < 8; i++) faceL(x0, y0, zf, ww, dd, top - zf, i / 8, 0.55, (i + 1) / 8, 0.95, cols[i % cols.length]);
      for (let k = -3; k <= 3; k++) box(k * 1.15 - 0.5, -0.9, top, 1, 0.8, 3.2 + (3 - Math.abs(k)) * 1.3, cols[(k + 3) % cols.length]);
    }
    if (p.headset) {
      box(4, -1.5, z0 + 2, 1.4, 3, 3.6, '#2a2f3a');          // concha direita
      faceR(4, -1.5, z0 + 2, 1.4, 3, 3.6, 0.2, 0.2, 0.8, 0.8, NEON);
      box(-4.6, -0.5, top, 9.2, 1, 0.7, '#2a2f3a');          // arco sobre a cabeça
    }
  }

  // Desenha o avatar com os pés em (x, y). o: { t, phase, moving, face:'L'|'R', alpha }
  function draw(ctx, p, x, y, scale, o) {
    o = o || {};
    C = ctx;
    K = 3.2 * (scale || 1);
    const H = HAIR[p.style];
    const sw = o.moving ? Math.sin(o.phase || 0) * 4 : 0;
    const zb = o.moving ? Math.abs(Math.cos(o.phase || 0)) * 0.9 : Math.sin((o.t || 0) * 2.2) * 0.35 + 0.35;
    ctx.save();
    ctx.imageSmoothingEnabled = false;      // estética voxel/pixel apenas nos avatares (texto e logos seguem suavizados)
    ctx.translate(x, y);
    if (o.face === 'R') ctx.scale(-1, 1);
    if (o.alpha != null) ctx.globalAlpha *= o.alpha;
    // poses de reação: 'cheer' (pula com os braços para cima) e 'think' (coça a cabeça, pensativo)
    const pose = o.pose || null, tt = o.t || 0;
    const jump = pose === 'cheer' && !o.still ? Math.abs(Math.sin(tt * 6)) * 5 : 0;
    ctx.fillStyle = 'rgba(0,0,0,.35)';
    ctx.beginPath(); ctx.ellipse(0, 0, 7 * K * (1 - jump * 0.04), 3.4 * K * (1 - jump * 0.04), 0, 0, Math.PI * 2); ctx.fill();
    if (jump) ctx.translate(0, -jump * K);

    // atrás de tudo: cabelo das costas e rabo de cavalo
    if (H.backZ != null) box(-4.5, -5.6, H.backZ + zb, 9, 1.6, 32 - H.backZ, p.hair);
    if (H.pony) {
      box(-1.6, -8.2, 13 + zb, 3.2, 3.8, 18, p.hair);
      box(-1.8, -4.8, 28.5 + zb, 3.6, 1, 1.2, p.trim);       // elástico
    }
    leg(p, -4, sw, zb);
    leg(p, 0, -sw, zb);
    skirt(p, zb);
    if (pose === 'cheer') armUp(p, -9, -2, 20.5 + zb + (o.still ? 0 : Math.sin(tt * 12) * 1.2), 12.5); else arm(p, -8, -sw, zb);
    torso(p, zb);
    if (pose === 'cheer') armUp(p, 5, -2, 20.5 + zb + (o.still ? 0 : Math.cos(tt * 12) * 1.2), 12.5);
    else if (pose === 'think') armThinkBack(p, zb);
    else arm(p, 4, sw, zb);
    headBehind(p, zb);
    head(p, zb);
    headFront(p, zb);
    if (pose === 'think') armThinkFront(p, zb, o.still ? 0 : Math.sin(tt * 9) * 1.6);
    ctx.restore();
  }

  // Gerenciador do catálogo e do desenho dos avatares.
  class AvatarManager {
    constructor() {
      this.catalog = PROFILES;
      this.PROFILES = PROFILES;   // alias usado pelas telas
    }

    // state: 'idle' | 'walking' | 'select' (estático, de frente, em escala 2x) | 'cheer' | 'think'.
    // walkFrame: fase do passo (radianos); opts: { scale, t, face, alpha }.
    drawAvatar(ctx, screenX, screenY, avatarIndex, state, walkFrame, opts) {
      opts = opts || {};
      const p = this.catalog[avatarIndex];
      if (!p) return;
      if (state === 'cheer' || state === 'think') {          // reações: opts.t = tempo da animação; opts.still = pose parada
        draw(ctx, p, screenX, screenY, opts.scale || 1, { pose: state, t: opts.t, still: opts.still, face: opts.face || 'L', alpha: opts.alpha });
        return;
      }
      const select = state === 'select';
      draw(ctx, p, screenX, screenY, (opts.scale || 1) * (select ? 2 : 1), {
        t: select ? 0 : opts.t,
        phase: walkFrame,
        moving: state === 'walking',
        face: select ? 'L' : opts.face,
        alpha: opts.alpha
      });
    }

    // Compatibilidade: desenha um perfil diretamente.
    draw(ctx, profile, x, y, scale, o) { draw(ctx, profile, x, y, scale, o); }
  }

  // Jogador no grid isométrico: posição, alvo de interpolação, velocidade e ciclo de passos.
  class Player {
    constructor(name, avatarIndex, opts) {
      opts = opts || {};
      this.name = name;
      this.avatarIndex = avatarIndex;
      this.gridX = opts.gridX != null ? opts.gridX : 7;
      this.gridY = opts.gridY != null ? opts.gridY : 7;
      this.targetGridX = null;
      this.targetGridY = null;
      this.speed = opts.speed || 2.3;          // unidades de grid por segundo
      this.state = 'idle';                     // 'idle' | 'walking'
      this.facing = 'L';
      this.alpha = 1;
      this.walkPhase = 0;
      this.bounds = opts.bounds || null;       // função(player) que mantém o jogador nos limites
      this.onStep = opts.onStep || null;       // chamada no ritmo dos passos (ex.: tocar som)
      this._onArrive = null;
      this._unbounded = false;
      this._targetSpeed = this.speed;
      this._moved = false;
      this._stepIdx = 0;
    }

    get moving() { return this.state === 'walking'; }
    get hasTarget() { return this.targetGridX !== null; }
    get depth() { return this.gridX + this.gridY; }      // s = x + y
    get lateral() { return this.gridX - this.gridY; }    // d = x - y

    // Inicia o deslocamento suave, em linha reta, até a posição alvo.
    moveTo(targetGridX, targetGridY, o) {
      o = o || {};
      this.targetGridX = targetGridX;
      this.targetGridY = targetGridY;
      this._targetSpeed = o.speed || this.speed;
      this._unbounded = o.bounded === false;
      this._onArrive = o.onArrive || null;
    }

    stop() {
      this.targetGridX = null; this.targetGridY = null; this._onArrive = null;
    }

    // Movimento contínuo por teclado: (dx, dy) é a direção no grid; cancela o alvo.
    moveBy(dx, dy, dt) {
      this.stop();
      this._step(dx, dy, this.speed * dt, true);
    }

    _step(dx, dy, dist, bounded) {
      const len = Math.hypot(dx, dy);
      if (!len || dist <= 0) return;
      this.gridX += dx / len * dist;
      this.gridY += dy / len * dist;
      const sx = dx - dy;                      // direção horizontal na tela
      if (sx > 0.01) this.facing = 'R'; else if (sx < -0.01) this.facing = 'L';
      if (bounded && this.bounds) this.bounds(this);
      this._moved = true;
    }

    // Avança o alvo, atualiza o estado e o ciclo de passos; invoca onStep a cada passo.
    update(dt) {
      if (this.hasTarget) {
        const vx = this.targetGridX - this.gridX, vy = this.targetGridY - this.gridY;
        const dist = Math.hypot(vx, vy);
        if (dist < 0.06) {
          this.gridX = this.targetGridX; this.gridY = this.targetGridY;
          const cb = this._onArrive;
          this.stop();
          if (cb) cb();
        } else {
          this._step(vx, vy, Math.min(dist, this._targetSpeed * dt), !this._unbounded);
        }
      }
      if (this._moved) {
        this.state = 'walking';
        this.walkPhase += dt * 11;
        const k = Math.floor(this.walkPhase / Math.PI);
        if (k !== this._stepIdx) { this._stepIdx = k; if (this.onStep) this.onStep(); }
      } else {
        this.state = 'idle';
      }
      this._moved = false;
    }
  }

  window.AvatarManagerClass = AvatarManager;
  window.AvatarManager = new AvatarManager();
  window.Avatars = window.AvatarManager;       // alias usado pelas telas
  window.Player = Player;
})();
