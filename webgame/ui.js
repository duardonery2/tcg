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
  const fxLayer = el("fx-layer");

  // Carta (objeto) -> DOM do slot/carta-mão que a representa AGORA MESMO.
  // Populado em elSlot()/renderMao() a cada render(); como é WeakMap, uma
  // carta que sai de campo/mão simplesmente some do mapa sozinha (não
  // precisa limpar manualmente). O pulo: um evento do bus dispara ANTES do
  // próximo render() (tentar() só chama render() no finally, depois que a
  // ação inteira — incluindo qualquer pausa por Maldição reativa — resolve),
  // então nesse instante o mapa ainda reflete o render ANTERIOR, com a
  // posição de tela onde a carta estava até agora — exatamente o que uma
  // animação de "saindo daqui" precisa.
  const elCartaAtual = new WeakMap();

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
    staggerFx = 0; // cada acao do jogador/IA e sua propria sequencia de animacao
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
      if (cartaPreview) elCartaAtual.set(cartaPreview, div);
    } else if (carta) {
      const img = document.createElement("img");
      img.src = carta.arquivo;
      img.alt = carta.nome;
      if (onClick) { div.classList.add("clicavel"); img.addEventListener("click", onClick); }
      comHoverPreview(img, carta);
      div.appendChild(img);
      elCartaAtual.set(carta, div);
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

  function elPilha(rotulo, quantidade, onClick, chave = "") {
    const wrap = document.createElement("div");
    wrap.className = "pilha";
    if (chave) wrap.dataset.pilha = chave; // landmark p/ animacoes (ver rectPilha)

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
    pilhaEsquerda.appendChild(elPilha("Descarte", game.descarte[playerId].length, () => mostrarDescarte(playerId), "descarte"));

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
    pilhaDireita.appendChild(elPilha("Baralho", TCG.Deck.restantes(game.baralhos[playerId]).length, null, "baralho"));
    pilhaDireita.appendChild(elPilha("Panteão", TCG.Deck.restantes(game.panteoes[playerId]).length, null, "panteao"));

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
      elCartaAtual.set(carta, div);
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

  // ---- FX: animações --------------------------------------------------
  //
  // Camada CSS-only por cima do render() de sempre (que continua refazendo
  // o tabuleiro do zero a cada ação) — ver style.css, seção "animações", e
  // o comentário de elCartaAtual acima. Duas famílias de efeito:
  //   - "em lugar" (fxPulso/fxShake): mexe direto num elemento que já está
  //     no layout normal (achado via elCartaAtual ou uma landmark fixa como
  //     a linha de magia) — usado quando o alvo continua onde está.
  //   - "de camada" (fxSpawnGhost/fxSpawnNumero/fxSpawnAnel/...): cria um
  //     elemento position:fixed dentro de #fx-layer, usado quando o alvo
  //     está mudando de zona (voa de uma pilha pra outra) ou pode já não
  //     existir mais na próxima renderização (destruição).
  //
  // Fila (`enfileirarFx`): TODO evento vira um "job" (uma função que recebe
  // `avancar` e chama ele — e só ele — quando a PRÓPRIA animação termina).
  // A fila roda um job de cada vez: o próximo só começa depois que o
  // anterior chama `avancar` (via animationend do elemento, com um
  // setTimeout de segurança) — nenhum evento é descartado nem sobreposto,
  // cada um tem sua vez, na ordem em que o jogo os disparou. `fxParalelo`
  // agrupa vários jobs que devem tocar JUNTOS como um único passo da fila
  // (ex.: o pulso E o número flutuante do mesmo golpe de dano).
  let filaFx = [];
  let filaFxOcupada = false;
  function enfileirarFx(job) {
    filaFx.push(job);
    processarFilaFx();
  }
  function processarFilaFx() {
    if (filaFxOcupada || filaFx.length === 0) return;
    filaFxOcupada = true;
    const job = filaFx.shift();
    job(() => {
      filaFxOcupada = false;
      // via setTimeout (não direto): evita empilhar a pilha de chamadas
      // quando vários jobs seguidos "avançam" na hora (alvo não encontrado
      // — ver os primitivos abaixo, todos chamam avancar() de graça nesse caso).
      setTimeout(processarFilaFx, 0);
    });
  }
  // pra scripts de teste conseguirem esperar a fila esvaziar de verdade em
  // vez de adivinhar um tempo fixo (ver scripts/testar_webgame_playwright.py).
  function filaFxVazia() { return !filaFxOcupada && filaFx.length === 0; }

  // agrupa N jobs que devem tocar ao mesmo tempo (um único passo da fila);
  // só avança quando TODOS terminarem.
  function fxParalelo(...tarefas) {
    return (avancar) => {
      let restantes = tarefas.length;
      if (restantes === 0) { avancar(); return; }
      const parcial = () => { restantes -= 1; if (restantes <= 0) avancar(); };
      for (const tarefa of tarefas) tarefa(parcial);
    };
  }

  function containerIdDe(playerId) {
    return playerId === jogadorLocal ? "tabuleiro-jogador" : "tabuleiro-oponente";
  }
  function rectDe(seletor) {
    const elemento = document.querySelector(seletor);
    return elemento ? elemento.getBoundingClientRect() : null;
  }
  function rectPilha(playerId, chave) { return rectDe(`#${containerIdDe(playerId)} [data-pilha="${chave}"] .slot`); }
  function rectMonstro(playerId) { return rectDe(`#${containerIdDe(playerId)} .linha-monstro .slot`); }
  function rectLinhaMagia(playerId) { return rectDe(`#${containerIdDe(playerId)} .linha-magia`); }
  // um slot do TAMANHO de uma carta dentro da linha de magia (não a linha
  // inteira, que esticaria uma revelação de Maldição) — usado quando
  // elCartaAtual não tem a carta mapeada (Maldição do OPONENTE, nunca
  // exposta em cartaPreview antes de revelar — ver elSlot/renderLado).
  function rectSlotDeMagia(playerId) { return rectDe(`#${containerIdDe(playerId)} .linha-magia .slot`); }
  function rectInfoLado(playerId) { return rectDe(`#${containerIdDe(playerId)} .info-lado`); }
  function rectMaoLocal() { return rectDe("#mao-jogador"); }
  // destino da animação de compra: um retângulo do TAMANHO de uma carta
  // (não a mão inteira, que esticaria a arte) — ancorado onde a carta nova
  // realmente vai cair (a última posição da mão, já que renderMao() sempre
  // adiciona na ordem de game.players[jogadorLocal].mao); com a mão vazia,
  // aproxima pelo tamanho real de .carta-mao (14vh, 5:7 — ver style.css).
  function rectProximoSlotDeMao() {
    const maoRect = rectMaoLocal();
    if (!maoRect) return null;
    const cartas = document.querySelectorAll("#mao-jogador .carta-mao");
    if (cartas.length) {
      const ultima = cartas[cartas.length - 1].getBoundingClientRect();
      return { left: maoRect.right - ultima.width, top: ultima.top, width: ultima.width, height: ultima.height };
    }
    const altura = window.innerHeight * 0.14;
    const largura = altura * (5 / 7);
    return { left: maoRect.left + maoRect.width / 2 - largura / 2, top: maoRect.bottom - altura, width: largura, height: altura };
  }

  // Remove o elemento e chama `avancar` quando a animação termina
  // (animationend/transitionend, com um setTimeout de segurança caso o
  // evento não dispare por algum motivo) — usado pelos primitivos "de camada".
  function fxRemoverEAvancar(elemento, vidaMs, avancar) {
    let feito = false;
    const terminar = () => {
      if (feito) return;
      feito = true;
      elemento.remove();
      avancar();
    };
    elemento.addEventListener("animationend", terminar);
    elemento.addEventListener("transitionend", terminar);
    setTimeout(terminar, vidaMs + 80);
  }

  function corDe(tipo) {
    return tipo === "dano" ? "var(--fx-dano)" : tipo === "cura" ? "var(--fx-cura)" : "var(--fx-destaque)";
  }

  // "em lugar": pulso/aviso num elemento que já está no layout normal.
  // Se o alvo não existe (carta fabricada de teste, evento sem contexto
  // visual), avança a fila na hora — nada a esperar.
  // `grande`: variante maior/mais demorada, usada pro impacto de dano —
  // ver style.css ".fx-pulso.grande" (fx-pulso-grande, 550ms).
  function fxPulso(elemento, tipo, avancar, grande = false) {
    if (!elemento) { avancar(); return; }
    elemento.style.setProperty("--fx-cor", corDe(tipo));
    elemento.classList.add("fx-pulso");
    if (grande) elemento.classList.add("grande");
    let feito = false;
    const terminar = () => {
      if (feito) return;
      feito = true;
      elemento.classList.remove("fx-pulso", "grande");
      avancar();
    };
    elemento.addEventListener("animationend", terminar, { once: true });
    setTimeout(terminar, grande ? 650 : 400);
  }
  function fxShake(elemento, avancar) {
    if (!elemento) { avancar(); return; }
    elemento.classList.add("fx-shake");
    let feito = false;
    const terminar = () => {
      if (feito) return;
      feito = true;
      elemento.classList.remove("fx-shake");
      avancar();
    };
    elemento.addEventListener("animationend", terminar, { once: true });
    setTimeout(terminar, 320);
  }

  // "de camada": elementos soltos dentro de #fx-layer.
  function fxSpawnGhost(rectOrigem, rectDestino, imgSrc, avancar, duracaoMs = 380) {
    if (!rectOrigem || !rectDestino || !imgSrc) { avancar(); return; }
    const img = document.createElement("img");
    img.className = "fx-ghost";
    img.src = imgSrc;
    img.style.setProperty("--x0", `${rectOrigem.left}px`);
    img.style.setProperty("--y0", `${rectOrigem.top}px`);
    img.style.setProperty("--w0", `${rectOrigem.width}px`);
    img.style.setProperty("--h0", `${rectOrigem.height}px`);
    img.style.setProperty("--x1", `${rectDestino.left}px`);
    img.style.setProperty("--y1", `${rectDestino.top}px`);
    img.style.setProperty("--w1", `${rectDestino.width}px`);
    img.style.setProperty("--h1", `${rectDestino.height}px`);
    img.style.setProperty("--fx-duracao", `${duracaoMs}ms`);
    fxLayer.appendChild(img);
    fxRemoverEAvancar(img, duracaoMs, avancar);
  }
  // `grande`: maior e some mais devagar — usado pros números de dano (ver
  // style.css ".fx-num.grande", fx-float-num-grande, 1100ms).
  function fxSpawnNumero(rect, texto, tipo, avancar, grande = false) {
    if (!rect) { avancar(); return; }
    const div = document.createElement("div");
    div.className = "fx-num" + (grande ? " grande" : "");
    div.textContent = texto;
    div.style.left = `${rect.left + rect.width / 2}px`;
    div.style.top = `${rect.top + rect.height * 0.25}px`;
    div.style.setProperty("--fx-cor", corDe(tipo));
    fxLayer.appendChild(div);
    fxRemoverEAvancar(div, grande ? 1100 : 700, avancar);
  }
  function fxSpawnAnel(rect, tipo, avancar) {
    if (!rect) { avancar(); return; }
    const div = document.createElement("div");
    div.className = "fx-anel";
    div.style.left = `${rect.left}px`;
    div.style.top = `${rect.top}px`;
    div.style.width = `${rect.width}px`;
    div.style.height = `${rect.height}px`;
    div.style.setProperty("--fx-cor", corDe(tipo));
    fxLayer.appendChild(div);
    fxRemoverEAvancar(div, 420, avancar);
  }

  // Revelação de Maldição: um flip 3D de verdade (verso -> arte real), não
  // só um flash — é o momento mais dramático de reagir a uma Maldição
  // setada, merece uma animação própria em vez de reaproveitar o anel de
  // destruição com outra cor.
  function fxSpawnFlip(rect, imgSrc, avancar, duracaoMs = 620) {
    if (!rect || !imgSrc) { avancar(); return; }
    const flip = document.createElement("div");
    flip.className = "fx-flip";
    flip.style.left = `${rect.left}px`;
    flip.style.top = `${rect.top}px`;
    flip.style.width = `${rect.width}px`;
    flip.style.height = `${rect.height}px`;
    flip.style.setProperty("--fx-duracao", `${duracaoMs}ms`);
    const interior = document.createElement("div");
    interior.className = "fx-flip-interior";
    const verso = document.createElement("div");
    verso.className = "fx-flip-verso";
    const frente = document.createElement("div");
    frente.className = "fx-flip-frente";
    const img = document.createElement("img");
    img.src = imgSrc;
    frente.appendChild(img);
    interior.appendChild(verso);
    interior.appendChild(frente);
    flip.appendChild(interior);
    fxLayer.appendChild(flip);
    fxRemoverEAvancar(flip, duracaoMs, avancar);
  }

  // Cura: um brilho suave que se expande, bem diferente do pulso seco de
  // buff/dano (fx-pulso) — a cura é reconfortante, não um impacto.
  function fxSpawnBloom(rect, avancar, duracaoMs = 750) {
    if (!rect) { avancar(); return; }
    const div = document.createElement("div");
    div.className = "fx-cura-bloom";
    const pad = Math.max(rect.width, rect.height) * 0.35;
    div.style.left = `${rect.left - pad / 2}px`;
    div.style.top = `${rect.top - pad / 2}px`;
    div.style.width = `${rect.width + pad}px`;
    div.style.height = `${rect.height + pad}px`;
    div.style.setProperty("--fx-duracao", `${duracaoMs}ms`);
    fxLayer.appendChild(div);
    fxRemoverEAvancar(div, duracaoMs, avancar);
  }

  // combatenteInvocado: voa do Panteão até o slot de Monstro — o slot já
  // existe vazio no esqueleto do tabuleiro, não precisa esperar o próximo render.
  game.bus.on("combatenteInvocado", (e) => {
    enfileirarFx((avancar) => fxSpawnGhost(rectPilha(e.playerId, "panteao"), rectMonstro(e.playerId), e.carta.arquivo, avancar));
  });

  // cartaComprada: mesmo tratamento do summon (Baralho -> um retângulo do
  // tamanho de uma carta, não a mão inteira esticada) — só que voando pro
  // jogador LOCAL; a mão do oponente não tem slots por carta pra mirar, só
  // um pulso na pilha do Baralho dele.
  game.bus.on("cartaComprada", (e) => {
    if (e.playerId === jogadorLocal) {
      enfileirarFx((avancar) => fxSpawnGhost(rectPilha(e.playerId, "baralho"), rectProximoSlotDeMao(), e.carta.arquivo, avancar));
    } else {
      enfileirarFx((avancar) => fxPulso(document.querySelector(`#${containerIdDe(e.playerId)} [data-pilha="baralho"] .slot`), "destaque", avancar));
    }
  });

  // cartaDescartada: de onde a carta estava (mão ou campo, via elCartaAtual)
  // até a pilha de Descarte.
  game.bus.on("cartaDescartada", (e) => {
    const elemento = elCartaAtual.get(e.carta);
    const origem = elemento ? elemento.getBoundingClientRect()
      : (e.playerId === jogadorLocal ? rectMaoLocal() : rectLinhaMagia(e.playerId));
    enfileirarFx((avancar) => fxSpawnGhost(origem, rectPilha(e.playerId, "descarte"), e.carta.arquivo, avancar));
  });

  // cartaSeraDestruida + cartaDestruida: sempre disparam em sequência pra
  // MESMA carta (ver DestructionSystem/TCG.destroyCard) — cada uma seu
  // próprio passo da fila, na ordem que já vêm: primeiro um anel no lugar
  // onde ela está (ainda visível nesse instante), depois o voo até o
  // Descarte (ou Panteão, se Valhalla redirecionou — não dá pra saber aqui
  // sem o contexto, então sempre mira o Descarte; a contagem da pilha real
  // só aparece no próximo render de qualquer forma).
  game.bus.on("cartaSeraDestruida", (e) => {
    const elemento = elCartaAtual.get(e.carta);
    if (elemento) enfileirarFx((avancar) => fxSpawnAnel(elemento.getBoundingClientRect(), "dano", avancar));
  });
  game.bus.on("cartaDestruida", (e) => {
    if (e.playerId === null) return; // carta sem dono nesse contexto — nada a animar
    const elemento = elCartaAtual.get(e.carta);
    const origem = elemento ? elemento.getBoundingClientRect() : (rectMonstro(e.playerId) || rectLinhaMagia(e.playerId));
    enfileirarFx((avancar) => fxSpawnGhost(origem, rectPilha(e.playerId, "descarte"), e.carta.arquivo, avancar));
  });

  // ataqueDeclarado: uma leve vibração no atacante, a "batida" de tensão
  // antes do impacto.
  game.bus.on("ataqueDeclarado", (e) => {
    enfileirarFx((avancar) => fxShake(elCartaAtual.get(e.atacante), avancar));
  });

  // danoCausado + vidaAlterada: o número flutuante aparece UMA vez só — se
  // vidaAlterada é o gêmeo direto do dano que acabou de aparecer (mesmo
  // jogador, mesma quantidade em módulo), não duplica. Dano usa a variante
  // "grande" (maior e fica mais tempo na tela, ver style.css) — é o
  // impacto mais importante de acompanhar numa partida. Pulso+número do
  // MESMO golpe tocam JUNTOS (fxParalelo) — são a mesma batida, não dois passos.
  let ultimoDanoDireto = null;
  game.bus.on("danoCausado", (e) => {
    ultimoDanoDireto = { alvoPlayer: e.alvoPlayer, quantidade: e.quantidade };
    if (e.alvo) {
      const elemento = elCartaAtual.get(e.alvo);
      if (elemento) {
        const rect = elemento.getBoundingClientRect();
        enfileirarFx(fxParalelo(
          (avancar) => fxPulso(elemento, "dano", avancar, true),
          (avancar) => fxSpawnNumero(rect, `-${e.quantidade}`, "dano", avancar, true)
        ));
      }
    } else {
      enfileirarFx((avancar) => fxSpawnNumero(rectInfoLado(e.alvoPlayer), `-${e.quantidade}`, "dano", avancar, true));
    }
  });
  game.bus.on("vidaAlterada", (e) => {
    if (ultimoDanoDireto && ultimoDanoDireto.alvoPlayer === e.playerId && e.delta === -ultimoDanoDireto.quantidade) {
      ultimoDanoDireto = null;
      return;
    }
    const perda = e.delta < 0;
    enfileirarFx((avancar) =>
      fxSpawnNumero(rectInfoLado(e.playerId), `${e.delta >= 0 ? "+" : ""}${e.delta}`, perda ? "dano" : "cura", avancar, perda));
  });

  // habilidadeAtivada: brilho no próprio combatente que ativou.
  game.bus.on("habilidadeAtivada", (e) => {
    enfileirarFx((avancar) => fxPulso(elCartaAtual.get(e.carta), "destaque", avancar));
  });

  // dominioAtivado/encantamentoJogado/maldicaoColocada ("jogar carta de
  // campo" — mesma família de combatenteInvocado/cartaComprada): mesmo
  // tratamento do summon — voa de onde a carta REALMENTE estava na mão
  // (elCartaAtual ainda aponta pro DOM do render ANTERIOR nesse instante,
  // ver comentário de elCartaAtual acima) até um slot do TAMANHO de uma
  // carta na linha de magia (rectSlotDeMagia), não a linha inteira esticada.
  // A mão do OPONENTE nunca é renderizada carta a carta (só a contagem —
  // ver renderMao, que só desenha game.players[jogadorLocal].mao), então
  // elCartaAtual nunca tem uma carta da mão dele mapeada: cair pra
  // rectMaoLocal() nesse caso seria a mão ERRADA (a do jogador local,
  // sempre embaixo na tela) — usa o "info-lado" do DONO de verdade.
  function origemNaMaoDe(carta, playerId) {
    const elemento = elCartaAtual.get(carta);
    if (elemento) return elemento.getBoundingClientRect();
    return playerId === jogadorLocal ? rectMaoLocal() : rectInfoLado(playerId);
  }
  game.bus.on("dominioAtivado", (e) => {
    const origem = origemNaMaoDe(e.carta, e.playerId);
    enfileirarFx((avancar) => fxSpawnGhost(origem, rectSlotDeMagia(e.playerId), e.carta.arquivo, avancar));
  });
  game.bus.on("encantamentoJogado", (e) => {
    const origem = origemNaMaoDe(e.carta, e.playerId);
    enfileirarFx((avancar) => fxSpawnGhost(origem, rectSlotDeMagia(e.playerId), e.carta.arquivo, avancar));
  });

  // maldicaoColocada: NUNCA mostra a arte real de uma Maldição do OPONENTE
  // sendo setada — vazaria a identidade da carta (ver testar_maldicao_oculta
  // em scripts/testar_webgame_playwright.py). A própria Maldição do jogador
  // local pode voar normalmente, igual a um Domínio/Encantamento; a do
  // oponente só ganha um pulso genérico num slot da linha de magia dele.
  game.bus.on("maldicaoColocada", (e) => {
    if (e.playerId === jogadorLocal) {
      const origem = origemNaMaoDe(e.carta, e.playerId);
      enfileirarFx((avancar) => fxSpawnGhost(origem, rectSlotDeMagia(e.playerId), e.carta.arquivo, avancar));
    } else {
      enfileirarFx((avancar) => fxPulso(document.querySelector(`#${containerIdDe(e.playerId)} .linha-magia .slot`), "destaque", avancar));
    }
  });

  // maldicaoAtivada: nesse momento a carta já virou pra cima (pública pros
  // dois lados), então mostrar a arte real não vaza nada mais — um flip 3D
  // de verdade (verso -> arte), não só um flash. `elCartaAtual` só tem essa
  // carta mapeada se for a Maldição do PRÓPRIO jogador local (cartaPreview,
  // ver elSlot/renderLado); pra Maldição do oponente, cai num slot do
  // tamanho certo dentro da linha de magia dele (rectSlotDeMagia).
  game.bus.on("maldicaoAtivada", (e) => {
    const elemento = elCartaAtual.get(e.carta);
    const rect = elemento ? elemento.getBoundingClientRect() : rectSlotDeMagia(e.playerId);
    enfileirarFx((avancar) => fxSpawnFlip(rect, e.carta.arquivo, avancar));
  });

  // statusAlterado (buff/debuff/cura — ver TCG.buff/TCG.curar): sinal
  // genérico, cobre efeitos de Habilidade/Domínio/Maldição sem precisar
  // saber qual carta causou (frequentemente é uma carta DIFERENTE da
  // nomeada no evento que disparou o efeito). Cura ganha um tratamento
  // PRÓPRIO (brilho que se expande) em vez do pulso seco de buff/dano —
  // reconfortante, não um impacto. Cada statusAlterado é um único passo
  // da fila (pulso/brilho + número tocam JUNTOS, fxParalelo).
  game.bus.on("statusAlterado", (e) => {
    const elemento = elCartaAtual.get(e.carta);
    if (!elemento) return;
    const rect = elemento.getBoundingClientRect();
    if (e.origem === "cura") {
      enfileirarFx(fxParalelo(
        (avancar) => fxSpawnBloom(rect, avancar),
        (avancar) => fxSpawnNumero(rect, `+${e.delta}`, "cura", avancar)
      ));
      return;
    }
    const tipo = e.delta > 0 ? "cura" : "dano";
    enfileirarFx(fxParalelo(
      (avancar) => fxPulso(elemento, tipo, avancar),
      (avancar) => fxSpawnNumero(rect, `${e.delta >= 0 ? "+" : ""}${e.delta}`, tipo, avancar)
    ));
  });

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

  return { render, filaFxVazia };
};
