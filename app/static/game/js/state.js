// Máquina de Estados Finitos (FSM) e modelo de dados de execução. Tudo em memória:
// nada é gravado em localStorage, sessionStorage ou cookies.
(function () {
  'use strict';

  const STATES = {
    BOOT: 'BOOT',
    TITLE: 'TITLE',
    INSTRUCTIONS: 'INSTRUCTIONS',
    AVATAR_SELECT: 'AVATAR_SELECT',
    QUIZ_PLAYING: 'QUIZ_PLAYING',
    ANSWER_FEEDBACK: 'ANSWER_FEEDBACK',
    PODIUM_REVIEW: 'PODIUM_REVIEW'
  };

  const TRANSITIONS = {
    BOOT: ['TITLE'],
    TITLE: ['INSTRUCTIONS'],
    INSTRUCTIONS: ['TITLE', 'AVATAR_SELECT'],
    AVATAR_SELECT: ['INSTRUCTIONS', 'QUIZ_PLAYING'],
    QUIZ_PLAYING: ['ANSWER_FEEDBACK'],                 // ao cruzar a porta, vem a reação do avatar
    ANSWER_FEEDBACK: ['QUIZ_PLAYING', 'PODIUM_REVIEW'],  // depois da reação: próxima pergunta ou pódio
    PODIUM_REVIEW: ['TITLE']
  };

  class GameState {
    constructor() {
      this.STATES = STATES;
      this.current = STATES.BOOT;
      this.bootErrors = [];
      this.questions = [];        // chegam do servidor depois que o aluno informa o código da turma (loadQuiz)
      this.quizMeta = null;       // { codigo, questionarioId } da coleta em andamento
      this.lastCode = '';         // último código digitado (só em memória): "Jogar novamente" já o traz preenchido
      this.resetData();
    }

    // Modelo de dados de execução.
    resetData() {
      this.playerName = '';
      this.selectedAvatar = null;     // 0 a 8
      this.currentQuestionIndex = 0;
      this.score = 0;                 // soma de XP
      this.answersHistory = [];
      this.activeModalHint = false;   // popup de autoajuda aberto
      this.partidaUuid = null;        // identifica a partida no servidor; reenviar o mesmo UUID nunca duplica
      this.saveStatus = { estado: 'idle' };   // 'enviando' | 'salvo' | 'erro' (ver salvarPartida)
    }

    // Estado BOOT: valida só a configuração. As perguntas não ficam mais no navegador: chegam do servidor quando o aluno
    // informa o código da turma (tela TITLE) e entram aqui por loadQuiz().
    boot() {
      const errs = [];
      const cfg = window.GAME_CONFIG;
      if (!cfg) {
        errs.push('window.GAME_CONFIG não encontrado (config/config.js).');
      } else {
        ['institution', 'economy', 'userValidation', 'interface'].forEach(k => {
          if (!cfg[k]) errs.push(`GAME_CONFIG.${k} ausente em config/config.js.`);
        });
      }
      if (!window.TQApi) errs.push('window.TQApi não encontrado (js/api.js).');
      this.bootErrors = errs;
      if (errs.length) return false;
      this.go(STATES.TITLE);
      return true;
    }

    // Recebe o questionário já convertido por TQApi.montaQuiz(): { quiz, orientacoes, codigo, questionarioId }.
    loadQuiz(montado, codigo) {
      const quiz = montado.quiz;
      if (!Array.isArray(quiz) || quiz.length === 0) throw new Error('Questionário vazio.');
      quiz.forEach(q => {
        const alts = q && q.alternatives;
        if (!Array.isArray(alts) || alts.length < 2 || alts.length > 4 || alts.filter(a => a.correct).length !== 1) {
          throw new Error(`Pergunta ${q && q.id}: precisa de 2 a 4 alternativas e exatamente 1 correta.`);
        }
      });
      this.questions = quiz
        .map(q => ({ ...q, alternatives: q.alternatives.slice().sort((a, b) => a.letter.localeCompare(b.letter)) }))
        .sort((a, b) => a.id - b.id);
      this.quizMeta = { codigo, questionarioId: montado.questionarioId };
      this.lastCode = codigo;
    }

    go(to) {
      if (!TRANSITIONS[this.current].includes(to)) {
        throw new Error(`Transição inválida: ${this.current} -> ${to}`);
      }
      this.current = to;
    }

    validName(n) {
      return new RegExp(window.GAME_CONFIG.userValidation.allowedPattern).test(n);
    }

    get totalQuestions() { return this.questions.length; }
    get currentQuestion() { return this.questions[this.currentQuestionIndex]; }
    get lastAnswer() { return this.answersHistory[this.answersHistory.length - 1]; }

    // Cadastro validado: zera o progresso e entra no loop de perguntas.
    startQuiz(name, avatarIndex) {
      this.playerName = name;
      this.selectedAvatar = avatarIndex;
      this.currentQuestionIndex = 0;
      this.score = 0;
      this.answersHistory = [];
      this.activeModalHint = false;
      this.partidaUuid = window.TQApi.novoUuid();
      this.saveStatus = { estado: 'idle' };
      this.go(STATES.QUIZ_PLAYING);
    }

    // Grava a resposta e acumula o XP; o feedback visual é mostrado no estado ANSWER_FEEDBACK.
    answer(question, alt, timeMs) {
      const eco = window.GAME_CONFIG.economy;
      const correct = question.alternatives.find(a => a.correct);
      const points = alt.correct ? eco.pointsCorrect : eco.pointsIncorrect;
      this.score += points;
      this.answersHistory.push({
        questionId: question.id,
        questionTitle: question.title,
        questionText: question.question,
        selectedLetter: alt.letter,
        isCorrect: alt.correct,
        correctLetter: correct.letter,
        feedbackText: alt.correct ? alt.successText : alt.errorText,
        // campos extras usados pela revisão
        questionGroup: question.group,
        selectedText: alt.text,
        correctText: correct.text,
        correctFeedbackText: correct.successText,
        points,
        // enviados ao servidor: o tempo até escolher a porta e a ordem em que a pergunta foi respondida
        timeMs: Math.max(0, Math.round(timeMs || 0)),
        order: this.answersHistory.length + 1
      });
    }

    // A partir de ANSWER_FEEDBACK: avança para a próxima pergunta ou, ao terminar, para o pódio. Retorna true se há mais.
    advance() {
      this.currentQuestionIndex++;
      this.activeModalHint = false;
      if (this.currentQuestionIndex >= this.questions.length) {
        this.go(STATES.PODIUM_REVIEW);
        return false;
      }
      this.go(STATES.QUIZ_PLAYING);
      return true;
    }

    // Grava a partida no servidor (com tentativas automáticas). Devolve o estado final: 'salvo' ou 'erro'.
    // Não há XP, nome nem avatar no envio: só o código, o UUID e as respostas.
    async salvarPartida() {
      this.saveStatus = { estado: 'enviando' };
      const api = window.TQApi;
      const payload = api.montaPayload(this.partidaUuid, this.quizMeta.codigo, this.answersHistory);
      const r = await api.enviarPartida(payload);
      this.saveStatus = r.ok ? { estado: 'salvo', duplicada: !!r.duplicada }
        : { estado: 'erro', motivo: r.motivo, mensagem: r.mensagem, definitivo: !!r.definitivo, esperaSeg: r.esperaSeg || 0 };
      return this.saveStatus;
    }

    // "Jogar Novamente": limpa pontuação, histórico, nome, avatar e perguntas; volta para TITLE (o código é pedido de novo,
    // já preenchido com o último).
    restart() {
      this.resetData();
      this.questions = [];
      this.quizMeta = null;
      this.go(STATES.TITLE);
    }
  }

  window.GameStateClass = GameState;
  window.GameState = new GameState();
})();
