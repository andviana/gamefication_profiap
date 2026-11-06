// Testes do módulo de rede e gabarito do jogo (app/static/game/js/api.js). Rodam com: node --test tests/js
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const ARQUIVO = path.join(__dirname, '..', '..', 'app', 'static', 'game', 'js', 'api.js');
const api = require(ARQUIVO);
const nodeSha = t => crypto.createHash('sha256').update(t, 'utf8').digest('hex');

// vetor compartilhado com tests/test_api_jogo.py (gerado pelo Python)
const VETOR = { sal: 'sal-de-teste', qid: 7, numero: 3, letra: 'B', esperado: 'bb081bac12b82d641a0b581b6a241a80159188fb93a490b9cc80b701c0bc2030' };

// ---------------- código ----------------
test('normalizaCodigo: maiúsculas, só letras, no máximo 5', () => {
  assert.equal(api.normalizaCodigo('kmgjt'), 'KMGJT');
  assert.equal(api.normalizaCodigo(' k m-g1 j@t '), 'KMGJT');
  assert.equal(api.normalizaCodigo('ABCDEFGH'), 'ABCDE');
  assert.equal(api.normalizaCodigo(null), '');
  assert.equal(api.normalizaCodigo(12345), '');
  assert.equal(api.codigoCompleto('ABCDE'), true);
  assert.equal(api.codigoCompleto('ABCD'), false);
});

// ---------------- SHA-256 ----------------
test('sha256Puro bate com o do Node em todos os tamanhos de borda', () => {
  const casos = ['', 'abc', 'a'.repeat(55), 'a'.repeat(56), 'a'.repeat(57), 'a'.repeat(63), 'a'.repeat(64), 'a'.repeat(65),
    'a'.repeat(119), 'a'.repeat(120), 'a'.repeat(1000), 'ação ü 日本語 😀', 'sal-de-teste73B'];
  for (const c of casos) assert.equal(api.sha256Puro(c), nodeSha(c), `tamanho ${c.length}`);
});

test('sha256Hex: o caminho com crypto.subtle e o puro dão o mesmo resultado', async () => {
  for (const c of ['', 'abc', 'Olá, mundo!']) {
    assert.equal(await api.sha256Hex(c), nodeSha(c));
    assert.equal(await api.sha256Hex(c, { forcaPuro: true }), nodeSha(c));
  }
});

test('token: mesmo vetor que o servidor calcula em Python', async () => {
  assert.equal(await api.token(VETOR.sal, VETOR.qid, VETOR.numero, VETOR.letra), VETOR.esperado);
  assert.equal(await api.token(VETOR.sal, VETOR.qid, VETOR.numero, VETOR.letra, { forcaPuro: true }), VETOR.esperado);
  assert.notEqual(await api.token(VETOR.sal, VETOR.qid, VETOR.numero, 'C'), VETOR.esperado);
});

// ---------------- montaQuiz ----------------
const tok = (sal, q, n, l) => nodeSha(`${sal}${q}${n}${l}`);
function dadosDoServidor(corretas = { 1: 'C', 2: 'A' }) {
  const sal = 'sal-x', id = 5;
  return { coleta: { codigo: 'KMGJT' }, questionario: { id, nome: 'Q', sal, orientacoes: '# Oi', perguntas: [1, 2].map(n => ({
    numero: n, titulo: `Tema ${n}`, grupo: 'Tecnologia', texto: `Enunciado ${n}?`, autoajuda: n === 1 ? 'dica' : null, token_correta: tok(sal, id, n, corretas[n]),
    alternativas: 'ABCD'.split('').map(l => ({ letra: l, texto: `Alt ${l}`, texto_acerto: l === corretas[n] ? 'Certo!' : null, texto_erro: l === corretas[n] ? null : 'Errado.' })) })) } };
}

test('montaQuiz descobre a correta por token e converte para o formato do jogo', async () => {
  const m = await api.montaQuiz(dadosDoServidor());
  assert.equal(m.codigo, 'KMGJT'); assert.equal(m.orientacoes, '# Oi'); assert.equal(m.questionarioId, 5);
  assert.deepEqual(m.quiz.map(q => q.id), [1, 2]);
  assert.deepEqual(m.quiz[0].alternatives.filter(a => a.correct).map(a => a.letter), ['C']);
  assert.deepEqual(m.quiz[1].alternatives.filter(a => a.correct).map(a => a.letter), ['A']);
  const q = m.quiz[0];
  assert.deepEqual(Object.keys(q).sort(), ['alternatives', 'group', 'hint', 'id', 'question', 'title']);
  assert.equal(q.title, 'Tema 1'); assert.equal(q.group, 'Tecnologia'); assert.equal(q.question, 'Enunciado 1?'); assert.equal(q.hint, 'dica');
  assert.equal(m.quiz[1].hint, '');                                  // sem dica -> string vazia (o jogo testa .trim())
  const c = q.alternatives[2];
  assert.deepEqual(c, { letter: 'C', text: 'Alt C', correct: true, successText: 'Certo!', errorText: '' });
  assert.equal(q.alternatives[0].errorText, 'Errado.'); assert.equal(q.alternatives[0].successText, '');
});

