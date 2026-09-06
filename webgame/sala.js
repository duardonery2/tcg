// Handshake com o relay com código de sala (scripts/relay_server.py),
// compartilhado entre menu.js (criar/entrar) e main.js (retomar, depois da
// navegação menu.html -> index.html). Não sabe nada de jogo — só abre a
// conexão e troca as mensagens de pareamento; a partir daí quem chama volta
// a ouvir "message" por conta própria (ver webgame/rede.js).
var TCG = window.TCG || (window.TCG = {});

// Relay publicado no Fly.io (ver fly.toml — "tcg-relay" já estava em uso,
// o nome de verdade saiu como tcg-relay-black-skylark-7238);
// ?relay=<url> sobrepõe, útil pra testar contra scripts/relay_server.py
// rodando local.
TCG.RELAY_PADRAO = "wss://tcg-relay-black-skylark-7238.fly.dev";

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
// Também rejeita se a conexão cair ANTES de qualquer mensagem chegar — sem
// isso, uma queda silenciosa (ex.: navegador suspende a aba em segundo
// plano enquanto o host troca de app pra compartilhar o código) deixava
// essa promise pendurada pra sempre, sem erro nenhum: a tela ficava presa
// em "Aguardando..." mesmo depois do oponente já ter entrado de verdade.
TCG.aguardarMensagemRelay = function aguardarMensagemRelay(ws) {
  return new Promise((resolve, reject) => {
    function limpar() {
      ws.removeEventListener("message", ouvir);
      ws.removeEventListener("close", aoFechar);
    }
    function ouvir(ev) {
      limpar();
      try { resolve(JSON.parse(ev.data)); } catch (e) { reject(e); }
    }
    function aoFechar() {
      limpar();
      reject(new Error("A conexão com o relay caiu antes de receber resposta. Tente de novo."));
    }
    ws.addEventListener("message", ouvir, { once: true });
    ws.addEventListener("close", aoFechar, { once: true });
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

// Mantém o WebSocket "quente": alguns proxies/redes (móvel, corporativa,
// e possivelmente o próprio Fly.io) fecham conexões que ficam um tempo
// sem tráfego de dados — um duelo de cartas passa minutos ocioso entre
// jogadas. Manda um ping pequeno periodicamente; o relay responde com
// pong direto pra quem mandou, sem repassar pro outro lado (ver
// scripts/relay_core.py bombear) — os dois lados de webgame/match.js
// simplesmente ignoram "pong" ao receber.
TCG.INTERVALO_HEARTBEAT_MS = 20000;
TCG.iniciarHeartbeat = function iniciarHeartbeat(ws, intervaloMs = TCG.INTERVALO_HEARTBEAT_MS) {
  const id = setInterval(() => {
    if (ws.readyState === WebSocket.OPEN) ws.send('{"type":"ping"}');
  }, intervaloMs);
  return () => clearInterval(id);
};
