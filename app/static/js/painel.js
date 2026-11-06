// Comportamentos pequenos do painel (sem dependências).
(function () {
  'use strict';

  // Botão "Copiar": <button data-copiar="CÓDIGO">. Tenta a API de área de transferência (só em HTTPS/localhost) e, se ela
  // não existir ou for recusada (permissões do navegador), cai para um campo temporário + execCommand.
  function copiaLegada(texto) {
    return new Promise(function (ok, falha) {
      var campo = document.createElement('textarea');
      campo.value = texto; campo.setAttribute('readonly', ''); campo.style.position = 'fixed'; campo.style.opacity = '0';
      document.body.appendChild(campo); campo.select();
      try { document.execCommand('copy') ? ok() : falha(new Error('copy recusado')); } catch (e) { falha(e); }
      finally { document.body.removeChild(campo); }
    });
  }

  function copia(texto) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(texto).catch(function () { return copiaLegada(texto); });
    }
    return copiaLegada(texto);
  }

  document.addEventListener('click', function (ev) {
    var botao = ev.target.closest('[data-copiar]');
    if (!botao) return;
    ev.preventDefault();
    var original = botao.getAttribute('data-rotulo') || botao.textContent;
    botao.setAttribute('data-rotulo', original);
    copia(botao.getAttribute('data-copiar')).then(function () { botao.textContent = 'Copiado!'; },
                                                  function () { botao.textContent = 'Não foi possível copiar'; });
    setTimeout(function () { botao.textContent = original; }, 1800);
  });

  // Formulário com confirmação: <form data-confirmar="Mensagem">. Sem JavaScript inline (a CSP não o permite).
  document.addEventListener('submit', function (ev) {
    var msg = ev.target.getAttribute && ev.target.getAttribute('data-confirmar');
    if (msg && !window.confirm(msg)) ev.preventDefault();
  });
})();
