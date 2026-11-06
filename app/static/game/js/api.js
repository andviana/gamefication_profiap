// Comunicação do jogo com o servidor e verificação do gabarito. Sem dependência do restante do jogo, de modo que
// os mesmos arquivos rodam no navegador (window.TQApi) e nos testes em Node (tests/js/api.test.js).
//
//  - iniciar(): valida o código da turma e traz o questionário (orientações e perguntas, SEM campo "correta").
//  - montaQuiz(): descobre a alternativa correta comparando tokens (SHA-256) e devolve as perguntas no formato do jogo.
//  - enviarPartida(): grava a partida finalizada, com tentativas automáticas; o UUID torna o reenvio seguro.
(function (raiz, fabrica) {
  'use strict';
  const api = fabrica(raiz);
  if (typeof module === 'object' && module.exports) module.exports = api;
  else raiz.TQApi = api;
})(typeof window !== 'undefined' ? window : globalThis, function (raiz) {
  'use strict';

  const LETRAS_CODIGO = 'ABCDEFGHJKMNPQRSTUVWXYZ';        // as 23 letras dos códigos (sem I, L e O)
  const TAMANHO_CODIGO = 5;

  // ---------------- código da turma ----------------
  // Maiúsculas, só letras, no máximo 5 (o que o aluno digitar além disso é descartado).
  function normalizaCodigo(texto) {
    return String(texto == null ? '' : texto).toUpperCase().replace(/[^A-Z]/g, '').slice(0, TAMANHO_CODIGO);
  }
  const codigoCompleto = codigo => codigo.length === TAMANHO_CODIGO;

  // ---------------- SHA-256 ----------------
  // Versão pura em JavaScript: o navegador só oferece crypto.subtle em HTTPS ou localhost, e uma sala de aula em HTTP
  // não pode ficar sem feedback. Os dois caminhos dão o mesmo resultado (verificado nos testes).
  const K = [
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be,
    0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa,
    0x5cb0a9dc, 0x76f988da, 0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967, 0x27b70a85,
    0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3,
    0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070, 0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f,
    0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2];

  function utf8(texto) {
    if (typeof TextEncoder !== 'undefined') return new TextEncoder().encode(texto);
    const s = unescape(encodeURIComponent(texto)), b = new Uint8Array(s.length);
    for (let i = 0; i < s.length; i++) b[i] = s.charCodeAt(i);
    return b;
  }

  function sha256Puro(texto) {
    const dados = utf8(texto), n = dados.length;
    const total = (((n + 9 + 63) >> 6) << 6);                // acolchoamento: 0x80, zeros e o tamanho em bits (64 bits)
    const bloco = new Uint8Array(total);
    bloco.set(dados); bloco[n] = 0x80;
    const dv = new DataView(bloco.buffer);
    dv.setUint32(total - 8, Math.floor((n * 8) / 4294967296)); dv.setUint32(total - 4, (n * 8) >>> 0);
    const H = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19];
    const w = new Array(64);
    const rotr = (x, k) => (x >>> k) | (x << (32 - k));
    for (let off = 0; off < total; off += 64) {
      for (let i = 0; i < 16; i++) w[i] = dv.getUint32(off + i * 4);
      for (let i = 16; i < 64; i++) {
        const s0 = rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >>> 3);
        const s1 = rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >>> 10);
        w[i] = (w[i - 16] + s0 + w[i - 7] + s1) >>> 0;
      }
      let [a, b, c, d, e, f, g, h] = H;
      for (let i = 0; i < 64; i++) {
        const S1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25), ch = (e & f) ^ (~e & g);
        const t1 = (h + S1 + ch + K[i] + w[i]) >>> 0;
        const S0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22), mj = (a & b) ^ (a & c) ^ (b & c);
        const t2 = (S0 + mj) >>> 0;
        h = g; g = f; f = e; e = (d + t1) >>> 0; d = c; c = b; b = a; a = (t1 + t2) >>> 0;
      }
      H[0] = (H[0] + a) >>> 0; H[1] = (H[1] + b) >>> 0; H[2] = (H[2] + c) >>> 0; H[3] = (H[3] + d) >>> 0;
      H[4] = (H[4] + e) >>> 0; H[5] = (H[5] + f) >>> 0; H[6] = (H[6] + g) >>> 0; H[7] = (H[7] + h) >>> 0;
    }
    return H.map(x => x.toString(16).padStart(8, '0')).join('');
  }

  async function sha256Hex(texto, opcoes) {
    const subtle = raiz.crypto && raiz.crypto.subtle;
    if (subtle && !(opcoes && opcoes.forcaPuro)) {
      const hash = await subtle.digest('SHA-256', utf8(texto));
      return Array.from(new Uint8Array(hash), x => x.toString(16).padStart(2, '0')).join('');
    }
    return sha256Puro(texto);
  }

  // Mesma fórmula do servidor (app/services/gabarito.py): SHA-256(sal + questionario_id + numero + letra).
  const token = (sal, questionarioId, numero, letra, opcoes) => sha256Hex(`${sal}${questionarioId}${numero}${letra}`, opcoes);

  // ---------------- do JSON do servidor para o formato do jogo ----------------
  // Cada alternativa recebe `correct` por comparação de tokens; o resto do jogo continua usando `alt.correct`.
  async function montaQuiz(dados, opcoes) {
    const q = dados && dados.questionario;
    if (!q || !Array.isArray(q.perguntas) || q.perguntas.length === 0) throw new Error('Questionário sem perguntas.');
    const quiz = [];
    for (const p of q.perguntas) {
      const alternativas = [];
      for (const a of p.alternativas) {
        const t = await token(q.sal, q.id, p.numero, a.letra, opcoes);
        alternativas.push({ letter: a.letra, text: a.texto, correct: t === p.token_correta,
          successText: a.texto_acerto || '', errorText: a.texto_erro || '' });
      }
      const corretas = alternativas.filter(a => a.correct).length;
      if (alternativas.length < 2 || alternativas.length > 4 || corretas !== 1) throw new Error(`Pergunta ${p.numero} inválida.`);
      quiz.push({ id: p.numero, title: p.titulo, question: p.texto, group: p.grupo, hint: p.autoajuda || '', alternatives: alternativas });
    }
    return { quiz, orientacoes: q.orientacoes || '', codigo: dados.coleta && dados.coleta.codigo, questionarioId: q.id };
  }

  // ---------------- UUID da partida ----------------
  function novoUuid() {
    const c = raiz.crypto;
    if (c && typeof c.randomUUID === 'function') return c.randomUUID();
    const b = new Uint8Array(16);
    if (c && typeof c.getRandomValues === 'function') c.getRandomValues(b); else for (let i = 0; i < 16; i++) b[i] = Math.floor(Math.random() * 256);
    b[6] = (b[6] & 0x0f) | 0x40; b[8] = (b[8] & 0x3f) | 0x80;      // versão 4
    const h = Array.from(b, x => x.toString(16).padStart(2, '0')).join('');
    return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
  }

  // Histórico do jogo -> corpo do POST /api/partidas. Não leva XP, nome, avatar nem o "acertou": o servidor recalcula.
  function montaPayload(uuid, codigo, historico) {
    return { uuid, codigo, respostas: historico.map(h => ({
      pergunta: h.questionId, alternativa: h.selectedLetter, tempo_ms: Math.max(0, Math.min(3600000, Math.round(h.timeMs || 0))), ordem: h.order })) };
  }

  // ---------------- chamadas ao servidor ----------------
  const MSG = {
    rede: 'Sem conexão com o servidor. Verifique a internet e tente de novo.',
    servidor: 'O servidor não respondeu direito. Tente de novo em instantes.',
  };

  async function chamar(url, corpo, opcoes) {
    const f = (opcoes && opcoes.fetch) || raiz.fetch.bind(raiz);
    const limite = (opcoes && opcoes.timeoutMs) || 8000;
    const controle = typeof AbortController !== 'undefined' ? new AbortController() : null;
    const timer = controle ? setTimeout(() => controle.abort(), limite) : null;
    try {
      const resposta = await f(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(corpo),
        credentials: 'omit', cache: 'no-store', signal: controle ? controle.signal : undefined });
      let json = null;
      try { json = await resposta.json(); } catch (e) { /* corpo não é JSON (por exemplo, página de erro do proxy) */ }
      return { status: resposta.status, ok: resposta.status >= 200 && resposta.status < 300, json, retryAfter: Number(resposta.headers && resposta.headers.get && resposta.headers.get('Retry-After')) || 0 };
    } catch (e) {
      return { status: 0, ok: false, json: null, rede: true };        // sem rede, DNS, timeout ou aborto
    } finally { if (timer) clearTimeout(timer); }
  }

  function descreveErro(r) {
    const erro = r.json && r.json.erro;
    if (r.rede) return { motivo: 'rede', mensagem: MSG.rede };
    if (!erro) return { motivo: 'servidor', mensagem: MSG.servidor };
    return { motivo: erro.motivo, mensagem: erro.mensagem, esperaSeg: (erro.detalhes && erro.detalhes.espera_seg) || r.retryAfter || 0 };
  }

  // Valida o código. Devolve { ok: true, dados } ou { ok: false, motivo, mensagem, esperaSeg? }.
  async function iniciar(codigo, opcoes) {
    const r = await chamar('/api/coleta/iniciar', { codigo }, opcoes);
    if (r.ok && r.json && r.json.questionario) return { ok: true, dados: r.json };
    return { ok: false, ...descreveErro(r) };
  }

  const dormir = ms => new Promise(ok => setTimeout(ok, ms));

  // Grava a partida. Tenta até `tentativas` vezes em falha de rede ou de servidor (5xx); erros do tipo "coleta encerrada"
  // (4xx) são definitivos. O UUID da partida garante que reenviar nunca duplica. Devolve
  // { ok: true, duplicada } ou { ok: false, motivo, mensagem, definitivo }.
  async function enviarPartida(payload, opcoes) {
    const o = opcoes || {};
    const atrasos = o.atrasos || [600, 1500];
    const espera = o.esperar || dormir;
    const tentativas = o.tentativas || atrasos.length + 1;
    let ultimo = null;
    for (let i = 0; i < tentativas; i++) {
      const r = await chamar('/api/partidas', payload, o);
      if (r.ok) return { ok: true, duplicada: !!(r.json && r.json.duplicada) };
      ultimo = r;
      const transitorio = r.rede || r.status >= 500;
      if (!transitorio) break;                                         // 4xx não melhora insistindo
      if (i < tentativas - 1) await espera(atrasos[Math.min(i, atrasos.length - 1)]);
    }
    const d = descreveErro(ultimo);
    const definitivo = !(ultimo.rede || ultimo.status >= 500 || ultimo.status === 429);
    return { ok: false, definitivo, ...d };
  }

  return { LETRAS_CODIGO, TAMANHO_CODIGO, normalizaCodigo, codigoCompleto, sha256Hex, sha256Puro, token, montaQuiz, novoUuid, montaPayload,
    iniciar, enviarPartida, MSG };
});
