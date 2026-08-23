// Ponto de entrada: cria a partida, liga a UI, expoe window.game pra
// depuracao/verificacao (ex.: script de teste em Playwright).
const JOGADOR_LOCAL = 1;
const JOGADOR_IA = 2;

function novaPartida(seed) {
  const game = TCG.criarJogo({ seed, nomes: { 1: "Você", 2: "Oponente" } });
  TCG.iniciarJogo(game);
  window.game = game;
  window.ui = TCG.criarUI(game, JOGADOR_LOCAL);
  return game;
}

window.iniciarNovaPartida = function iniciarNovaPartida() {
  const overlayFim = document.getElementById("overlay-fim");
  if (overlayFim) overlayFim.classList.remove("ativo");
  const params = new URLSearchParams(window.location.search);
  const seed = params.has("seed") ? Number(params.get("seed")) : null;
  novaPartida(seed);
};

window.addEventListener("DOMContentLoaded", () => {
  const params = new URLSearchParams(window.location.search);
  const seed = params.has("seed") ? Number(params.get("seed")) : null;
  novaPartida(seed);
});