test('montaQuiz funciona também sem crypto.subtle', async () => {
  const m = await api.montaQuiz(dadosDoServidor(), { forcaPuro: true });
  assert.deepEqual(m.quiz[0].alternatives.filter(a => a.correct).map(a => a.letter), ['C']);
});

test('montaQuiz recusa dados inconsistentes', async () => {
  const semCorreta = dadosDoServidor(); semCorreta.questionario.perguntas[0].token_correta = 'x'.repeat(64);
  await assert.rejects(api.montaQuiz(semCorreta), /Pergunta 1 inválida/);
  const umaSo = dadosDoServidor(); umaSo.questionario.perguntas[0].alternativas.length = 1;
  await assert.rejects(api.montaQuiz(umaSo), /inválida/);
  const cinco = dadosDoServidor(); cinco.questionario.perguntas[0].alternativas.push({ letra: 'E', texto: 'x' });
  await assert.rejects(api.montaQuiz(cinco), /inválida/);
  await assert.rejects(api.montaQuiz({ questionario: { perguntas: [] } }), /sem perguntas/);
  await assert.rejects(api.montaQuiz(null), /sem perguntas/);
});

// ---------------- UUID e payload ----------------
test('novoUuid: formato v4 e únicos', () => {
  const v = new Set(); for (let i = 0; i < 200; i++) v.add(api.novoUuid());
  assert.equal(v.size, 200);
  for (const u of v) assert.match(u, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
});

test('novoUuid: plano B quando não há crypto.randomUUID', () => {
  const sandbox = { crypto: { getRandomValues: b => crypto.getRandomValues(b) }, TextEncoder, setTimeout, clearTimeout };
  vm.runInNewContext(fs.readFileSync(ARQUIVO, 'utf8'), sandbox);
  const u = sandbox.TQApi.novoUuid();
  assert.match(u, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
  const sem = { TextEncoder, setTimeout, clearTimeout }; vm.runInNewContext(fs.readFileSync(ARQUIVO, 'utf8'), sem);   // nem getRandomValues
  assert.match(sem.TQApi.novoUuid(), /^[0-9a-f-]{36}$/);
});

test('montaPayload leva só o necessário e limita o tempo', () => {
  const p = api.montaPayload('uuid-1', 'KMGJT', [
    { questionId: 1, selectedLetter: 'C', timeMs: 4321.6, order: 1, isCorrect: true, points: 100, selectedText: 'x' },
    { questionId: 2, selectedLetter: 'A', timeMs: -5, order: 2 },
    { questionId: 3, selectedLetter: 'B', timeMs: 99999999, order: 3 },
    { questionId: 4, selectedLetter: 'D', order: 4 }]);
  assert.deepEqual(Object.keys(p).sort(), ['codigo', 'respostas', 'uuid']);
  assert.deepEqual(p.respostas.map(r => r.tempo_ms), [4322, 0, 3600000, 0]);
  assert.deepEqual(Object.keys(p.respostas[0]).sort(), ['alternativa', 'ordem', 'pergunta', 'tempo_ms']);   // sem XP, nome, avatar nem "acertou"
  assert.deepEqual(p.respostas[0], { pergunta: 1, alternativa: 'C', tempo_ms: 4322, ordem: 1 });
});

// ---------------- rede ----------------
const resp = (status, json, headers = {}) => ({ status, json: async () => { if (json === undefined) throw new Error('sem json'); return json; }, headers: { get: k => headers[k] ?? null } });

test('iniciar: sucesso e o que é enviado', async () => {
  let visto;
  const fetch = async (url, init) => { visto = { url, init }; return resp(200, dadosDoServidor()); };
  const r = await api.iniciar('KMGJT', { fetch });
  assert.equal(r.ok, true); assert.equal(r.dados.coleta.codigo, 'KMGJT');
  assert.equal(visto.url, '/api/coleta/iniciar'); assert.equal(visto.init.method, 'POST');
  assert.deepEqual(JSON.parse(visto.init.body), { codigo: 'KMGJT' });
  assert.equal(visto.init.credentials, 'omit'); assert.equal(visto.init.headers['Content-Type'], 'application/json');
});

test('iniciar: erros do servidor viram motivo e mensagem', async () => {
  const erro = (status, motivo, mensagem, extra = {}) => async () => resp(status, { erro: { codigo: status, motivo, mensagem, ...extra } });
  let r = await api.iniciar('ZZZZZ', { fetch: erro(404, 'inexistente', 'Código não encontrado.') });
  assert.deepEqual([r.ok, r.motivo, r.mensagem], [false, 'inexistente', 'Código não encontrado.']);
  r = await api.iniciar('KMGJT', { fetch: erro(410, 'fora_do_prazo', 'O prazo desta coleta já terminou.') });
  assert.equal(r.motivo, 'fora_do_prazo');
  r = await api.iniciar('KMGJT', { fetch: async () => resp(429, { erro: { motivo: 'limite_excedido', mensagem: 'Muitas tentativas.', detalhes: { espera_seg: 240 } } }, { 'Retry-After': '240' }) });
  assert.deepEqual([r.motivo, r.esperaSeg], ['limite_excedido', 240]);
});

test('iniciar: falha de rede e resposta que não é JSON', async () => {
  let r = await api.iniciar('KMGJT', { fetch: async () => { throw new TypeError('Failed to fetch'); } });
  assert.deepEqual([r.ok, r.motivo, r.mensagem], [false, 'rede', api.MSG.rede]);
  r = await api.iniciar('KMGJT', { fetch: async () => resp(502, undefined) });        // página de erro do proxy
  assert.deepEqual([r.ok, r.motivo, r.mensagem], [false, 'servidor', api.MSG.servidor]);
});

test('iniciar: tempo esgotado vira erro de rede', async () => {
  const fetch = (url, init) => new Promise((_, rejeita) => init.signal.addEventListener('abort', () => rejeita(new Error('abortado'))));
  const r = await api.iniciar('KMGJT', { fetch, timeoutMs: 20 });
  assert.equal(r.motivo, 'rede');
});

test('enviarPartida: sucesso, duplicada e corpo enviado', async () => {
  const chamadas = [];
  const fetch = async (url, init) => { chamadas.push([url, JSON.parse(init.body)]); return resp(201, { salvo: true, duplicada: false }); };
  assert.deepEqual(await api.enviarPartida({ uuid: 'u', codigo: 'KMGJT', respostas: [] }, { fetch }), { ok: true, duplicada: false });
  assert.deepEqual(chamadas, [['/api/partidas', { uuid: 'u', codigo: 'KMGJT', respostas: [] }]]);
  assert.deepEqual(await api.enviarPartida({}, { fetch: async () => resp(200, { salvo: true, duplicada: true }) }), { ok: true, duplicada: true });
});

test('enviarPartida: falha de rede é repetida (2 reenvios) e depois funciona', async () => {
  let n = 0; const esperas = [];
  const fetch = async () => { n++; if (n < 3) throw new TypeError('offline'); return resp(201, { salvo: true }); };
  const r = await api.enviarPartida({}, { fetch, esperar: async ms => esperas.push(ms) });
  assert.deepEqual(r, { ok: true, duplicada: false }); assert.equal(n, 3); assert.deepEqual(esperas, [600, 1500]);
});

test('enviarPartida: esgotadas as tentativas devolve erro não definitivo', async () => {
  let n = 0;
  const r = await api.enviarPartida({}, { fetch: async () => { n++; throw new TypeError('offline'); }, esperar: async () => {} });
  assert.equal(n, 3); assert.deepEqual([r.ok, r.definitivo, r.motivo], [false, false, 'rede']);
  n = 0;
  const s = await api.enviarPartida({}, { fetch: async () => { n++; return resp(503, undefined); }, esperar: async () => {} });
  assert.equal(n, 3); assert.deepEqual([s.ok, s.definitivo, s.motivo], [false, false, 'servidor']);   // 5xx também é repetido
});

test('enviarPartida: coleta encerrada e erros 4xx são definitivos e não são repetidos', async () => {
  for (const [status, motivo] of [[410, 'coleta_encerrada'], [422, 'invalido'], [409, 'questionario_alterado'], [404, 'inexistente']]) {
    let n = 0;
    const r = await api.enviarPartida({}, { fetch: async () => { n++; return resp(status, { erro: { motivo, mensagem: `msg ${motivo}` } }); }, esperar: async () => assert.fail('não deveria esperar') });
    assert.equal(n, 1, motivo); assert.deepEqual([r.ok, r.definitivo, r.motivo, r.mensagem], [false, true, motivo, `msg ${motivo}`]);
  }
});

test('enviarPartida: 429 não é repetido na hora e não é definitivo (dá para tentar de novo depois)', async () => {
  let n = 0;
  const r = await api.enviarPartida({}, { fetch: async () => { n++; return resp(429, { erro: { motivo: 'limite_excedido', mensagem: 'Aguarde.', detalhes: { espera_seg: 120 } } }); }, esperar: async () => {} });
  assert.equal(n, 1); assert.deepEqual([r.ok, r.definitivo, r.esperaSeg], [false, false, 120]);
});

test('enviarPartida: reenvio usa o mesmo UUID em todas as tentativas', async () => {
  const uuids = [];
  let n = 0;
  await api.enviarPartida({ uuid: 'fixo-123', codigo: 'K', respostas: [] }, {
    fetch: async (u, init) => { uuids.push(JSON.parse(init.body).uuid); if (++n < 3) throw new TypeError('x'); return resp(201, {}); }, esperar: async () => {} });
  assert.deepEqual(uuids, ['fixo-123', 'fixo-123', 'fixo-123']);
});
