// Sintetizador procedural (Web Audio API nativa). Nenhum arquivo de áudio externo.
(function () {
  'use strict';

  class SoundSystem {
    constructor() {
      this.ctx = null;
      this.master = null;
      this.isMuted = false;
      this._noise = null;
      this.unlock = this.unlock.bind(this);
      // O navegador só libera áudio após um gesto do usuário: clique, toque ou tecla.
      ['pointerdown', 'keydown'].forEach(ev => window.addEventListener(ev, this.unlock, true));
    }

    // Cria o AudioContext de forma preguiçosa no primeiro gesto e o retoma se estiver suspenso.
    unlock() {
      try {
        if (!this.ctx) {
          const AC = window.AudioContext || window.webkitAudioContext;
          if (!AC) return;
          this.ctx = new AC();
          this.master = this.ctx.createGain();
          this.master.gain.value = this.isMuted ? 0 : 0.5;
          this.master.connect(this.ctx.destination);
          this._noise = this.ctx.createBuffer(1, this.ctx.sampleRate, this.ctx.sampleRate);
          const d = this._noise.getChannelData(0);
          for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
        }
        if (this.ctx.state === 'suspended') this.ctx.resume();
      } catch (e) { /* sem áudio: o jogo segue mudo */ }
    }

    toggleMute() {
      this.isMuted = !this.isMuted;
      if (this.master) this.master.gain.value = this.isMuted ? 0 : 0.5;
      return this.isMuted;
    }

    _ready() {
      return !this.isMuted && this.ctx && this.ctx.state === 'running';
    }

    // Oscilador com envelope: ataque curto e decaimento exponencial até o fim da nota.
    _tone(type, freq, dur, vol, delay, freqEnd) {
      const t = this.ctx.currentTime + (delay || 0);
      const o = this.ctx.createOscillator();
      const g = this.ctx.createGain();
      o.type = type;
      o.frequency.setValueAtTime(freq, t);
      if (freqEnd) o.frequency.exponentialRampToValueAtTime(freqEnd, t + dur);
      g.gain.setValueAtTime(vol, t);
      g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
      o.connect(g);
      g.connect(this.master);
      o.start(t);
      o.stop(t + dur + 0.02);
    }

    // Passo: onda triangular de 120 Hz para 40 Hz em 0,08 s, ganho 0,1.
    playStep() {
      if (!this._ready()) return;
      this._tone('triangle', 120, 0.08, 0.1, 0, 40);
    }

    // Eclusa: bipes senoidais de 440 Hz e 880 Hz (0,15 s cada) com leve ruído branco modulado.
    playDoorOpen() {
      if (!this._ready()) return;
      this._tone('sine', 440, 0.15, 0.18, 0);
      this._tone('sine', 880, 0.15, 0.18, 0.15);
      const t = this.ctx.currentTime;
      const src = this.ctx.createBufferSource();
      src.buffer = this._noise;
      const f = this.ctx.createBiquadFilter();
      f.type = 'bandpass';
      f.frequency.value = 2400;
      const g = this.ctx.createGain();
      g.gain.setValueAtTime(0.0001, t);
      const lfo = this.ctx.createOscillator();     // modulação do ruído
      const lfoGain = this.ctx.createGain();
      lfo.frequency.value = 24;
      lfoGain.gain.value = 0.02;
      g.gain.linearRampToValueAtTime(0.03, t + 0.05);
      g.gain.linearRampToValueAtTime(0.0001, t + 0.3);
      lfo.connect(lfoGain);
      lfoGain.connect(g.gain);
      src.connect(f);
      f.connect(g);
      g.connect(this.master);
      src.start(t, Math.random() * 0.5);
      src.stop(t + 0.3);
      lfo.start(t);
      lfo.stop(t + 0.3);
    }

    // Clique de botão: senoide de 1200 Hz com fade-out em 0,05 s.
    playHintClick() {
      if (!this._ready()) return;
      this._tone('sine', 1200, 0.05, 0.15, 0);
    }

    // Acerto: arpejo ascendente curto (E5, G5, C6) em onda triangular, com brilho final.
    playCorrect() {
      if (!this._ready()) return;
      [659.25, 783.99, 1046.5].forEach((f, i) => this._tone('triangle', f, 0.14, 0.2, i * 0.09));
      this._tone('sine', 2093, 0.25, 0.08, 0.27);
    }

    // Erro: duas notas suaves e descendentes (sem tom de punição), em onda senoidal.
    playWrong() {
      if (!this._ready()) return;
      this._tone('sine', 392, 0.2, 0.18, 0);
      this._tone('sine', 311.13, 0.32, 0.18, 0.18);
    }

    // Fanfarra 8-bit: ondas quadradas C5, E5, G5, C6 com 0,12 s cada.
    playSuccessFanfare() {
      if (!this._ready()) return;
      [523.25, 659.25, 783.99, 1046.5].forEach((f, i) => this._tone('square', f, 0.12, 0.12, i * 0.12));
    }
  }

  window.SoundSystemClass = SoundSystem;
  window.SoundSystem = new SoundSystem();
})();
