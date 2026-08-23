// Renderizacao DOM + clique/hover. Nunca le o estado "por fora": redesenha
// depois de cada acao humana, e reage aos eventos do bus pro log e pra
// abrir/fechar overlays. O preview em hover estende literalmente o padrao
// ja usado em gallery.html.
var TCG = window.TCG || (window.TCG = {});

TCG.criarUI = function criarUI(game, jogadorLocal) {
  const el = (id) => document.getElementById(id);
  const oponenteId = TCG.oponenteDe(game, jogadorLocal);

  const previewImg = el("preview-img");
  const previewVazio = el("preview-vazio");
  const previewLegenda = el("preview-legenda");
  const previewNome = el("preview-nome");
  const previewMeta = el("preview-meta");
  const logEl = el("log");
  const overlaySelecao = el("overlay-selecao");
  const overlayFim = el("overlay-fim");

  // O preview de uma carta com imagem mostra SÓ a imagem — nome, custo,
  // tipo/elemento ja estao todos impressos nela; POW/RES atual (o único
  // valor que pode mudar em relação à arte estática) já tem seu próprio
  // selo sempre visível direto no card do tabuleiro (.stats-badge), então
  // não precisa duplicar aqui também.
  function mostrarPreview(carta) {
    if (!carta) {
      previewImg.style.display = "none";
      previewLegenda.style.display = "none";
      previewVazio.style.display = "block";
      return;
    }
    previewVazio.style.display = "none";
    previewImg.style.display = "block";
    previewImg.src = carta.arquivo;
    previewLegenda.style.display = "none";
  }

  function mostrarPreviewOculto(texto) {
    // aqui NAO ha imagem (carta virada pra baixo, baralho, etc.) — o texto
    // e a unica informacao disponivel, entao a "legenda" volta a aparecer.
    previewVazio.style.display = "none";
    previewImg.style.display = "none";
    previewLegenda.style.display = "block";
    previewNome.style.display = "block";
    previewNome.textContent = texto;
    previewMeta.textContent = "";
  }

  function comHoverPreview(elemento, carta, textoOculto) {
    elemento.addEventListener("mouseenter", () => (carta ? mostrarPreview(carta) : mostrarPreviewOculto(textoOculto)));
    elemento.addEventListener("focus", () => (carta ? mostrarPreview(carta) : mostrarPreviewOculto(textoOculto)));
  }

  function log(msg) {
    const linha = document.createElement("div");
    linha.textContent = msg;
    logEl.appendChild(linha);
    logEl.scrollTop = logEl.scrollHeight;
  }

  function tentar(fn) {
    try {
      fn();
    } catch (e) {
      if (e instanceof TCG.AcaoInvalida) log(`⚠ ${e.message}`);
      else throw e;
    } finally {
      render();
    }
  }

  // ---- construcao de elementos de carta -----------------------------------

  function elSlot({ carta, classes = [], onClick, tabIndex = true, versoOculto = false, textoVerso = "", cartaPreview = null }) {
    const div = document.createElement("div");
    div.className = ["slot", ...classes].join(" ");
    if (versoOculto) {
      div.classList.add("verso");
      if (onClick) { div.classList.add("clicavel"); div.addEventListener("click", onClick); }
      // O DONO de uma Maldição setada sabe muito bem o que ela é — só o
      // OPONENTE não pode ver (ver renderLado: cartaPreview só vem
      // preenchido quando ehLocal). A arte no tabuleiro continua virada pra
      // baixo pros dois lados; só o preview de hover muda pro dono.
      comHoverPreview(div, cartaPreview, textoVerso);
    } else if (carta) {
      const img = document.createElement("img");
      img.src = carta.arquivo;
      img.alt = carta.nome;
      if (onClick) { div.classList.add("clicavel"); img.addEventListener("click", onClick); }
      comHoverPreview(img, carta);
      div.appendChild(img);
      if (carta.combate !== null) {
        // POW/RES *atuais* (com buffs/debuffs já aplicados) — a arte impressa
        // no PNG é estática, então isso é o único lugar que sempre mostra o
        // valor certo depois de qualquer efeito que altere os atributos.
        const badge = document.createElement("div");
        badge.className = "stats-badge";
        badge.textContent = `POW ${carta.atualPow} | RES ${carta.atualRes}`;
        div.appendChild(badge);
      }
    }
    if (tabIndex) div.tabIndex = 0;
    return div;
  }

  function podeAtivarHabilidade(carta) {
    return carta && carta.custoHabilidade != null && !carta.habilidadeUsadaNesteTurno
      && game.jogadorDaVez === jogadorLocal && ["TATICA", "COMBATE"].includes(game.fase);
  }

  // ---- Baralho / Panteão / Pilha de Descarte: renderizados como um slot
  // virado pra baixo (igual a uma Maldição setada) com o número de cartas
  // centralizado por cima. Só o Descarte é clicável — é informação pública
  // e abre num modal de leitura; Baralho/Panteão são só a contagem.

  function elPilha(rotulo, quantidade, onClick) {
    const wrap = document.createElement("div");
    wrap.className = "pilha";

    const slot = document.createElement("div");
    slot.className = "slot verso pilha-slot" + (onClick ? " clicavel" : "");
    const numero = document.createElement("span");
    numero.className = "pilha-numero";
    numero.textContent = quantidade;
    slot.appendChild(numero);
    if (onClick) slot.addEventListener("click", onClick);
    comHoverPreview(slot, null, `${rotulo}: ${quantidade} carta(s)`);

    const rotuloEl = document.createElement("div");
    rotuloEl.className = "pilha-rotulo";
    rotuloEl.textContent = rotulo;

    wrap.appendChild(slot);
    wrap.appendChild(rotuloEl);
    return wrap;
  }

  function mostrarDescarte(playerId) {
    const cartas = game.descarte[playerId];
    el("descarte-titulo").textContent = `Pilha de Descarte de ${game.players[playerId].nome} (${cartas.length})`;
    const grid = el("descarte-cartas");
    grid.innerHTML = "";
    for (const carta of cartas) {
      const img = document.createElement("img");
      img.src = carta.arquivo;
      img.alt = carta.nome;
      comHoverPreview(img, carta);
      grid.appendChild(img);
    }
    el("overlay-descarte").classList.add("ativo");
  }

  // ---- render dos tabuleiros -----------------------------------------
  // Cada lado do tabuleiro e uma LINHA: Descarte na ponta esquerda, o
  // conteudo principal (info + Monstro/Magia) no centro, Baralho+Panteão
  // empilhados na ponta direita — todos do mesmo tamanho de um slot normal.

  function renderLado(playerId, containerId, ehLocal) {
    const container = el(containerId);
    container.innerHTML = "";
    const lado = game.board[playerId];
    const ps = game.players[playerId];

    // Domínio ativo (no máximo 1 NO JOGO INTEIRO — a própria Ação já destrói
    // qualquer um já ativo, seja de quem for, ao jogar um novo, ver
    // TCG.acoes.jogarCartaDeCampo; ele ocupa normalmente um slot de magia,
    // abaixo, só no campo do dono). A arte dele vira o fundo do campo inteiro
    // dos DOIS lados do tabuleiro — é o cenário onde a partida toda acontece,
    // não um efeito visual pessoal de quem jogou (ver TCG.dominioParaFundo).
    const fundoDominio = TCG.dominioParaFundo(game);
    if (fundoDominio) {
      container.classList.add("com-dominio");
      container.style.setProperty("--dominio-art", `url('${fundoDominio.carta.arquivo}')`);
      const tag = document.createElement("div");
      tag.className = "dominio-tag";
      tag.textContent = `Domínio: ${fundoDominio.carta.nome}`;
      tag.tabIndex = 0;
      comHoverPreview(tag, fundoDominio.carta);
      container.appendChild(tag);
    } else {
      container.classList.remove("com-dominio");
      container.style.removeProperty("--dominio-art");
    }

    const pilhaEsquerda = document.createElement("div");
    pilhaEsquerda.className = "pilhas-laterais";
    pilhaEsquerda.appendChild(elPilha("Descarte", game.descarte[playerId].length, () => mostrarDescarte(playerId)));

    const centro = document.createElement("div");
    centro.className = "tabuleiro-centro";

    const infoLinha = document.createElement("div");
    infoLinha.className = "info-lado";
    infoLinha.textContent = `${ps.nome} — ${ps.mana} mana, ${ps.vida} vida` + (ehLocal ? "" : ` — mão: ${ps.mao.length} carta(s)`);
    centro.appendChild(infoLinha);

    const linhaMonstro = document.createElement("div");
    linhaMonstro.className = "linha-monstro";
    linhaMonstro.appendChild(elSlot({
      carta: lado.monstro,
      classes: ["monstro"],
      onClick: ehLocal && podeAtivarHabilidade(lado.monstro)
        ? () => tentar(() => TCG.acoes.ativarHabilidade(game, playerId, lado.monstro))
        : null,
    }));

    const linhaMagia = document.createElement("div");
    linhaMagia.className = "linha-magia";
    lado.magia.forEach((carta) => {
      // o Domínio ocupa um slot de magia normalmente, ALÉM de virar a arte
      // de fundo do campo inteiro do dono (acima) — as duas coisas juntas.
      if (carta && carta.faceDown) {
        // só o dono pode revelar a própria Maldição, e só "a qualquer
        // momento no turno do OPONENTE" (GAME_DESIGN.md) — nunca no próprio.
        const revelavel = ehLocal && game.jogadorDaVez !== playerId;
        linhaMagia.appendChild(elSlot({
          carta: null, versoOculto: true, textoVerso: "Maldição virada para baixo",
          cartaPreview: ehLocal ? carta : null, // o dono sempre pode ver a própria; o oponente nunca
          onClick: revelavel ? () => tentar(() => TCG.acoes.ativarMaldicaoSetada(game, playerId, carta)) : null,
        }));
      } else {
        linhaMagia.appendChild(elSlot({ carta }));
      }
    });

    // Tabuleiro do oponente fica espelhado: o combatente dele fica na borda
    // de baixo do quadro (perto do centro da tela), de frente pro combatente
    // do jogador local, que fica na borda de cima do proprio quadro — as
    // duas criaturas se encaram atraves do meio do tabuleiro.
    if (ehLocal) {
      centro.appendChild(linhaMonstro);
      centro.appendChild(linhaMagia);
    } else {
      centro.appendChild(linhaMagia);
      centro.appendChild(linhaMonstro);
    }

    const pilhaDireita = document.createElement("div");
    pilhaDireita.className = "pilhas-laterais";
    pilhaDireita.appendChild(elPilha("Baralho", TCG.Deck.restantes(game.baralhos[playerId]).length));
    pilhaDireita.appendChild(elPilha("Panteão", TCG.Deck.restantes(game.panteoes[playerId]).length));

    container.appendChild(pilhaEsquerda);
    container.appendChild(centro);
    container.appendChild(pilhaDireita);
  }

  // A escolha de Combatente pra invocar (e qualquer escolha de carta, ver
  // renderOverlaySelecao) sempre aparece como modal — nunca como lista solta
  // no tabuleiro. Dispara sozinho ao entrar na Fase de Invocação com o slot
  // vazio; se a escolha falhar (ex.: mana insuficiente), reabre o modal pra
  // tentar de novo em vez de simplesmente perder a chance de invocar.
  //
  // A Fase de Invocação inteira e curta e some assim que a escolha e feita —
  // sozinha avança pra Tática logo depois de invocar, pular, ou quando nao
  // ha nada pra escolher (slot ja ocupado / Panteão vazio), sem exigir mais
  // um clique em "Próxima Fase" só pra sair dela.
  function avancarSeAindaNaoAcabou() {
    if (!game.fimDeJogo) TCG.acoes.avancarFase(game);
    render();
  }

  function solicitarInvocacao() {
    if (game.fimDeJogo) return;
    if (game.board[jogadorLocal].monstro !== null) { avancarSeAindaNaoAcabou(); return; }
    const opcoes = TCG.Deck.restantes(game.panteoes[jogadorLocal]);
    if (!opcoes.length) { avancarSeAindaNaoAcabou(); return; }
    game.selection.solicitar(
      jogadorLocal, "Escolha um Combatente para invocar", opcoes,
      (escolha) => {
        if (!escolha.length) { avancarSeAindaNaoAcabou(); return; } // pulou -> segue pra Tática
        try {
          TCG.acoes.invocar(game, jogadorLocal, escolha[0]);
          if (!game.fimDeJogo) TCG.acoes.avancarFase(game); // invocou -> segue pra Tática
        } catch (e) {
          if (e instanceof TCG.AcaoInvalida) { log(`⚠ ${e.message}`); solicitarInvocacao(); return; }
          throw e;
        } finally {
          render();
        }
      },
      0, 1
    );
  }
  game.bus.on("faseAlterada", (e) => {
    if (e.faseNova === "INVOCACAO" && e.playerId === jogadorLocal) solicitarInvocacao();
  });

  function renderMao() {
    const container = el("mao-jogador");
    container.innerHTML = "";
    const jogavel = game.jogadorDaVez === jogadorLocal && game.fase === "TATICA";
    for (const carta of game.players[jogadorLocal].mao) {
      const div = document.createElement("div");
      div.className = "carta-mao";
      const img = document.createElement("img");
      img.src = carta.arquivo;
      img.alt = carta.nome;
      div.appendChild(img);
      comHoverPreview(div, carta);
      if (jogavel && ["Domínio", "Encantamento", "Maldição"].includes(carta.tipo)) {
        div.addEventListener("click", () => tentar(() => TCG.acoes.jogarCartaDeCampo(game, jogadorLocal, carta)));
      }
      container.appendChild(div);
    }
  }

  function renderControles() {
    const btnAtacar = el("btn-atacar");
    const btnFase = el("btn-fase");
    const monstroLocal = game.board[jogadorLocal].monstro;
    const podeAtacar = game.jogadorDaVez === jogadorLocal && game.fase === "COMBATE" && game.turno !== 1
      && monstroLocal && !monstroLocal.atacouNesteTurno;
    btnAtacar.style.display = game.fase === "COMBATE" ? "inline-block" : "none";
    btnAtacar.disabled = !podeAtacar;
    btnFase.disabled = game.jogadorDaVez !== jogadorLocal || !!game.fimDeJogo;
    btnFase.textContent = game.fase === "COMBATE" ? "Fim de Turno" : "Próxima Fase";
  }

  function renderStatus() {
    el("status-turno").innerHTML =
      `Turno <b>${game.turno}</b> — vez de <b>${game.players[game.jogadorDaVez].nome}</b> — Fase <b>${game.fase}</b>`;
  }

  function renderFim() {
    if (!game.fimDeJogo) { overlayFim.classList.remove("ativo"); return; }
    overlayFim.classList.add("ativo");
    const venceu = game.fimDeJogo.perdedor !== jogadorLocal;
    el("fim-titulo").textContent = venceu ? "Vitória!" : "Derrota";
    el("fim-titulo").style.color = venceu ? "var(--accent-2)" : "var(--perigo)";
    el("fim-motivo").textContent = `Motivo: ${game.fimDeJogo.motivo}`;
    el("fim-resumo").textContent =
      `${game.players[1].nome}: ${game.players[1].mana} mana / ${game.players[1].vida} vida — ` +
      `${game.players[2].nome}: ${game.players[2].mana} mana / ${game.players[2].vida} vida`;
  }

  function render() {
    renderStatus();
    renderLado(oponenteId, "tabuleiro-oponente", false);
    renderLado(jogadorLocal, "tabuleiro-jogador", true);
    renderMao();
    renderControles();
    renderFim();
  }

  // ---- selecao pendente (overlay) -----------------------------------------

  function renderOverlaySelecao(evento) {
    if (evento.playerId !== jogadorLocal) return; // selecao da IA resolve sozinha, nao mostra overlay
    overlaySelecao.classList.add("ativo");
    el("selecao-prompt").textContent = evento.prompt;
    const opcoesEl = el("selecao-opcoes");
    opcoesEl.innerHTML = "";
    for (const carta of evento.opcoes) {
      const img = document.createElement("img");
      img.src = carta.arquivo;
      img.alt = carta.nome;
      comHoverPreview(img, carta);
      img.addEventListener("click", () => {
        overlaySelecao.classList.remove("ativo");
        tentar(() => game.selection.resolver(evento.requestId, [carta]));
      });
      opcoesEl.appendChild(img);
    }

    const btnPularExistente = el("selecao-pular");
    if (btnPularExistente) btnPularExistente.remove();
    if (evento.minimo === 0) {
      const btnPular = document.createElement("button");
      btnPular.className = "acao";
      btnPular.id = "selecao-pular";
      btnPular.textContent = "Pular";
      btnPular.addEventListener("click", () => {
        overlaySelecao.classList.remove("ativo");
        tentar(() => game.selection.resolver(evento.requestId, []));
      });
      overlaySelecao.appendChild(btnPular);
    }
  }

  // ---- log via eventos -----------------------------------------

  const nomeDe = (c) => (c ? c.nome : "?");
  game.bus.on("faseAlterada", (e) => log(`Fase: ${game.players[e.playerId].nome} → ${e.faseNova}`));
  game.bus.on("cartaComprada", (e) => log(`${game.players[e.playerId].nome} comprou ${nomeDe(e.carta)}`));
  game.bus.on("combatenteInvocado", (e) => log(`${game.players[e.playerId].nome} invocou ${nomeDe(e.carta)}`));
  game.bus.on("manaAlterada", (e) => log(`${game.players[e.playerId].nome} mana ${e.delta >= 0 ? "+" : ""}${e.delta} → ${e.total}`));
  game.bus.on("vidaAlterada", (e) => log(`${game.players[e.playerId].nome} vida ${e.delta >= 0 ? "+" : ""}${e.delta} → ${e.total}`));
  game.bus.on("ataqueDeclarado", (e) => log(`${game.players[e.atacantePlayer].nome} ataca com ${nomeDe(e.atacante)}`));
  game.bus.on("danoCausado", (e) => log(`${e.quantidade} de dano em ${e.alvo ? nomeDe(e.alvo) : game.players[e.alvoPlayer].nome}`));
  game.bus.on("cartaDestruida", (e) => log(`${nomeDe(e.carta)} destruída (${e.motivo})`));
  game.bus.on("dominioAtivado", (e) => log(`${game.players[e.playerId].nome} ativou o Domínio ${nomeDe(e.carta)}`));
  game.bus.on("encantamentoJogado", (e) => log(`${game.players[e.playerId].nome} jogou ${nomeDe(e.carta)}`));
  game.bus.on("maldicaoColocada", (e) => log(`${game.players[e.playerId].nome} colocou uma Maldição virada para baixo`));
  game.bus.on("maldicaoAtivada", (e) => log(`${game.players[e.playerId].nome} revelou ${nomeDe(e.carta)}`));
  game.bus.on("habilidadeAtivada", (e) => log(`${game.players[e.playerId].nome} ativou a habilidade de ${nomeDe(e.carta)}`));
  game.bus.on("fimDeJogo", (e) => log(`FIM DE JOGO — ${game.players[e.perdedor].nome} perdeu (${e.motivo})`));
  game.bus.on("selecaoPedida", renderOverlaySelecao);

  // Qualquer selecao pedida ao lado que NAO e o jogador local (a IA) precisa
  // ser resolvida por alguem — sem isso, uma selecao pedida durante o turno
  // da IA (ex.: Ressurreição Arcana, ou a Maldição em resposta a um ataque,
  // ver TCG.acoes.atacar) ficaria pendente pra sempre e travaria o jogo.
  // Decide igual ao resto da IA: escolha aleatoria entre as opcoes legais.
  game.bus.on("selecaoPedida", (e) => {
    if (e.playerId === jogadorLocal) return; // esse caso quem trata e renderOverlaySelecao
    const opcoes = e.minimo === 0 ? [...e.opcoes, null] : e.opcoes;
    const escolha = game.rng.choice(opcoes);
    game.selection.resolver(e.requestId, escolha === null ? [] : [escolha]);
  });

  // ---- botoes -----------------------------------------

  // A Fase de Recurso e so compra+mana automaticos, sem decisao do jogador —
  // passa direto pra Invocação sozinha, sem exigir um clique so pra "sair" dela.
  function pularRecursoSeForAVez() {
    if (!game.fimDeJogo && game.jogadorDaVez === jogadorLocal && game.fase === "RECURSO") {
      TCG.acoes.avancarFase(game);
    }
  }

  el("btn-atacar").addEventListener("click", () => tentar(() => TCG.acoes.atacar(game, jogadorLocal, oponenteId)));
  el("btn-fase").addEventListener("click", () => {
    // "Próxima Fase" avança um passo só; só na Fase de Combate o botão vira
    // "Fim de Turno" e de fato fecha o turno do jogador local (terminarTurno
    // consome o resto da Fase de Combate e entrega a vez ao oponente).
    if (game.fase === "COMBATE") tentar(() => TCG.acoes.terminarTurno(game));
    else tentar(() => TCG.acoes.avancarFase(game));

    if (!game.fimDeJogo && game.jogadorDaVez === oponenteId) {
      tentar(() => TCG.executarTurnoIA(game, oponenteId));
    }
    tentar(pularRecursoSeForAVez);
  });
  el("btn-nova-partida").addEventListener("click", () => window.iniciarNovaPartida());
  el("btn-fechar-descarte").addEventListener("click", () => el("overlay-descarte").classList.remove("ativo"));

  mostrarPreview(null);
  pularRecursoSeForAVez();
  render();

  return { render };
};
