// Dashboard (Fase 6c). Cada render consome um endpoint de /admin/api/dashboard/*; as contas ficam no servidor.
// Rótulos vindos do banco entram no DOM com textContent; o único innerHTML é o dos tooltips, sempre com esc().
(function () {
  'use strict';

  /* ---------- tokens (espelham o CSS) ---------- */
  const C = {
    acerto: '#1351b4', erro: '#e66f0e', ctx: '#98afd2', ctxErro: '#f3bf90',
    ink: '#333333', ink2: '#555555', muted: '#636363', grid: '#e6e6e6', axis: '#cccccc', surface: '#ffffff', border: '#dcdcdc',
  };
  const RAMPA_ERRO = ['#fdf5e6', '#fce2c5', '#ffbc78', '#e66f0e', '#c05600', '#8c471c', '#5f3617'];
  const FONTE = 'Rawline, Raleway, "Segoe UI", system-ui, sans-serif';
  const BASE = document.getElementById('dash').dataset.api;

  /* ---------- utilitários ---------- */
  const nf0 = new Intl.NumberFormat('pt-BR');
  const nf1 = new Intl.NumberFormat('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const fr = p => (p == null ? 0 : p / 100);                       // a API devolve percentuais (0-100); os gráficos usam fração
  const pct0 = v => Math.round(v * 100).toLocaleString('pt-BR') + '%';
  const pct1 = v => nf1.format(v * 100) + '%';
  const seg = ms => (ms == null ? '–' : nf1.format(ms / 1000) + ' s');
  const esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const $ = id => document.getElementById(id);
  const dataBR = iso => iso.slice(8, 10) + '/' + iso.slice(5, 7) + '/' + iso.slice(0, 4);

  /* ---------- estado ---------- */
  const CHAVES = ['coleta', 'campus', 'curso', 'ano', 'periodo', 'grupo', 'questao'];
  const NOMES_FILTRO = { coleta: 'Coleta', campus: 'Campus', curso: 'Curso', ano: 'Ano', periodo: 'Período', grupo: 'Grupo', questao: 'Questão' };
  const DIMS = { campus: 'Campus', curso: 'Curso', ano: 'Ano', periodo: 'Período' };
  const f = Object.fromEntries(CHAVES.concat(['dias', 'de', 'ate']).map(k => [k, '']));
  const ui = { quest: '', gran: 'semana', ordem: 'erro', dim: 'campus', aba: 'questao', busca: '', sort: null, decal: false, custom: false };
  let cartoes = [], opts = null, D = null, seq = 0;
  const haFiltro = () => CHAVES.some(k => f[k]) || !!(f.dias || f.de || f.ate);
  const nomeQuest = () => (cartoes.find(c => String(c.id) === ui.quest) || {}).nome || '';

  /* ---------- API ---------- */
  function params(extra, semFiltros) {
    const p = new URLSearchParams({ questionario: ui.quest });
    if (!semFiltros) Object.entries(f).forEach(([k, v]) => v && p.set(k, v));
    Object.entries(extra || {}).forEach(([k, v]) => p.set(k, v));
    return p;
  }
  async function api(caminho, extra, semFiltros) {
    const url = BASE + '/' + caminho + (caminho === 'questionarios' ? '' : '?' + params(extra, semFiltros));
    let r;
    try { r = await fetch(url, { credentials: 'same-origin', headers: { Accept: 'application/json' } }); }
    catch (e) { throw new Error('Sem conexão com o servidor. Verifique a rede e tente de novo.'); }
    if (r.status === 401) { location.reload(); throw new Error('Sessão expirada.'); }
    let corpo = null; try { corpo = await r.json(); } catch (e) { /* resposta sem JSON */ }
    if (!r.ok) throw new Error((corpo && corpo.erro && corpo.erro.mensagem) || 'Não foi possível carregar os dados (' + r.status + ').');
    return corpo;
  }
  function mostraErro(msg) { $('erro-api-texto').textContent = msg || ''; $('erro-api').hidden = !msg; }

  /* ---------- gráficos ---------- */
  const charts = {}, ultimo = {};
  function chart(id) {
    if (!charts[id]) {
      charts[id] = echarts.init($(id), null, { renderer: 'canvas' });
      new ResizeObserver(() => charts[id].resize()).observe($(id));
    }
    return charts[id];
  }
  const aria = () => ({ enabled: true, label: { enabled: false }, decal: { show: ui.decal } });
  const tooltipBase = { confine: true, backgroundColor: C.surface, borderColor: C.border, borderWidth: 1, padding: [8, 12], textStyle: { color: C.ink, fontFamily: FONTE, fontSize: 13 }, extraCssText: 'box-shadow:0 4px 14px rgba(0,0,0,.12);border-radius:6px;' };
  const eixoTexto = { color: C.muted, fontFamily: FONTE, fontSize: 12 };
  const textoVazio = () => (haFiltro() ? 'Nenhuma resposta para este filtro' : 'Este questionário ainda não tem respostas');
  const vazioGrafico = ch => ch.setOption({ aria: aria(), series: [], xAxis: { show: false }, yAxis: { show: false }, grid: { show: false }, visualMap: [], legend: { show: false }, tooltip: { show: false },
    graphic: [{ type: 'text', left: 'center', top: 'middle', style: { text: textoVazio(), fill: C.muted, font: '14px ' + FONTE } }] }, true);
  const linhaTip = (cor, rot, val) => '<div style="display:flex;gap:8px;align-items:center;margin-top:3px"><span style="width:12px;height:3px;background:' + cor + ';display:inline-block;border-radius:2px"></span><span style="color:' + C.ink2 + '">' + esc(rot) + '</span><b style="margin-left:auto;padding-left:14px;font-size:14px">' + esc(val) + '</b></div>';

  const mob = () => window.innerWidth <= 640;
  const cortaRot = (t, n) => (mob() && t.length > n ? t.slice(0, n - 1) + '…' : t);
  const escalaMax = it => Math.min(1, Math.max(0.2, Math.ceil(Math.max(...it.map(i => i.v)) * 10 + 1) / 10));
  const rotBarra = i => pct0(i.v) + ' · ' + nf0.format(i.n) + ' resp.';

  function barrasH(id, itens, o) {
    const ch = chart(id);
    ultimo[id] = itens;
    if (!itens.length) return vazioGrafico(ch);
    ch.setOption({
      aria: aria(), animationDuration: 250, graphic: [],
      grid: { left: 8, right: mob() ? 58 : (o.dir || 124), top: o.top || 6, bottom: 22, containLabel: true },
      tooltip: { ...tooltipBase, trigger: 'item', formatter: p => o.tip(itens[p.dataIndex]) },
      xAxis: { type: 'value', min: 0, max: o.max || escalaMax(itens), splitNumber: mob() ? 2 : 4, axisLine: { show: false }, axisTick: { show: false }, axisLabel: { ...eixoTexto, formatter: v => Math.round(v * 100) + '%' }, splitLine: { lineStyle: { color: C.grid } } },
      yAxis: { type: 'category', inverse: true, data: itens.map(i => i.nome), axisTick: { show: false }, axisLine: { lineStyle: { color: C.axis } }, axisLabel: { ...eixoTexto, color: C.ink2, width: mob() ? 104 : (o.larg || 170), overflow: 'truncate' } },
      series: [{ type: 'bar', barWidth: 18, cursor: 'pointer', data: itens.map(i => ({ value: i.v, itemStyle: { color: i.cor, borderRadius: [0, 4, 4, 0] } })),
        label: { show: true, position: 'right', color: C.ink, fontFamily: FONTE, fontSize: 12, formatter: p => mob() ? pct0(itens[p.dataIndex].v) : o.rot(itens[p.dataIndex]) },
        emphasis: { itemStyle: { opacity: .82 } }, ...(o.extra || {}) }],
    }, true);
  }

  /* visão em tabela de cada gráfico (gêmea acessível) */
  const vistas = {};
  function registraVista(cardId, cols, rows) { vistas[cardId] = { cols, rows }; if ($('card-' + cardId).classList.contains('modo-tabela')) montaVista(cardId); }
  function montaVista(cardId) {
    const { cols, rows } = vistas[cardId]; const alvo = $('vt-' + cardId); alvo.textContent = '';
    alvo.appendChild(tabelaDOM(cols, rows, { caption: 'Dados do gráfico' }));
  }
  function tabelaDOM(cols, rows, o = {}) {
    const t = document.createElement('table'); t.className = 'dados';
    if (o.caption) { const c = document.createElement('caption'); c.className = 'sr-only'; c.style.cssText = 'position:absolute;left:-9999px'; c.textContent = o.caption; t.appendChild(c); }
    const th = t.createTHead().insertRow();
    cols.forEach(c => {
      const h = document.createElement('th'); h.scope = 'col'; if (c.esq) h.className = 'esq';
      if (o.ordenavel) {
        const b = document.createElement('button'); b.type = 'button'; b.textContent = c.t;
        const ic = document.createElement('i'); ic.className = 'fas fa-sort'; ic.style.cssText = 'font-size:11px;color:#888';
        if (ui.sort && ui.sort.id === c.id) { ic.className = 'fas fa-sort-' + (ui.sort.dir > 0 ? 'up' : 'down'); ic.style.color = C.acerto; h.setAttribute('aria-sort', ui.sort.dir > 0 ? 'ascending' : 'descending'); }
        b.appendChild(ic);
        b.addEventListener('click', () => { ui.sort = ui.sort && ui.sort.id === c.id ? { id: c.id, dir: -ui.sort.dir } : { id: c.id, dir: c.esq ? 1 : -1 }; renderTabela(); });
        h.appendChild(b);
      } else h.textContent = c.t;
      th.appendChild(h);
    });
    const tb = t.createTBody();
    rows.forEach(r => {
      const tr = tb.insertRow(); if (r._sel) tr.className = 'sel';
      cols.forEach(c => { const td = tr.insertCell(); if (c.esq) td.className = 'esq'; const v = c.fmt ? c.fmt(r) : r[c.id]; if (v instanceof Node) td.appendChild(v); else td.textContent = v; });
    });
    if (o.rodape) { const tr = t.createTFoot().insertRow(); cols.forEach(c => { const td = tr.insertCell(); if (c.esq) td.className = 'esq'; const v = o.rodape[c.id]; td.textContent = v == null ? '' : v; }); }
    return t;
  }

  /* ---------- renders ---------- */
  function renderKPIs() {
    const t = D.resumo, g = D.resumo.geral, tem = t.respostas > 0;
    $('k-acerto').textContent = tem ? pct1(fr(t.pct_acerto)) : '–';
    $('k-meter').style.width = tem ? t.pct_acerto.toFixed(1) + '%' : '0';
    const dl = $('k-delta'); dl.textContent = '';
    if (!tem) dl.textContent = haFiltro() ? 'Sem respostas neste recorte' : 'Sem respostas neste questionário';
    else if (!haFiltro() || g.pct_acerto == null) dl.textContent = 'Base geral, sem filtros';
    else {
      const pp = t.pct_acerto - g.pct_acerto; const ic = document.createElement('i');
      ic.className = 'fas ' + (Math.abs(pp) < 0.05 ? 'fa-equals' : pp > 0 ? 'fa-arrow-up' : 'fa-arrow-down'); ic.setAttribute('aria-hidden', 'true');
      dl.append(ic, (pp > 0 ? '+' : '') + nf1.format(pp) + ' p.p. vs. geral (' + pct1(fr(g.pct_acerto)) + ')');
    }
    $('k-resp').textContent = nf0.format(t.respondentes);
    $('k-respostas').textContent = nf0.format(t.respostas);
    const nq = D.nQuestoes; $('k-qtd-q').textContent = nq + (nq === 1 ? ' questão' : ' questões');
    $('k-acertos').textContent = nf0.format(t.acertos);
    $('k-acertos-p').textContent = tem ? pct1(fr(t.pct_acerto)) + ' das respostas' : '';
    $('k-erros').textContent = nf0.format(t.erros);
    $('k-erros-p').textContent = tem ? pct1(fr(t.pct_erro)) + ' das respostas' : '';
    $('k-tempo').textContent = tem ? seg(t.tempo_mediano_ms) : '–';
    $('resumo-recorte').textContent = nomeQuest() + ' · ' + (tem ? nf0.format(t.respondentes) + ' partidas · ' + nf0.format(t.respostas) + ' respostas' : textoVazio());
  }

  function renderQuestoes() {
    const acerto = ui.ordem === 'acerto';
    const todas = D.questoes.itens.slice();
    if (acerto) todas.sort((a, b) => b.pct_acerto - a.pct_acerto || a.numero - b.numero);
    const arr = todas.slice(0, 10);
    $('t-questoes').textContent = acerto ? 'Questões com maior % de acerto' : 'Questões com maior % de erro';
    $('s-questoes').textContent = 'Todas as questões do recorte' + (f.questao ? ' · Q' + f.questao + ' em destaque' : ' · clique numa barra para filtrar');
    const itens = arr.map(o => {
      const sel = f.questao === String(o.numero); const v = fr(acerto ? o.pct_acerto : o.pct_erro);
      const cor = acerto ? (f.questao && !sel ? C.ctx : C.acerto) : (f.questao && !sel ? C.ctxErro : C.erro);
      return { num: o.numero, nome: o.rotulo, v, n: o.respostas, cor, o };
    });
    barrasH('g-questoes', itens, {
      larg: 190, rot: rotBarra,
      tip: i => '<b>' + esc(i.nome) + '</b><div style="color:' + C.muted + ';font-size:12px">' + esc(i.o.grupo) + '</div>' +
        linhaTip(C.erro, '% de erro', pct1(fr(i.o.pct_erro))) + linhaTip(C.acerto, '% de acerto', pct1(fr(i.o.pct_acerto))) + linhaTip(C.muted, 'Respostas', nf0.format(i.n)),
    });
    registraVista('questoes', [{ id: 'nome', t: 'Questão', esq: true }, { id: 'v', t: acerto ? '% acerto' : '% erro', fmt: r => pct1(r.v) }, { id: 'n', t: 'Respostas', fmt: r => nf0.format(r.n) }], itens);
  }

  function renderGrupos() {
    const itens = D.grupos.itens.map(o => ({ nome: o.rotulo, v: fr(o.pct_erro), n: o.respostas, o, cor: f.grupo && f.grupo !== o.rotulo ? C.ctxErro : C.erro }));
    $('s-grupos').textContent = 'Erros ÷ respostas de cada grupo' + (f.grupo ? ' · ' + f.grupo + ' em destaque' : ' · clique para filtrar');
    barrasH('g-grupos', itens, { larg: 130, rot: rotBarra,
      tip: i => '<b>' + esc(i.nome) + '</b>' + linhaTip(C.erro, '% de erro', pct1(fr(i.o.pct_erro))) + linhaTip(C.acerto, '% de acerto', pct1(fr(i.o.pct_acerto))) + linhaTip(C.muted, 'Respostas', nf0.format(i.n)) });
    registraVista('grupos', [{ id: 'nome', t: 'Grupo', esq: true }, { id: 'v', t: '% erro', fmt: r => pct1(r.v) }, { id: 'n', t: 'Respostas', fmt: r => nf0.format(r.n) }], itens);
  }

  const natural = dim => dim === 'ano' || dim === 'periodo';
  function renderComparativo() {
    const dim = ui.dim, nome = DIMS[dim], media = fr(D.comp.media_pct_erro);
    const lista = D.comp.itens.slice(); if (natural(dim)) lista.sort((a, b) => a.id - b.id);
    $('s-comp').textContent = '% de erro por ' + nome.toLowerCase() + ' · linha = média do recorte' + (f[dim] ? ' · seleção em destaque' : '');
    const itens = lista.map(o => ({ nome: o.rotulo, chave: String(o.id), v: fr(o.pct_erro), n: o.respostas, o, cor: f[dim] && f[dim] !== String(o.id) ? C.ctxErro : C.erro }));
    barrasH('g-comp', itens, { larg: 150, top: 24, rot: rotBarra,
      tip: i => '<b>' + esc(i.nome) + '</b>' + linhaTip(C.erro, '% de erro', pct1(i.v)) + linhaTip(C.muted, 'Média do recorte', pct1(media)) + linhaTip(C.muted, 'Respondentes', nf0.format(i.o.respondentes)) + linhaTip(C.muted, 'Respostas', nf0.format(i.n)),
      extra: { markLine: { silent: true, symbol: 'none', lineStyle: { color: C.ink2, width: 1, type: 'solid' }, label: { formatter: 'média ' + pct0(media), color: C.ink2, fontFamily: FONTE, fontSize: 11, position: 'start', distance: 4 }, data: [{ xAxis: media }] } },
    });
    registraVista('comp', [{ id: 'nome', t: nome, esq: true }, { id: 'v', t: '% erro', fmt: r => pct1(r.v) }, { id: 'resp', t: 'Respondentes', fmt: r => nf0.format(r.o.respondentes) }, { id: 'n', t: 'Respostas', fmt: r => nf0.format(r.n) }], itens);
  }

  function renderHeat() {
    const dim = ui.dim, nome = DIMS[dim], h = D.heat;
    $('heat-dim').textContent = nome.toLowerCase();
    $('s-heat').textContent = '% de erro por célula · n no tooltip' + (f.grupo || f[dim] ? ' · seleção em destaque' : ' · clique numa célula para filtrar');
    const ch = chart('g-heat');
    const colunas = h.colunas.slice(); if (natural(dim)) colunas.sort((a, b) => a.id - b.id);
    if (!colunas.length) { ultimo['g-heat'] = []; return vazioGrafico(ch); }
    const grupos = (opts.grupo || []).filter(g => h.grupos.includes(g));
    const m = new Map(h.celulas.map(c => [c.grupo + '|' + c.id, c]));
    const data = []; let maxV = 0;
    grupos.forEach((g, yi) => colunas.forEach((x, xi) => { const c = m.get(g + '|' + x.id); if (!c) return; const v = fr(c.pct_erro); maxV = Math.max(maxV, v); data.push({ xi, yi, g, x: String(x.id), rot: x.rotulo, c, v }); }));
    maxV = Math.max(0.5, Math.ceil(maxV * 10) / 10);
    ultimo['g-heat'] = data;
    ch.setOption({
      aria: aria(), animationDuration: 250, graphic: [],
      grid: { left: 8, right: 12, top: 8, bottom: 62, containLabel: true },
      tooltip: { ...tooltipBase, trigger: 'item', formatter: p => { const i = data[p.dataIndex]; return '<b>' + esc(i.g) + ' · ' + esc(i.rot) + '</b>' + linhaTip(C.erro, '% de erro', pct1(i.v)) + linhaTip(C.muted, 'Erros / respostas', nf0.format(i.c.erros) + ' / ' + nf0.format(i.c.respostas)); } },
      xAxis: { type: 'category', data: colunas.map(x => mob() ? (dim === 'periodo' ? x.rotulo.slice(0, 2) : cortaRot(x.rotulo, 7)) : x.rotulo), position: 'top', splitArea: { show: false }, axisTick: { show: false }, axisLine: { show: false }, axisLabel: { ...eixoTexto, color: C.ink2, interval: 0, width: mob() ? 58 : 96, overflow: 'break', lineHeight: 14, fontSize: mob() ? 11 : 12 } },
      yAxis: { type: 'category', data: grupos, inverse: true, axisTick: { show: false }, axisLine: { show: false }, axisLabel: { ...eixoTexto, color: C.ink2, width: mob() ? 84 : 120, overflow: 'break', fontSize: mob() ? 11 : 12 } },
      visualMap: { type: 'continuous', min: 0, max: maxV, dimension: 2, orient: 'horizontal', left: 'center', bottom: 6, itemWidth: 12, itemHeight: 200, calculable: false, text: ['mais erro', 'menos erro'], textStyle: { color: C.ink2, fontFamily: FONTE, fontSize: 12 }, formatter: v => pct0(v), inRange: { color: RAMPA_ERRO.slice(1) } },
      series: [{ type: 'heatmap', cursor: 'pointer',
        data: data.map(i => {
          const sel = f.grupo === i.g && f[dim] === i.x; const outra = (f.grupo && f.grupo !== i.g) || (f[dim] && f[dim] !== i.x);
          return { value: [i.xi, i.yi, i.v], itemStyle: { borderColor: sel ? C.ink : C.surface, borderWidth: sel ? 3 : 2, borderRadius: 3, opacity: outra ? 0.55 : 1 },
            label: { show: true, formatter: pct0(i.v), color: (!outra && i.v / maxV > 0.5) ? '#ffffff' : C.ink, fontFamily: FONTE, fontSize: 13, fontWeight: 600 } };
        }),
        emphasis: { itemStyle: { borderColor: C.ink, borderWidth: 2 } } }],
    }, true);
    registraVista('heat', [{ id: 'g', t: 'Grupo', esq: true }, { id: 'x', t: nome, esq: true, fmt: r => r.rot }, { id: 'p', t: '% erro', fmt: r => pct1(r.v) }, { id: 'n', t: 'Respostas', fmt: r => nf0.format(r.c.respostas) }], data);
  }

  function renderDetalhe() {
    const ch = chart('g-det'), q = D.det;
    if (!q || !q.respostas) { $('det-enunciado').textContent = ''; $('det-stats').textContent = ''; $('det-alts').textContent = ''; $('s-det').textContent = ''; $('t-det').textContent = 'Detalhe da questão'; ultimo['g-det'] = []; return vazioGrafico(ch); }
    $('t-det').textContent = 'Detalhe da questão Q' + q.numero + ' · ' + q.titulo;
    $('s-det').textContent = (f.questao ? 'Questão selecionada' : 'Questão com maior % de erro no recorte (clique numa barra acima para escolher outra)') + ' · ' + q.grupo;
    const en = $('det-enunciado'); en.textContent = ''; const sm = document.createElement('small'); sm.textContent = 'Enunciado'; en.append(sm, q.enunciado);
    const st = $('det-stats'); st.textContent = '';
    [['% de erro', pct1(fr(q.pct_erro))], ['% de acerto', pct1(fr(q.pct_acerto))], ['Respostas', nf0.format(q.respostas)], ['Tempo mediano', seg(q.tempo_mediano_ms)]].forEach(([k, v]) => {
      const s = document.createElement('span'); s.append(k + ': '); const b = document.createElement('b'); b.textContent = v; s.appendChild(b); st.appendChild(s); });
    const lista = $('det-alts'); lista.textContent = '';
    q.alternativas.forEach(a => { const li = document.createElement('li'); li.textContent = (a.correta ? '✓ ' : '✗ ') + a.letra + '. ' + a.texto; lista.appendChild(li); });
    const itens = q.alternativas.map(a => ({ nome: (a.correta ? '✓ ' : '✗ ') + a.letra + '. ' + a.texto, letra: a.letra, texto: a.texto, correta: a.correta, n: a.escolhas, v: fr(a.pct), cor: a.correta ? C.acerto : C.erro }));
    const maxV = Math.max(0.5, Math.ceil(Math.max(...itens.map(i => i.v)) * 10) / 10);
    barrasH('g-det', itens, { max: maxV, larg: 420, dir: 130, rot: rotBarra,
      tip: i => '<b>' + (i.correta ? '✓ Correta' : '✗ Incorreta') + ' · alternativa ' + esc(i.letra) + '</b><div style="max-width:320px;white-space:normal;color:' + C.ink2 + ';margin:2px 0 4px">' + esc(i.texto) + '</div>' + linhaTip(i.cor, 'Escolhida por', pct1(i.v)) + linhaTip(C.muted, 'Respostas', nf0.format(i.n)) });
    registraVista('det', [{ id: 'letra', t: 'Alt.', esq: true }, { id: 'texto', t: 'Texto', esq: true }, { id: 'c', t: 'Resultado', esq: true, fmt: r => r.correta ? '✓ Correta' : '✗ Incorreta' }, { id: 'v', t: '% escolhida', fmt: r => pct1(r.v) }, { id: 'n', t: 'Respostas', fmt: r => nf0.format(r.n) }], itens);
  }

  function renderEvolucao() {
    const ch = chart('g-evo'), sem = ui.gran === 'semana';
    document.querySelectorAll('#card-evo [data-gran]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.gran === ui.gran)));
    $('t-evo').textContent = sem ? 'Partidas por semana' : 'Partidas por dia';
    const out = D.evo.pontos.map(p => [p.inicio, p.partidas]);
    ultimo['g-evo'] = out;
    if (!out.length) { $('s-evo').textContent = ''; return vazioGrafico(ch); }
    const pico = out.reduce((a, b) => b[1] > a[1] ? b : a);
    $('s-evo').textContent = 'Partidas finalizadas ' + (sem ? 'em cada semana (a partir da segunda-feira)' : 'em cada dia') + ' · pico: ' + nf0.format(pico[1]) + ' em ' + (sem ? 'semana de ' : '') + dataBR(pico[0]);
    const rot = k => (sem ? 'Semana de ' : '') + dataBR(k);
    ch.setOption({
      aria: aria(), animationDuration: 250, graphic: [],
      grid: { left: 8, right: 40, top: 24, bottom: 8, containLabel: true },
      tooltip: { ...tooltipBase, trigger: 'axis', axisPointer: { type: 'line', lineStyle: { color: C.axis, width: 1 } }, formatter: ps => '<b>' + rot(ps[0].axisValue) + '</b>' + linhaTip(C.acerto, 'Partidas', nf0.format(ps[0].value)) },
      xAxis: { type: 'category', data: out.map(x => x[0]), boundaryGap: false, axisTick: { show: false }, axisLine: { lineStyle: { color: C.axis } }, axisLabel: { ...eixoTexto, formatter: v => v.slice(8, 10) + '/' + v.slice(5, 7), hideOverlap: true } },
      yAxis: { type: 'value', minInterval: 1, axisLine: { show: false }, axisTick: { show: false }, axisLabel: eixoTexto, splitLine: { lineStyle: { color: C.grid } } },
      series: [{ type: 'line', data: out.map(x => x[1]), smooth: false, showSymbol: sem, showAllSymbol: true, symbol: 'circle', symbolSize: 8, lineStyle: { width: 2, color: C.acerto, cap: 'round', join: 'round' }, itemStyle: { color: C.acerto, borderColor: C.surface, borderWidth: 2 },
        areaStyle: { color: C.acerto, opacity: 0.1 }, emphasis: { focus: 'none' }, endLabel: { show: true, formatter: p => nf0.format(p.value), color: C.ink, fontFamily: FONTE, fontSize: 12 } }],
    }, true);
    registraVista('evo', [{ id: 'd', t: sem ? 'Semana de' : 'Dia', esq: true, fmt: r => dataBR(r[0]) }, { id: 'n', t: 'Partidas', fmt: r => nf0.format(r[1]) }], out);
  }

  /* tabela de dados (obrigatória) */
  const abaApi = () => (ui.aba === 'dim' ? ui.dim : ui.aba);
  function linhasTabela() {
    const t = D.tab, a = abaApi();
    const linhas = t.itens.map(o => ({
      nome: a === 'questao' ? 'Q' + o.numero : o.rotulo, titulo: o.titulo, grupo: o.grupo,
      resp: o.respondentes, n: o.respostas, ok: o.acertos, erro: o.erros, pAc: fr(o.pct_acerto), pEr: fr(o.pct_erro), tempo: o.tempo_mediano_ms,
      _sel: a === 'questao' ? f.questao === String(o.numero) : a === 'grupo' ? f.grupo === o.rotulo : f[a] === String(o.id) }));
    return { linhas, tot: t.totais };
  }
  function colsTabela() {
    const barra = r => { const w = document.createElement('span'); const b = document.createElement('span'); b.className = 'barrinha'; b.setAttribute('aria-hidden', 'true'); const i = document.createElement('span'); i.style.width = (r.pEr * 100) + '%'; b.appendChild(i); w.append(b, pct1(r.pEr)); return w; };
    const lead = ui.aba === 'questao' ? [{ id: 'nome', t: 'Nº', esq: true }, { id: 'titulo', t: 'Título', esq: true }, { id: 'grupo', t: 'Grupo', esq: true }]
      : [{ id: 'nome', t: ui.aba === 'grupo' ? 'Grupo' : DIMS[ui.dim], esq: true }];
    return lead.concat([{ id: 'resp', t: 'Respondentes', fmt: r => nf0.format(r.resp) }, { id: 'n', t: 'Respostas', fmt: r => nf0.format(r.n) }, { id: 'ok', t: 'Acertos', fmt: r => nf0.format(r.ok) }, { id: 'erro', t: 'Erros', fmt: r => nf0.format(r.erro) },
      { id: 'pAc', t: '% acerto', fmt: r => (r.n ? pct1(r.pAc) : '–') }, { id: 'pEr', t: '% erro', fmt: r => (r.n ? barra(r) : '–') }, { id: 'tempo', t: 'Tempo mediano', fmt: r => seg(r.tempo) }]);
  }
  function renderTabs() {
    const tabs = $('tabs'); tabs.textContent = '';
    [['questao', 'Por questão'], ['grupo', 'Por grupo'], ['dim', 'Por ' + DIMS[ui.dim].toLowerCase()]].forEach(([id, t]) => {
      const b = document.createElement('button'); b.type = 'button'; b.setAttribute('role', 'tab'); b.setAttribute('aria-selected', String(ui.aba === id)); b.textContent = t;
      b.addEventListener('click', () => { ui.aba = id; ui.sort = null; renderTabs(); carrega({ soTabela: true }); }); tabs.appendChild(b);
    });
  }
  function renderTabela() {
    const alvo = $('tabela'); alvo.textContent = '';
    if (!D || !D.tab) return;
    const { linhas, tot } = linhasTabela(), cols = colsTabela();
    if (!tot.respostas) {
      const e = document.createElement('div'); e.className = 'vazio'; const i = document.createElement('i'); i.className = 'fas fa-inbox'; i.setAttribute('aria-hidden', 'true');
      const d = document.createElement('div'); d.textContent = textoVazio() + '.'; e.append(i, d);
      if (haFiltro()) { const b = document.createElement('button'); b.className = 'limpar'; b.type = 'button'; b.textContent = 'Limpar filtros'; b.onclick = limpar; e.appendChild(b); }
      alvo.appendChild(e); return;
    }
    let v = linhas;
    if (ui.busca) { const b = ui.busca.toLowerCase(); v = v.filter(r => [r.nome, r.titulo, r.grupo].filter(Boolean).join(' ').toLowerCase().includes(b)); }
    const s = ui.sort || { id: 'pEr', dir: -1 };
    v = v.slice().sort((a, b) => { const x = a[s.id], y = b[s.id]; return (typeof x === 'string' ? x.localeCompare(y, 'pt-BR', { numeric: true }) : (x ?? -1) - (y ?? -1)) * s.dir; });
    const rodape = { nome: 'Total do recorte', resp: nf0.format(tot.respondentes), n: nf0.format(tot.respostas), ok: nf0.format(tot.acertos), erro: nf0.format(tot.erros), pAc: pct1(fr(tot.pct_acerto)), pEr: pct1(fr(tot.pct_erro)), tempo: seg(tot.tempo_mediano_ms) };
    alvo.appendChild(tabelaDOM(cols, v, { ordenavel: true, rodape, caption: 'Tabela de dados do recorte' }));
    if (ui.busca && !v.length) { const p = document.createElement('p'); p.className = 'rodape-nota'; p.textContent = 'Nenhuma linha corresponde à busca.'; alvo.appendChild(p); }
  }
  function exportarCSV() { location.href = BASE + '/export.csv?' + params({ aba: abaApi() }); }

  function baixaPNG(id) {
    const ch = charts[id]; if (!ch) return;
    const a = document.createElement('a'); a.href = ch.getDataURL({ type: 'png', pixelRatio: 2, backgroundColor: '#ffffff' });
    a.download = 'dashboard-' + id.replace('g-', '') + '.png'; document.body.appendChild(a); a.click(); a.remove();
  }

  /* ---------- filtros: controles, chips, URL ---------- */
  function opcoes(sel, lista, todos) {
    sel.textContent = '';
    [['', todos]].concat(lista).forEach(([v, t]) => { const o = document.createElement('option'); o.value = v; o.textContent = t; sel.appendChild(o); });
  }
  function montaFiltros() {
    opcoes($('f-data'), [['7', 'Últimos 7 dias'], ['30', 'Últimos 30 dias'], ['90', 'Últimos 90 dias'], ['custom', 'Personalizado…']], 'Todo o período');
    $('f-questionario').addEventListener('change', e => escolheQuestionario(e.target.value));
    CHAVES.forEach(k => $('f-' + k).addEventListener('change', e => { f[k] = e.target.value; mudou(); }));
    $('f-data').addEventListener('change', e => {
      const v = e.target.value; f.dias = ''; f.de = ''; f.ate = '';
      ui.custom = v === 'custom'; if (v && v !== 'custom') f.dias = v;
      $('f-de').value = ''; $('f-ate').value = ''; mudou();
    });
    ['de', 'ate'].forEach(k => $('f-' + k).addEventListener('change', e => { f[k] = e.target.value; mudou(); }));
  }
  function populaOpcoes() {
    const o = opts;
    opcoes($('f-coleta'), o.coletas.map(c => [c.codigo, c.codigo + ' · ' + c.campus + ' · ' + c.curso + ' · ' + c.ano + '/' + c.periodo]), 'Todas');
    opcoes($('f-campus'), o.campus.map(x => [String(x.id), x.nome]), 'Todos');
    opcoes($('f-curso'), o.curso.map(x => [String(x.id), x.nome]), 'Todos');
    opcoes($('f-ano'), o.ano.map(x => [String(x), String(x)]), 'Todos');
    opcoes($('f-periodo'), o.periodo.map(x => [String(x.id), x.nome]), 'Ambos');
    opcoes($('f-grupo'), o.grupo.map(x => [x, x]), 'Todos');
    opcoes($('f-questao'), o.questao.map(x => [String(x.numero), 'Q' + x.numero + ' · ' + x.titulo]), 'Todas');
  }
  const NOME_OPT = {
    campus: v => ((opts.campus.find(x => String(x.id) === v)) || {}).nome, curso: v => ((opts.curso.find(x => String(x.id) === v)) || {}).nome,
    periodo: v => ((opts.periodo.find(x => String(x.id) === v)) || {}).nome,
    questao: v => { const q = opts.questao.find(x => String(x.numero) === v); return q && 'Q' + v + ' · ' + q.titulo; },
  };
  const valorLegivel = (k, v) => (NOME_OPT[k] && NOME_OPT[k](v)) || v;

  // trocar de questionário recomeça: limpa os outros filtros e refaz as listas
  async function escolheQuestionario(id, manterFiltros) {
    ui.quest = id; D = null; opts = null; mostraErro('');
    if (!manterFiltros) { Object.keys(f).forEach(k => f[k] = ''); ui.custom = false; }
    ui.sort = null; ui.busca = ''; $('busca').value = ''; ui.aba = 'questao';
    if (!id) return renderTudo();
    try { opts = await api('opcoes', null, true); }
    catch (e) { ui.quest = ''; mostraErro(e.message); return renderTudo(); }
    populaOpcoes(); sincronizaControles(); carrega();
  }
  const DICA_ESTADO = {
    'travado': 'Estrutura travada: só texto e gabarito podem ser corrigidos.',
    'em coleta': 'Tem coleta, ainda sem respostas: a estrutura trava na primeira resposta.',
    'rascunho': 'Rascunho: sem coletas, estrutura livre.',
  };
  const classeEstado = e => e.replace(' ', '-');
  function renderQinfo() {
    const box = $('qinfo'); box.textContent = ''; const q = cartoes.find(c => String(c.id) === ui.quest); if (!q) return;
    const b = document.createElement('span'); b.className = 'badge ' + classeEstado(q.estado); b.textContent = q.estado; box.appendChild(b);
    const t = document.createElement('span');
    t.textContent = q.n_perguntas + ' perguntas · ' + q.n_coletas + (q.n_coletas === 1 ? ' coleta' : ' coletas') + ' · ' + nf0.format(q.n_partidas) + ' partidas' + (q.derivado_de ? ' · derivado de ' + q.derivado_de : '');
    box.appendChild(t);
    const d = document.createElement('span'); d.textContent = DICA_ESTADO[q.estado] || ''; d.style.color = 'var(--d-muted)'; box.appendChild(d);
  }
  function renderEscolha() {
    const box = $('cards-q'); box.textContent = '';
    if (!cartoes.length) { const p = document.createElement('p'); p.textContent = 'Nenhum questionário cadastrado ainda. Crie um em Questionários.'; box.appendChild(p); return; }
    cartoes.forEach(q => {
      const b = document.createElement('button'); b.type = 'button'; b.className = 'card-q';
      const h = document.createElement('h3'); h.textContent = q.nome;
      const bd = document.createElement('span'); bd.className = 'badge ' + classeEstado(q.estado); bd.textContent = q.estado; bd.style.alignSelf = 'flex-start';
      const m = document.createElement('div'); m.className = 'meta'; m.textContent = q.n_perguntas + ' perguntas · ' + q.n_coletas + (q.n_coletas === 1 ? ' coleta' : ' coletas') + ' · ' + nf0.format(q.n_partidas) + ' partidas';
      const dv = document.createElement('div'); dv.className = 'deriv'; dv.textContent = q.derivado_de ? 'Derivado de ' + q.derivado_de : 'Questionário original';
      const ab = document.createElement('span'); ab.className = 'abrir'; ab.append('Abrir dashboard '); const ic = document.createElement('i'); ic.className = 'fas fa-arrow-right'; ic.setAttribute('aria-hidden', 'true'); ab.appendChild(ic);
      b.append(h, bd, m, dv, ab); b.addEventListener('click', () => escolheQuestionario(String(q.id))); box.appendChild(b);
    });
  }
  function sincronizaControles() {
    const sq = $('f-questionario'); sq.value = ui.quest; sq.parentElement.classList.toggle('ativo', !!ui.quest); renderQinfo();
    if (!opts) return;
    CHAVES.forEach(k => { const el = $('f-' + k); el.value = f[k]; el.parentElement.classList.toggle('ativo', !!f[k]); });
    const modo = f.dias ? f.dias : (f.de || f.ate || ui.custom) ? 'custom' : '';
    $('f-data').value = modo; $('f-data').parentElement.classList.toggle('ativo', !!modo);
    $('intervalo').classList.toggle('visivel', modo === 'custom'); $('f-de').value = f.de; $('f-ate').value = f.ate;
    const chips = $('chips'); chips.textContent = '';
    const chip = (rotulo, remove) => {
      const s = document.createElement('span'); s.className = 'chip'; s.append(rotulo);
      const b = document.createElement('button'); b.type = 'button'; b.setAttribute('aria-label', 'Remover filtro ' + rotulo);
      const i = document.createElement('i'); i.className = 'fas fa-xmark'; i.setAttribute('aria-hidden', 'true'); b.appendChild(i); b.onclick = remove; s.appendChild(b); chips.appendChild(s);
    };
    CHAVES.filter(k => f[k]).forEach(k => chip(NOMES_FILTRO[k] + ': ' + valorLegivel(k, f[k]), () => { f[k] = ''; mudou(); }));
    if (f.dias) chip('Últimos ' + f.dias + ' dias', () => { f.dias = ''; mudou(); });
    if (f.de) chip('A partir de ' + dataBR(f.de), () => { f.de = ''; mudou(); });
    if (f.ate) chip('Até ' + dataBR(f.ate), () => { f.ate = ''; mudou(); });
    if (haFiltro()) { const l = document.createElement('button'); l.type = 'button'; l.className = 'limpar'; l.textContent = 'Limpar tudo'; l.onclick = limpar; chips.appendChild(l); }
    const qs = new URLSearchParams(); if (ui.quest) qs.set('questionario', ui.quest); Object.entries(f).forEach(([k, v]) => v && qs.set(k, v)); if (ui.dim !== 'campus') qs.set('dim', ui.dim);
    try { history.replaceState(null, '', qs.toString() ? '?' + qs : location.pathname); } catch (e) { /* sem história */ }
  }
  function limpar() { Object.keys(f).forEach(k => f[k] = ''); ui.custom = false; mudou(); }
  function toggleFiltro(k, v) { f[k] = f[k] === v ? '' : v; mudou(); }

  /* ---------- orquestração ---------- */
  const CARDS = ['card-questoes', 'card-grupos', 'card-comp', 'card-heat', 'card-det', 'card-evo', 'card-tab'];
  let ligado = false;
  function renderTudo() {
    sincronizaControles();
    const tem = !!ui.quest && !!opts;
    $('painel').hidden = !tem; $('escolha').hidden = tem;
    if (!tem) { renderEscolha(); $('resumo-recorte').textContent = 'Nenhum questionário selecionado'; return; }
    if (!ligado) { ligado = true; liga(); }        // gráficos só nascem com o painel visível
    if (!D) return;
    desenha();
  }
  function desenha() {
    renderKPIs(); renderQuestoes(); renderGrupos(); renderComparativo(); renderHeat(); renderDetalhe(); renderEvolucao(); renderTabs(); renderTabela();
    document.querySelectorAll('#card-comp [data-dim]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.dim === ui.dim)));
    document.querySelectorAll('#card-questoes [data-ord]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.ord === ui.ordem)));
  }
  // busca os dados do recorte; mantém o quadro anterior com opacidade reduzida (sem esqueleto nem salto de layout)
  async function carrega(o = {}) {
    const minha = ++seq;
    CARDS.forEach(id => $(id).classList.add('carregando'));
    try {
      if (o.soTabela && D) {
        const tab = await api('tabela', { aba: abaApi() });
        if (minha !== seq) return;
        D.tab = tab;
      } else {
        const [resumo, questoes, grupos, comp, heat, evo, tab] = await Promise.all([
          api('resumo'), api('questoes', { limite: 500 }), api('grupos'), api('comparativo', { dim: ui.dim }),
          api('heatmap', { dim: ui.dim }), api('evolucao', { passo: ui.gran }), api('tabela', { aba: abaApi() })]);
        const alvo = f.questao ? Number(f.questao) : (questoes.itens[0] && questoes.itens[0].numero);
        const det = alvo ? await api('questao/' + alvo) : null;
        if (minha !== seq) return;
        D = { resumo, questoes, grupos, comp, heat, evo, tab, det, nQuestoes: questoes.total };
      }
      mostraErro('');
      renderTudo();
    } catch (e) {
      if (minha !== seq) return;
      mostraErro(e.message);
    } finally {
      if (minha === seq) CARDS.forEach(id => $(id).classList.remove('carregando'));
    }
  }
  function mudou() { sincronizaControles(); carrega(); }

  function liga() {
    chart('g-questoes').on('click', p => ultimo['g-questoes'][p.dataIndex] && toggleFiltro('questao', String(ultimo['g-questoes'][p.dataIndex].num)));
    chart('g-grupos').on('click', p => ultimo['g-grupos'][p.dataIndex] && toggleFiltro('grupo', ultimo['g-grupos'][p.dataIndex].nome));
    chart('g-comp').on('click', p => ultimo['g-comp'][p.dataIndex] && toggleFiltro(ui.dim, ultimo['g-comp'][p.dataIndex].chave));
    chart('g-heat').on('click', p => {
      const i = ultimo['g-heat'][p.dataIndex]; if (!i) return;
      const jaSel = f.grupo === i.g && f[ui.dim] === i.x; f.grupo = jaSel ? '' : i.g; f[ui.dim] = jaSel ? '' : i.x; mudou();
    });
    document.querySelectorAll('#card-comp [data-dim]').forEach(b => b.addEventListener('click', () => { ui.dim = b.dataset.dim; ui.sort = null; mudou(); }));
    document.querySelectorAll('#card-questoes [data-ord]').forEach(b => b.addEventListener('click', () => { ui.ordem = b.dataset.ord; desenha(); }));
    document.querySelectorAll('#card-evo [data-gran]').forEach(b => b.addEventListener('click', () => { ui.gran = b.dataset.gran; mudou(); }));
    document.querySelectorAll('[data-png]').forEach(b => b.addEventListener('click', () => baixaPNG('g-' + b.closest('.card-g').id.replace('card-', ''))));
    document.querySelectorAll('[data-tabela]').forEach(b => b.addEventListener('click', () => {
      const card = b.closest('.card-g'); const on = !card.classList.contains('modo-tabela'); card.classList.toggle('modo-tabela', on); b.setAttribute('aria-pressed', String(on));
      b.lastChild.textContent = on ? 'Gráfico' : 'Tabela';
      const id = card.id.replace('card-', ''); if (on) montaVista(id); else setTimeout(() => charts['g-' + id] && charts['g-' + id].resize(), 0);
    }));
    $('busca').addEventListener('input', e => { ui.busca = e.target.value; renderTabela(); });
    $('exportar').addEventListener('click', exportarCSV);
    $('decal').addEventListener('change', e => { ui.decal = e.target.checked; if (D) desenha(); });
    const mq = matchMedia('(max-width: 640px)'); const ajusta = () => { $('filtros').open = !mq.matches; }; ajusta(); mq.addEventListener('change', ajusta);
  }

  let larguraAnt = window.innerWidth;
  window.addEventListener('resize', () => { const cruzou = (larguraAnt <= 640) !== (window.innerWidth <= 640); larguraAnt = window.innerWidth; if (cruzou && D) desenha(); });

  function lerURL() {
    const qs = new URLSearchParams(location.search);
    CHAVES.concat(['dias', 'de', 'ate']).forEach(k => { const v = qs.get(k); if (v) f[k] = v; });
    if (qs.get('dim') && DIMS[qs.get('dim')]) ui.dim = qs.get('dim');
    return qs.get('questionario');
  }

  async function inicia() {
    montaFiltros();
    const inicial = lerURL();
    try { cartoes = (await api('questionarios')).itens; }
    catch (e) { mostraErro(e.message); cartoes = []; }
    opcoes($('f-questionario'), cartoes.map(q => [String(q.id), q.nome + ' · ' + q.estado]), 'Escolha um questionário…');
    if (inicial && cartoes.some(c => String(c.id) === inicial)) await escolheQuestionario(inicial, true);
    else renderTudo();
  }
  inicia();
  window.__dash = { f, ui, get dados() { return D; } };
})();
