// Handshake com o relay com código de sala (scripts/relay_server.py),
// compartilhado entre menu.js (criar/entrar) e main.js (retomar, depois da
// navegação menu.html -> index.html). Não sabe nada de jogo — só abre a
// conexão e troca as mensagens de pareamento; a partir daí quem chama volta
// a ouvir "message" por conta própria (ver webgame/rede.js).
var TCG = window.TCG || (window.TCG = {});

// Trocado pelo endereço do relay publicado antes do deploy (ver plano de
// multiplayer / fly.toml); ?relay=<url> sobrepõe, útil pra testar contra
// scripts/relay_server.py rodando local.
TCG.RELAY_PADRAO = "wss://tcg-relay.fly.dev";

TCG.relayUrl = function relayUrl() {
  const params = new URLSearchParams(window.location.search);
  return params.get("relay") || TCG.RELAY_PADRAO;
};

TCG.ErroSala = class ErroSala extends Error {
  constructor(codigo, mensagem) {
    super(mensagem);
    this.codigo = codigo; // "SALA_NAO_ENCONTRADA" | "SALA_CHEIA" | "REQUISICAO_INVALIDA"
  }
};

TCG.conectarRelay = function conectarRelay(url) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(url);
    ws.addEventListener("open", () => resolve(ws), { once: true });
    ws.addEventListener("error", () => reject(new Error(`Não foi possível conectar em ${url}.`)), { once: true });
  });
};

// Espera a PRÓXIMA mensagem JSON e some do fluxo — uso único, só pro
// handshake ponto-a-ponto (criar/entrar/retomar); depois disso quem chama
// volta a instalar seu próprio listener de "message" pro resto da partida.
TCG.aguardarMensagemRelay = function aguardarMensagemRelay(ws) {
  return new Promise((resolve, reject) => {
    ws.addEventListener("message", function ouvir(ev) {
      ws.removeEventListener("message", ouvir);
      try { resolve(JSON.parse(ev.data)); } catch (e) { reject(e); }
    }, { once: true });
  });
};

async function trocaComRelay(ws, mensagemEnviada) {
  ws.send(JSON.stringify(mensagemEnviada));
  const resposta = await TCG.aguardarMensagemRelay(ws);
  if (resposta.type === "erro") throw new TCG.ErroSala(resposta.codigo, resposta.mensagem);
  return resposta; // {type:"papel", papel, codigo}
}

TCG.criarSalaNoRelay = (ws) => trocaComRelay(ws, { type: "criarSala" });
TCG.entrarSalaNoRelay = (ws, codigo) => trocaComRelay(ws, { type: "entrarSala", codigo });
TCG.retomarSalaNoRelay = (ws, codigo, papel) => trocaComRelay(ws, { type: "retomarSala", codigo, papel });
