// Acessibilidade para leitores de tela: o Canvas não é lido, então o jogo espelha o que está na tela
// numa região oculta com aria-live (avisos) e numa lista oculta com a revisão final.
(function () {
  'use strict';

  const live = document.getElementById('a11y-live');
  const review = document.getElementById('a11y-review');
  let flip = false;
  let last = '';

  window.A11y = {
    // Anuncia um texto. O caractere invisível alterna para que textos repetidos sejam lidos de novo.
    announce(text) {
      if (!live || !text) return;
      last = text;
      flip = !flip;
      live.textContent = text + (flip ? '​' : '');
    },

    // Repete o último aviso (tecla R), útil quando o leitor de tela perde ou o jogador quer reouvir.
    repeat() { this.announce(last); },

    // Revisão completa em lista (navegável pelo leitor de tela). items: array de strings.
    setReview(items) {
      if (!review) return;
      review.textContent = '';
      const ol = document.createElement('ol');
      items.forEach(t => { const li = document.createElement('li'); li.textContent = t; ol.appendChild(li); });
      review.appendChild(ol);
    },

    clearReview() { if (review) review.textContent = ''; }
  };
})();
