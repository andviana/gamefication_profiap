// Parametrização institucional e de regras do jogo (sem valores fixos no código).
window.GAME_CONFIG = {
  institution: {
    name: "UFRA - Universidade Federal Rural da Amazônia",
    department: "Programa de Pós-Graduação em Administração Pública - PROFIAP",
    logoUniversityUrl: "assets/logos/logo_ufra.png",
    logoProgramUrl: "assets/logos/logo_pos.png"
  },
  economy: {
    pointsCorrect: 100,
    pointsIncorrect: 10,
    currencyName: "XP",
    currencySymbol: "XP"
  },
  userValidation: {
    maxNameLength: 15,
    allowedPattern: "^[a-zA-Z0-9]{1,15}$"
  },
  interface: {
    gameTitle: "TechQuiz Campus",
    canvasWidth: 1280,
    canvasHeight: 720
  }
};
