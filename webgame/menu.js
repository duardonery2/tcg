// Menu Principal: só navegação + uma linha de status lendo o baralho salvo
// (TCG.carregarDeckSalvo, engine.js) — nenhum estado de jogo é criado aqui.
const deckSalvo = TCG.carregarDeckSalvo();
const elStatus = document.getElementById("menu-status");
elStatus.textContent = deckSalvo
  ? `Baralho personalizado ativo (Panteão: ${deckSalvo.panteao.length}, Arcano: ${deckSalvo.baralhoArcano.length} cartas)`
  : "Usando baralho automático (Panteão aleatório, Baralho Arcano completo)";

document.getElementById("btn-jogar").addEventListener("click", () => {
  location.href = "index.html";
});
document.getElementById("btn-construir-baralho").addEventListener("click", () => {
  location.href = "deckbuilder.html";
});
