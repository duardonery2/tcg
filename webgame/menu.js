// Menu Principal: navegação local (Jogar/Construir Baralho) + criar/entrar
// numa sala de duelo pela internet (webgame/sala.js, scripts/relay_server.py).
// Nenhum estado de JOGO é criado aqui — só a conexão com o relay até o
// pareamento acontecer; quem constrói o `game` de verdade é index.html/
// main.js, depois da navegação (ver "retomar sala" abaixo).
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

// ---- sala de duelo (multiplayer pela internet) -------------------------

const btnCriarSala = document.getElementById("btn-criar-sala");
const btnEntrarSala = document.getElementById("btn-entrar-sala");
const inputCodigo = document.getElementById("input-codigo-sala");
const elSalaStatus = document.getElementById("menu-sala-status");

function mostrarStatusSala(texto, { erro = false } = {}) {
  elSalaStatus.textContent = texto || "";
  elSalaStatus.classList.toggle("erro", erro);
}

function travarControlesSala(travado) {
  btnCriarSala.disabled = travado;
  btnEntrarSala.disabled = travado;
  inputCodigo.disabled = travado;
}

// Uma sala recém-pareada não sobrevive à navegação (WebSocket não atravessa
// location.href) — index.html abre uma conexão NOVA e manda "retomarSala"
// pra reocupar o mesmo slot no relay (ver scripts/relay_server.py), então
// não precisamos manter este `ws` aberto além do necessário pra esperar o
// outro lado entrar.
function irParaDuelo({ codigo, papel }) {
  const relay = encodeURIComponent(TCG.relayUrl());
  location.href = `index.html?relay=${relay}&sala=${encodeURIComponent(codigo)}&papel=${papel}&retomar=1`;
}

btnCriarSala.addEventListener("click", async () => {
  travarControlesSala(true);
  mostrarStatusSala("Conectando...");
  try {
    const ws = await TCG.conectarRelay(TCG.relayUrl());
    const { codigo } = await TCG.criarSalaNoRelay(ws);
    mostrarStatusSala(`Sala criada! Código: ${codigo} — compartilhe com o oponente. Aguardando ele entrar...`);
    const proxima = await TCG.aguardarMensagemRelay(ws);
    if (proxima.type === "guestConectou") {
      mostrarStatusSala("Oponente conectado! Iniciando a partida...");
      irParaDuelo({ codigo, papel: "host" });
    }
  } catch (e) {
    mostrarStatusSala(e.message || "Não foi possível criar a sala.", { erro: true });
    travarControlesSala(false);
  }
});

async function entrarNaSala() {
  const codigo = inputCodigo.value.trim().toUpperCase();
  if (!codigo) { mostrarStatusSala("Digite o código da sala.", { erro: true }); return; }
  travarControlesSala(true);
  mostrarStatusSala("Conectando...");
  try {
    const ws = await TCG.conectarRelay(TCG.relayUrl());
    await TCG.entrarSalaNoRelay(ws, codigo);
    mostrarStatusSala("Entrou na sala! Iniciando a partida...");
    irParaDuelo({ codigo, papel: "guest" });
  } catch (e) {
    mostrarStatusSala(e.message || "Não foi possível entrar na sala.", { erro: true });
    travarControlesSala(false);
  }
}
btnEntrarSala.addEventListener("click", entrarNaSala);
inputCodigo.addEventListener("keydown", (ev) => { if (ev.key === "Enter") entrarNaSala(); });
inputCodigo.addEventListener("input", () => { inputCodigo.value = inputCodigo.value.toUpperCase(); });
