// Mecanismo de selecao: quando o motor precisa que um jogador escolha algo
// (carta do Panteao pra invocar, carta do descarte, etc.), ele publica
// "selecaoPedida" pelo EventBus e guarda um callback pendente — nao trava
// esperando input. A UI humana mostra um overlay e chama resolver() quando o
// jogador clica; a IA chama resolver() na hora, de forma sincrona.
// Espelha game/selection.py.
var TCG = window.TCG || (window.TCG = {});

TCG.criarSelectionManager = function criarSelectionManager(bus) {
  let proximoId = 1;
  const pendentes = new Map();

  return {
    solicitar(playerId, prompt, opcoes, onResolved, minimo = 1, maximo = 1) {
      const requestId = proximoId++;
      pendentes.set(requestId, { playerId, minimo, maximo, opcoes: opcoes.slice(), onResolved });
      bus.emit("selecaoPedida", { requestId, playerId, prompt, opcoes: opcoes.slice(), minimo, maximo });
      return requestId;
    },

    pendente(requestId) {
      return pendentes.has(requestId);
    },

    // Acha a primeira selecao pendente pedida pra esse jogador (se houver) —
    // usado por scripts de teste/depuracao que simulam o jogador local sem
    // passar pela UI de verdade (que reage via o evento "selecaoPedida").
    algumaPendentePara(playerId) {
      for (const [requestId, pend] of pendentes) {
        if (pend.playerId === playerId) return { requestId, opcoes: pend.opcoes };
      }
      return null;
    },

    resolver(requestId, escolha) {
      const pend = pendentes.get(requestId);
      if (!pend) throw new Error(`Nao ha selecao pendente com id ${requestId}.`);
      pendentes.delete(requestId);
      for (const c of escolha) {
        if (!pend.opcoes.includes(c)) throw new Error(`Opcao invalida na selecao ${requestId}.`);
      }
      if (escolha.length < pend.minimo || escolha.length > pend.maximo) {
        throw new Error(`Selecao ${requestId} exige entre ${pend.minimo} e ${pend.maximo} escolhas.`);
      }
      bus.emit("selecaoFeita", { requestId, playerId: pend.playerId, escolha });
      pend.onResolved(escolha);
    },
  };
};
