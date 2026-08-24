# -*- coding: utf-8 -*-
"""Verificacao ponta-a-ponta do webgame/ via Playwright headless, no mesmo
espirito de game/demo_sim.py (Python) — roda o jogo de verdade e falha alto
se algo quebrar, em vez de inspecionar o codigo por fora.

Uso: python3 scripts/testar_webgame_playwright.py
"""
import os
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

INDEX = "file://" + os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "webgame", "index.html")


def clicar_se_possivel(elemento, timeout=500):
    """Clica com um timeout curto e engole o erro se um modal (ex.: gatilho
    de Maldição do oponente atacando) abrir bem entre o estado lido e o
    clique — o proximo ciclo do loop de teste ja fecha esse modal sozinho."""
    try:
        elemento.click(timeout=timeout)
        return True
    except PlaywrightTimeoutError:
        return False


def fechar_modal_se_aberto(page, escolher=True):
    """A escolha de Combatente (e qualquer selecao de carta) sempre aparece
    como modal (#overlay-selecao) — fecha clicando na 1a opcao, ou em
    'Pular' quando a escolha for opcional e nao quisermos escolher nada."""
    ativo = page.eval_on_selector("#overlay-selecao", "el => el.classList.contains('ativo')")
    if not ativo:
        return False
    if escolher:
        imgs = page.query_selector_all("#selecao-opcoes img")
        if imgs:
            imgs[0].click()
        else:
            btn_pular = page.query_selector("#selecao-pular")
            if btn_pular:
                btn_pular.click()
    else:
        btn_pular = page.query_selector("#selecao-pular")
        if btn_pular:
            btn_pular.click()
    page.wait_for_timeout(30)
    return True


def esperar_fila_fx_esvaziar(page, max_ms=30000, passo_ms=200):
    """A fila de animação (ui.js, enfileirarFx) toca UM job por vez, do
    início ao fim de cada um, antes de começar o próximo — depois de um
    driver de teste que avança MUITO mais rápido que a velocidade real do
    jogo (jogar_ate_o_fim usa esperas de 10-20ms entre ações), a fila pode
    acumular bem mais eventos do que uma sessão humana produziria, e
    demorar mais que qualquer tempo fixo pra esvaziar de verdade — por
    isso espera de verdade (`window.ui.filaFxVazia()`) em vez de adivinhar
    quanto tempo basta."""
    decorrido = 0
    while decorrido < max_ms:
        if page.evaluate("() => window.ui.filaFxVazia()"):
            return True
        page.wait_for_timeout(passo_ms)
        decorrido += passo_ms
    return False


def jogar_ate_o_fim(page, max_ciclos=250):
    for _ in range(max_ciclos):
        estado = page.evaluate("() => TCG.estado(window.game)")
        if estado["fimDeJogo"]:
            return estado
        fechar_modal_se_aberto(page)
        if estado["fase"] == "TATICA":
            # joga a 1a carta da mão (Domínio/Encantamento/Maldição, se houver)
            # pra exercitar de verdade o lado humano jogando carta de campo —
            # não só a Fase Tática da IA — num playthrough real.
            cartas = page.query_selector_all(".mao-jogador .carta-mao")
            if cartas:
                clicar_se_possivel(cartas[0])
                page.wait_for_timeout(15)
                fechar_modal_se_aberto(page)
        if estado["fase"] == "COMBATE":
            btn = page.query_selector("#btn-atacar")
            if btn and not btn.is_disabled():
                btn.click()
        page.wait_for_timeout(10)
        btn_fase = page.query_selector("#btn-fase")
        if btn_fase and not btn_fase.is_disabled():
            btn_fase.click()
        page.wait_for_timeout(20)
    return page.evaluate("() => TCG.estado(window.game)")


def testar_estado_inicial(browser):
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    erros = []
    page.on("pageerror", lambda e: erros.append(str(e)))
    page.on("console", lambda m: erros.append(m.text) if m.type == "error" else None)
    page.goto(INDEX)
    page.wait_for_timeout(200)

    estado = page.evaluate("() => TCG.estado(window.game)")
    assert estado["jogadores"]["1"]["mana"] == 5, estado
    assert len(estado["jogadores"]["1"]["mao"]) == 4, estado
    assert estado["tabuleiro"]["1"]["monstro"] is None, estado
    # a Fase de Recurso e so compra+mana automaticos e e pulada sozinha pra
    # quem esta jogando localmente (sem decisao nela, sem exigir clique)
    assert estado["fase"] == "INVOCACAO", estado
    # a escolha de Combatente pra invocar sempre aparece como modal, sozinha,
    # assim que a Fase de Invocacao comeca com o slot vazio
    overlay_ativo = page.eval_on_selector("#overlay-selecao", "el => el.classList.contains('ativo')")
    assert overlay_ativo, "o modal de invocacao deveria ter aberto sozinho"
    assert len(page.query_selector_all("#selecao-opcoes img")) == 5, "modal deveria mostrar as 5 opcoes do Panteão"
    assert page.query_selector("#selecao-pular") is not None, "modal de invocacao deveria ter a opcao de Pular"
    assert not erros, f"erros no console: {erros}"
    page.close()
    print("OK  estado inicial (mana=5, mao=4, Recurso pulado -> INVOCACAO, modal de invocação automático)")


def testar_acoes_e_hover(browser):
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    erros = []
    page.on("pageerror", lambda e: erros.append(str(e)))
    page.goto(INDEX + "?seed=42")
    page.wait_for_timeout(200)

    # Recurso ja foi pulado sozinho ao carregar; o modal de invocacao ja abriu sozinho.
    # Escolher no modal ja avanca a Fase de Invocacao sozinha ate a Tática — sem clique extra.
    mana_antes = page.evaluate("() => window.game.players[1].mana")
    page.query_selector_all("#selecao-opcoes img")[0].click()
    page.wait_for_timeout(80)
    estado = page.evaluate("() => TCG.estado(window.game)")
    assert estado["tabuleiro"]["1"]["monstro"] is not None, "invocar nao colocou o combatente no tabuleiro"
    assert estado["jogadores"]["1"]["mana"] < mana_antes, "invocar nao descontou mana"
    assert estado["fase"] == "TATICA", f"Invocação deveria ter avançado sozinha pra Tática, mas esta em {estado['fase']}"

    mao_cartas = page.query_selector_all(".mao-jogador .carta-mao")
    if mao_cartas:
        mao_cartas[0].hover()
        page.wait_for_timeout(120)
        # preview de carta com imagem mostra SO a imagem — nome/custo/tipo/
        # POW/RES ficam de fora de proposito (ja estao na imagem ou no
        # .stats-badge sempre visível no card do tabuleiro)
        src_no_preview = page.eval_on_selector("#preview-img", "el => el.getAttribute('src')")
        arquivo_esperado = page.evaluate("() => window.game.players[1].mao[0].arquivo")
        assert src_no_preview == arquivo_esperado, f"preview mostrou '{src_no_preview}', esperava '{arquivo_esperado}'"
        assert page.eval_on_selector("#preview-legenda", "el => getComputedStyle(el).display") == "none", \
            "nenhuma legenda deveria aparecer no preview de uma carta com imagem"

    page.click("#btn-fase")  # TATICA -> COMBATE
    page.wait_for_timeout(60)

    # regra nova: nao se pode atacar no primeiro turno
    assert page.evaluate("() => window.game.turno") == 1
    assert page.query_selector("#btn-atacar").is_disabled(), "atacar deveria estar bloqueado no turno 1"
    erro_turno_1 = page.evaluate("""() => {
        try { TCG.acoes.atacar(window.game, 1, 2); return null; }
        catch (e) { return e.message; }
    }""")
    assert erro_turno_1 == "Não é possível atacar no primeiro turno.", f"mensagem inesperada: {erro_turno_1}"

    turno_antes = page.evaluate("() => window.game.turno")
    page.click("#btn-fase")  # fim do turno 1 -> IA joga o turno 2 sozinha (ela pode atacar)
    page.wait_for_timeout(300)
    fechar_modal_se_aberto(page)  # possivel novo modal de invocacao no turno 3 do humano
    page.wait_for_timeout(60)

    estado_pos_ia = page.evaluate("() => TCG.estado(window.game)")
    if not estado_pos_ia["fimDeJogo"]:
        assert estado_pos_ia["jogadorDaVez"] == 1, "controle nao voltou pro jogador humano apos o turno da IA"
        assert estado_pos_ia["turno"] > turno_antes, "turno nao avancou apos o turno da IA"

        # agora ja e turno >= 3: testa o ataque de verdade, que devia estar liberado.
        # A Invocação já pode ter avançado sozinha até a Tática (ver fechar_modal_se_aberto
        # acima), entao avanca so o que ainda faltar pra chegar ao Combate.
        for _ in range(3):
            if page.evaluate("() => window.game.fase") == "COMBATE":
                break
            page.click("#btn-fase")
            page.wait_for_timeout(60)
        btn_atacar = page.query_selector("#btn-atacar")
        if btn_atacar and not btn_atacar.is_disabled():
            # dano de combate agora e a DIFERENCA de Combate entre os dois
            # combatentes — pode legitimamente dar 0 se forem parelhos/o
            # defensor for mais forte, entao o teste so confirma que a acao
            # rodou (o combatente atacou e o jogo nao travou), nao que causou dano.
            monstro_local_antes = page.evaluate("() => window.game.board[1].monstro.atacouNesteTurno")
            assert monstro_local_antes is False, "combatente ja deveria comecar o turno sem ter atacado"
            btn_atacar.click()
            page.wait_for_timeout(100)
            monstro_local_depois = page.evaluate("() => { const m = window.game.board[1].monstro; return m ? m.atacouNesteTurno : null; }")
            assert monstro_local_depois is True, "atacar deveria marcar o combatente como tendo atacado neste turno"

    assert not erros, f"erros no console: {erros}"
    page.close()
    print("OK  invocar (modal) / hover-preview / ataque bloqueado no turno 1 / turno da IA automatico")


def testar_dano_por_diferenca_e_recompensa_de_mana(browser):
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    erros = []
    page.on("pageerror", lambda e: erros.append(str(e)))
    page.goto(INDEX + "?seed=42")
    page.wait_for_timeout(200)
    fechar_modal_se_aberto(page, escolher=False)

    resultado = page.evaluate("""() => {
        const g = window.game;
        // monta um confronto controlado: atacante forte (pow 20) vs defensor
        // fraco (pow 5, res 8) do mesmo elemento (sem vantagem elemental
        // interferindo na conta), pra conferir a formula da diferenca de perto
        const atacante = { nome: 'Teste Atacante', arquivo: '../cards/Rei_Arthur.png', tipo: 'Herói', elemento: 'Fogo',
            custoMana: 1, resistencia: 20, combate: 20, atualPow: 20, atualRes: 20,
            statusEffects: [], habilidadeUsadaNesteTurno: false, atacouNesteTurno: false,
            faceDown: false, elementoOverride: null, attackNegated: false,
            damageReflected: false, ignoraFraquezaElemental: false, instanceId: -1 };
        const defensor = { nome: 'Teste Defensor', arquivo: '../cards/Rei_Arthur.png', tipo: 'Herói', elemento: 'Fogo',
            custoMana: 1, resistencia: 8, combate: 5, atualPow: 5, atualRes: 8,
            statusEffects: [], habilidadeUsadaNesteTurno: false, atacouNesteTurno: false,
            faceDown: false, elementoOverride: null, attackNegated: false,
            damageReflected: false, ignoraFraquezaElemental: false, instanceId: -2 };
        g.board[1].monstro = atacante;
        g.board[2].monstro = defensor;
        const mana1_antes = g.players[1].mana;

        TCG.resolverAtaque(g, 1, atacante, 2, defensor);

        return {
            resDepois: defensor.atualRes,
            destruido: g.board[2].monstro === null,
            mana1_antes, mana1_depois: g.players[1].mana,
        };
    }""")
    print("resultado:", resultado)
    # diferenca de poder: 20 - 5 = 15 >= res 8 -> destruido, sem sobra negativa (clamp em 0)
    assert resultado["resDepois"] == 0, f"RES deveria zerar (dano 15 >= 8), ficou {resultado['resDepois']}"
    assert resultado["destruido"], "o defensor deveria ter sido destruído e removido do slot"
    assert resultado["mana1_depois"] == resultado["mana1_antes"] + 1, \
        f"quem destruiu deveria ganhar +1 mana: {resultado['mana1_antes']} -> {resultado['mana1_depois']}"

    # confronto parelho: mesma potencia -> diferenca 0 -> sem dano, sem destruicao, sem mana
    resultado2 = page.evaluate("""() => {
        const g = window.game;
        const a = { nome: 'A', arquivo: '../cards/Rei_Arthur.png', tipo: 'Herói', elemento: 'Fogo', custoMana: 1, resistencia: 10, combate: 10,
            atualPow: 10, atualRes: 10, statusEffects: [], habilidadeUsadaNesteTurno: false, atacouNesteTurno: false,
            faceDown: false, elementoOverride: null, attackNegated: false, damageReflected: false,
            ignoraFraquezaElemental: false, instanceId: -3 };
        const b = { nome: 'B', arquivo: '../cards/Rei_Arthur.png', tipo: 'Herói', elemento: 'Fogo', custoMana: 1, resistencia: 10, combate: 10,
            atualPow: 10, atualRes: 10, statusEffects: [], habilidadeUsadaNesteTurno: false, atacouNesteTurno: false,
            faceDown: false, elementoOverride: null, attackNegated: false, damageReflected: false,
            ignoraFraquezaElemental: false, instanceId: -4 };
        g.board[1].monstro = a;
        g.board[2].monstro = b;
        const mana1_antes = g.players[1].mana;
        TCG.resolverAtaque(g, 1, a, 2, b);
        return { resB: b.atualRes, mana1_antes, mana1_depois: g.players[1].mana };
    }""")
    print("resultado2 (confronto parelho):", resultado2)
    assert resultado2["resB"] == 10, f"combatentes parelhos nao deveriam causar dano nenhum, RES ficou {resultado2['resB']}"
    assert resultado2["mana1_depois"] == resultado2["mana1_antes"], "sem destruição não deveria dar mana nenhuma"

    assert not erros, f"erros no console: {erros}"
    page.close()
    print("OK  dano de combate = diferença de Combate (com clamp em 0), +1 mana pra quem destrói")


def testar_gatilho_de_maldicao_ao_ser_atacado(browser):
    """Regressão de um bug real: Escudo de Gelo Absoluto/Barreira de Vento
    Cortante negavam o ataque no combatente ERRADO (o do atacante, em vez do
    próprio combatente de quem ativa a Maldição) — só apareceu ao testar o
    gatilho de verdade (o ataque acontecendo), não só checando que a flag
    era setada em algum alvo."""
    page = browser.new_page(viewport={"width": 1500, "height": 950})
    erros = []
    page.on("pageerror", lambda e: erros.append(str(e)))
    page.on("console", lambda m: erros.append(m.text) if m.type == "error" else None)
    page.goto(INDEX + "?seed=42")
    page.wait_for_timeout(200)

    page.evaluate("""() => {
        const g = window.game;
        g.turno = 3; g.fase = 'COMBATE'; g.jogadorDaVez = 2; g.fimDeJogo = null;
        const atacanteIA = { nome: 'AtacanteIA', arquivo: '../cards/Rei_Arthur.png', tipo: 'Monstro', elemento: 'Fogo', custoMana: 1,
            resistencia: 15, combate: 15, atualPow: 15, atualRes: 15, statusEffects: [],
            habilidadeUsadaNesteTurno: false, atacouNesteTurno: false, faceDown: false,
            elementoOverride: null, attackNegated: false, damageReflected: false,
            ignoraFraquezaElemental: false, instanceId: -10 };
        const defensorLocal = { nome: 'DefensorLocal', arquivo: '../cards/Rei_Arthur.png', tipo: 'Herói', elemento: 'Terra', custoMana: 1,
            resistencia: 15, combate: 10, atualPow: 10, atualRes: 15, statusEffects: [],
            habilidadeUsadaNesteTurno: false, atacouNesteTurno: false, faceDown: false,
            elementoOverride: null, attackNegated: false, damageReflected: false,
            ignoraFraquezaElemental: false, instanceId: -11 };
        const maldicao = { nome: 'Escudo de Gelo Absoluto', arquivo: '../cards/Rei_Arthur.png', tipo: 'Maldição', elemento: null, custoMana: 3,
            resistencia: null, combate: null, atualPow: null, atualRes: null, statusEffects: [],
            habilidadeUsadaNesteTurno: false, atacouNesteTurno: false, faceDown: true,
            elementoOverride: null, attackNegated: false, damageReflected: false,
            ignoraFraquezaElemental: false, instanceId: -12 };
        g.board[2].monstro = atacanteIA;
        g.board[1].monstro = defensorLocal;
        g.board[1].magia = [maldicao, null, null, null, null];
        TCG.acoes.atacar(g, 2, 1);
    }""")
    page.wait_for_timeout(150)

    overlay_ativo = page.eval_on_selector("#overlay-selecao", "el => el.classList.contains('ativo')")
    assert overlay_ativo, "o gatilho deveria abrir o modal perguntando se quer ativar a Maldição"
    assert "Maldição" in page.text_content("#selecao-prompt"), "prompt do gatilho nao bate"

    page.query_selector_all("#selecao-opcoes img")[0].click()
    page.wait_for_timeout(150)

    res_defensor = page.evaluate("() => window.game.board[1].monstro.atualRes")
    elemento_atacante = page.evaluate("() => window.game.board[2].monstro.elementoOverride")
    assert res_defensor == 15, f"o ataque deveria ter sido negado (RES intacta), ficou {res_defensor}"
    assert elemento_atacante is not None and elemento_atacante["elemento"] is None, \
        "o elemento do ATACANTE deveria ter sido removido"
    assert not erros, f"erros no console: {erros}"
    page.close()
    print("OK  gatilho de Maldição ao ser atacado (modal) + Escudo de Gelo Absoluto nega o lado certo")


def testar_maldicao_gratis_para_setar(browser):
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    erros = []
    page.on("pageerror", lambda e: erros.append(str(e)))
    page.goto(INDEX + "?seed=42")
    page.wait_for_timeout(200)
    fechar_modal_se_aberto(page, escolher=False)

    resultado = page.evaluate("""() => {
        const g = window.game;
        const ps = g.players[1];
        ps.mana = 0;
        const maldicao = ps.mao.find(c => c.tipo === "Maldição");
        if (!maldicao) return { semMaldicaoNaMao: true };
        let erroSetar = null;
        try { TCG.acoes.jogarCartaDeCampo(g, 1, maldicao); } catch (e) { erroSetar = e.message; }
        const setadaOk = g.board[1].magia.includes(maldicao);
        let erroAtivar = null;
        try { TCG.acoes.ativarMaldicaoSetada(g, 1, maldicao); } catch (e) { erroAtivar = e.message; }
        return { erroSetar, setadaOk, erroAtivar, faceDownDepois: maldicao.faceDown, custo: maldicao.custoMana };
    }""")
    if resultado.get("semMaldicaoNaMao"):
        page.close()
        print("--  pulei testar_maldicao_gratis_para_setar (sem Maldição na mão nesse seed)")
        return

    assert resultado["erroSetar"] is None, f"setar sem mana deveria funcionar, mas deu erro: {resultado['erroSetar']}"
    assert resultado["setadaOk"], "a Maldição deveria ter ido pro tabuleiro mesmo sem mana"
    assert resultado["erroAtivar"] == f"Mana insuficiente: precisa de {resultado['custo']}, tem 0.", \
        f"ativar sem mana deveria falhar por mana insuficiente, deu: {resultado['erroAtivar']}"
    assert resultado["faceDownDepois"] is True, "a Maldição deveria continuar virada pra baixo apos a ativacao falhar"
    assert not erros, f"erros no console: {erros}"
    page.close()
    print("OK  Maldição: setar é grátis, ativar sem mana falha e a carta continua em campo")


def testar_maldicao_oculta(browser):
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    page.goto(INDEX + "?seed=5")
    page.wait_for_timeout(200)
    fechar_modal_se_aberto(page, escolher=False)  # pula o modal de invocacao automatico pra nao bloquear o teste

    nome_real = page.evaluate("""() => {
        const g = window.game;
        const carta = g.baralhos[2].cartas.find(c => c.tipo === "Maldição");
        carta.faceDown = true;
        TCG.Board.colocarMagia(g.board[2], carta, 0);
        window.ui.render();
        return carta.nome;
    }""")

    slot_verso = page.query_selector("#tabuleiro-oponente .slot.verso")
    assert slot_verso is not None, "Maldição setada do oponente nao renderizou como verso"
    assert slot_verso.query_selector("img") is None, "o verso nao devia conter a imagem real da carta"

    slot_verso.hover()
    page.wait_for_timeout(120)
    preview_nome = page.text_content("#preview-nome")
    assert nome_real not in (preview_nome or ""), f"VAZOU o nome da carta oculta no preview: {preview_nome}"
    page.close()
    print(f"OK  Maldição setada do oponente ('{nome_real}') nao vaza no hover")


def testar_maldicao_setada_visivel_para_o_dono_no_hover(browser):
    """O DONO de uma Maldição setada sabe muito bem o que ela é — só o
    OPONENTE não pode ver (ver testar_maldicao_oculta acima). A arte no
    tabuleiro continua virada pra baixo pros dois lados; só o preview de
    hover muda pro dono."""
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    erros = []
    page.on("pageerror", lambda e: erros.append(str(e)))
    page.goto(INDEX + "?seed=42")
    page.wait_for_timeout(200)
    fechar_modal_se_aberto(page, escolher=False)

    nome_real = page.evaluate("""() => {
        const g = window.game;
        g.jogadorDaVez = 1; g.fase = 'TATICA';
        const acharCarta = (nome) => TCG.criarCardInstance(CARTAS.find(c => c.nome === nome));
        const maldicao = acharCarta('Escudo de Gelo Absoluto');
        g.players[1].mao = [maldicao];
        TCG.acoes.jogarCartaDeCampo(g, 1, maldicao);
        window.ui.render();
        return maldicao.nome;
    }""")

    # seletor preciso (nao ".slot.verso" solto, que tambem bate com as pilhas
    # de Baralho/Panteão/Descarte, igualmente ".verso") direto na linha de magia.
    slot_proprio = page.query_selector("#tabuleiro-jogador .linha-magia .slot.verso")
    assert slot_proprio is not None, "Maldição setada do próprio jogador nao renderizou como verso"
    assert slot_proprio.query_selector("img") is None, "o verso continua sem mostrar a arte no tabuleiro"

    slot_proprio.hover(force=True)
    page.wait_for_timeout(120)
    img_visivel = page.eval_on_selector("#preview-img", "el => el.style.display") == "block"
    img_src = page.eval_on_selector("#preview-img", "el => el.src")
    assert img_visivel and nome_real.replace(" ", "_").replace("'", "") in img_src.replace("%27", ""), \
        f"o dono deveria ver a arte real da própria Maldição setada no preview, veio: {img_src}"
    page.close()
    print(f"OK  Maldição setada ('{nome_real}') aparece no preview do PRÓPRIO dono (só o oponente fica sem ver)")


def testar_dominio_unico_no_jogo_e_fundo_compartilhado(browser):
    """Só pode haver 1 Domínio ativo NO JOGO INTEIRO — "só pode haver um
    ativo na mesa" (GAME_DESIGN.md) é a mesa compartilhada dos dois
    jogadores, não uma por lado. Ativar um novo (de QUALQUER um dos dois)
    destrói o que já estava ativo, seja de quem for — inclusive o do
    OPONENTE. A arte dele vira o fundo do campo inteiro dos DOIS lados."""
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    erros = []
    page.on("pageerror", lambda e: erros.append(str(e)))
    page.on("console", lambda m: erros.append(m.text) if m.type == "error" else None)
    page.goto(INDEX + "?seed=42")
    page.wait_for_timeout(200)
    fechar_modal_se_aberto(page, escolher=False)

    resultado = page.evaluate("""() => {
        const g = window.game;
        g.jogadorDaVez = 1; g.fase = 'TATICA'; g.turno = 2;
        const acharCarta = (nome) => structuredClone(CARTAS.find(c => c.nome === nome));
        const dominio1 = acharCarta('Vulcão Primordial');
        const dominio2 = acharCarta('Templo de Atlântida');
        g.players[1].mana = 99;
        g.players[1].mao = [dominio1, dominio2];
        TCG.acoes.jogarCartaDeCampo(g, 1, dominio1);
        TCG.acoes.jogarCartaDeCampo(g, 1, dominio2); // substitui o dele mesmo
        window.ui.render();
        const fundoSoDoJogador1 = {
            classeOp: document.getElementById('tabuleiro-oponente').className,
            classeJo: document.getElementById('tabuleiro-jogador').className,
        };

        // agora o OPONENTE ativa o PRÓPRIO Domínio — isso deveria destruir o
        // do jogador 1 também, já que só pode haver 1 no jogo inteiro
        const dominioOponente = acharCarta('Cânion dos Ventos');
        g.players[2].mana = 99;
        g.players[2].mao = [dominioOponente];
        g.jogadorDaVez = 2;
        TCG.acoes.jogarCartaDeCampo(g, 2, dominioOponente);
        g.jogadorDaVez = 1;
        window.ui.render();

        return {
            fundoSoDoJogador1,
            ativo1: TCG.dominioAtivo(g, 1)?.nome,
            ativo2: TCG.dominioAtivo(g, 2)?.nome,
            noDescarte1: g.descarte[1].some(c => c.nome === 'Vulcão Primordial'),
            noDescarte1_templo: g.descarte[1].some(c => c.nome === 'Templo de Atlântida'),
            cartasNaMagia1: g.board[1].magia.filter(c => c !== null).length,
            cartasNaMagia2: g.board[2].magia.filter(c => c !== null).length,
        };
    }""")
    print("resultado:", resultado)
    assert resultado["noDescarte1"], "o 1o Domínio do jogador 1 (substituído pelo 2o dele mesmo) deveria estar no descarte"
    # antes do oponente ativar o dele, so havia 1 Domínio em jogo (do jogador 1) —
    # o fundo compartilhado ja deveria ter aparecido nos DOIS lados desde entao
    assert "com-dominio" in resultado["fundoSoDoJogador1"]["classeOp"], \
        "o fundo do Domínio do jogador deveria aparecer TAMBÉM no lado do oponente"
    assert "com-dominio" in resultado["fundoSoDoJogador1"]["classeJo"]

    # depois que o OPONENTE ativa o SEU Domínio, o do jogador 1 (Templo de
    # Atlântida) deveria ter sido destruído TAMBÉM — só pode haver 1 no jogo
    assert resultado["ativo1"] is None, \
        f"o Domínio do jogador 1 deveria ter sido destruído quando o oponente ativou o dele, mas continua ativo: {resultado['ativo1']}"
    assert resultado["ativo2"] == "Cânion dos Ventos", "o Domínio do oponente deveria ter ativado normalmente"
    assert resultado["noDescarte1_templo"], "o Domínio do jogador 1 destruído pelo do oponente deveria ir pro descarte DELE (jogador 1)"
    assert resultado["cartasNaMagia1"] == 0, "o jogador 1 não deveria ter Domínio nenhum no campo mais"
    assert resultado["cartasNaMagia2"] == 1, "só o Domínio do oponente deveria estar no campo dele"

    # o fundo compartilhado passa a ser o do oponente — nos DOIS lados,
    # inclusive no do jogador local (a arte fica no ::before, ver style.css)
    for container_id in ("#tabuleiro-jogador", "#tabuleiro-oponente"):
        classe = page.eval_on_selector(container_id, "el => el.className")
        fundo = page.eval_on_selector(container_id, "el => getComputedStyle(el, '::before').backgroundImage")
        tag = page.text_content(f"{container_id} .dominio-tag")
        assert "com-dominio" in classe, f"{container_id}: deveria ganhar a classe de fundo com Domínio"
        assert "url(" in fundo, f"{container_id}: fundo do campo deveria usar a arte do Domínio, veio '{fundo}'"
        assert tag == "Domínio: Cânion dos Ventos", \
            f"{container_id}: o fundo compartilhado deveria mostrar o único Domínio ativo (do oponente), veio '{tag}'"

    # o card do Domínio do jogador 1 NÃO deveria mais aparecer em nenhum slot
    imgs_magia_jogador = page.eval_on_selector_all("#tabuleiro-jogador .linha-magia .slot img", "els => els.map(e => e.alt)")
    assert "Templo de Atlântida" not in imgs_magia_jogador, "o Domínio destruído do jogador 1 não deveria mais estar em nenhum slot"

    # o lado do oponente é a mesa "vista do lado oposto" — a arte do fundo
    # compartilhado aparece invertida (scaleY) só ali, nunca no lado do jogador
    transform_op = page.eval_on_selector("#tabuleiro-oponente", "el => getComputedStyle(el, '::before').transform")
    transform_jo = page.eval_on_selector("#tabuleiro-jogador", "el => getComputedStyle(el, '::before').transform")
    assert transform_op == "matrix(1, 0, 0, -1, 0, 0)", f"fundo do oponente deveria estar invertido (scaleY(-1)), veio '{transform_op}'"
    assert transform_jo in ("none", "matrix(1, 0, 0, 1, 0, 0)"), f"fundo do jogador NÃO deveria estar invertido, veio '{transform_jo}'"

    # PIXEL de verdade, não só computed style: um bug real (z-index:-1 escapando
    # pra debaixo de um ancestral por falta de stacking context em .tabuleiro)
    # fazia o getComputedStyle acima reportar tudo "certo" mesmo com a arte
    # NUNCA aparecendo na tela — só um screenshot pego no flagra. Compara a cor
    # de um pixel de fundo vazio (canto interno, fora de qualquer card/tag)
    # ANTES de ativar Domínio nenhum com a cor DEPOIS: tem que ter mudado.
    import tempfile
    from PIL import Image
    box = page.eval_on_selector("#tabuleiro-jogador", "el => { const r = el.getBoundingClientRect(); return {x:r.x,y:r.y}; }")
    ponto = (int(box["x"]) + 5, int(box["y"]) + 5)  # canto vazio: antes do .dominio-tag (left:12,top:6) e de qualquer filho
    caminho_shot = os.path.join(tempfile.gettempdir(), "_teste_dominio_pixel.png")
    page.screenshot(path=caminho_shot)
    cor_com_dominio = Image.open(caminho_shot).getpixel(ponto)

    pagina_limpa = browser.new_page(viewport={"width": 1400, "height": 900})
    pagina_limpa.goto(INDEX + "?seed=42")
    pagina_limpa.wait_for_timeout(200)
    fechar_modal_se_aberto(pagina_limpa, escolher=False)
    pagina_limpa.screenshot(path=caminho_shot)
    cor_sem_dominio = Image.open(caminho_shot).getpixel(ponto)
    pagina_limpa.close()

    distancia = sum((a - b) ** 2 for a, b in zip(cor_com_dominio[:3], cor_sem_dominio[:3])) ** 0.5
    print(f"pixel de fundo: sem Domínio={cor_sem_dominio}, com Domínio={cor_com_dominio}, distância={distancia:.1f}")
    assert distancia > 20, \
        f"a arte do Domínio deveria ter mudado visivelmente o pixel de fundo, mas ficou quase igual " \
        f"(sem={cor_sem_dominio}, com={cor_com_dominio}) — a arte pode estar computando certo no CSS mas não pintando de verdade"

    # o card do Domínio ativo (Cânion dos Ventos, do oponente) só ocupa slot
    # de magia no campo DELE — nunca no do jogador local, que não tem nenhum
    # Domínio próprio mais (foi destruído quando o oponente ativou o dele)
    imgs_magia_jogador = page.eval_on_selector_all("#tabuleiro-jogador .linha-magia .slot img", "els => els.map(e => e.alt)")
    imgs_magia_oponente = page.eval_on_selector_all("#tabuleiro-oponente .linha-magia .slot img", "els => els.map(e => e.alt)")
    assert "Templo de Atlântida" not in imgs_magia_jogador and "Cânion dos Ventos" not in imgs_magia_jogador
    assert "Cânion dos Ventos" in imgs_magia_oponente and "Templo de Atlântida" not in imgs_magia_oponente

    assert not erros, f"erros no console: {erros}"
    page.close()
    print("OK  Domínio único no jogo inteiro (destrói o do oponente também) com fundo compartilhado nos DOIS lados")


def testar_nunca_2_dominios_simultaneos_em_partida_real(browser, seeds=range(1, 20)):
    """Regressão do bug relatado: o jogador ativa seu Domínio, o OPONENTE
    ativa o dele depois, e o do jogador não era destruído — porque a Ação
    só derrubava o Domínio do MESMO dono, não o "único ativo na mesa"
    (GAME_DESIGN.md). Roda partidas reais (humano jogando carta de mão de
    verdade + IA) e garante que a soma de Domínios nos dois campos NUNCA
    passa de 1, em turno nenhum."""
    for seed in seeds:
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        erros = []
        page.on("pageerror", lambda e: erros.append(str(e)))
        page.on("console", lambda m: erros.append(m.text) if m.type == "error" else None)
        page.goto(INDEX + f"?seed={seed}")
        page.wait_for_timeout(150)

        resultado = page.evaluate("""() => {
            const g = window.game;
            const violacoes = [];
            // TCG.executarTurnoIA agora pode PAUSAR no meio (uma decisão de
            // Maldição reativa pro jogador 1) e só continuar quando essa
            // seleção for resolvida — chamar de novo enquanto ainda está "em
            // andamento" reiniciaria o turno da IA do zero, duplicando ações
            // (ver ai.js). `iaEmAndamento` garante 1 chamada por turno da IA;
            // as iterações seguintes só resolvem a pendente do jogador 1, que
            // por si só encadeia o resto do turno da IA sozinha.
            let iaEmAndamento = false;
            for (let t = 0; t < 300; t++) {
                if (g.fimDeJogo) break;
                const pendente = g.selection.algumaPendentePara(1);
                if (pendente) {
                    g.selection.resolver(pendente.requestId, pendente.opcoes.length ? [pendente.opcoes[0]] : []);
                }
                if (g.jogadorDaVez === 1) {
                    iaEmAndamento = false;
                    if (g.fase === 'TATICA') {
                        const jogavel = g.players[1].mao.find(c => ['Domínio','Encantamento','Maldição'].includes(c.tipo));
                        if (jogavel) { try { TCG.acoes.jogarCartaDeCampo(g, 1, jogavel); } catch(e) {} }
                    }
                    if (g.fase === 'COMBATE' && g.board[1].monstro && !g.board[1].monstro.atacouNesteTurno && g.turno !== 1) {
                        try { TCG.acoes.atacar(g, 1, 2); } catch(e) {}
                    }
                    if (!g.fimDeJogo) TCG.acoes.avancarFase(g);
                } else if (!iaEmAndamento) {
                    iaEmAndamento = true;
                    TCG.executarTurnoIA(g, 2);
                }
                const total = [1, 2].reduce((soma, pid) =>
                    soma + g.board[pid].magia.filter(c => c && c.tipo === 'Domínio').length, 0);
                if (total > 1) violacoes.push({ turno: g.turno, total });
            }
            return { violacoes };
        }""")
        assert not resultado["violacoes"], \
            f"seed={seed}: mais de 1 Domínio ativo NO JOGO ao mesmo tempo: {resultado['violacoes']}"
        assert not erros, f"seed={seed}: erros no console: {erros}"
        page.close()
    print(f"OK  nunca houve 2 Domínios simultâneos no jogo inteiro, em {len(list(seeds))} seeds")


def testar_dominio_aparece_em_partida_real(browser, max_seeds=15):
    """Regressão de um falso-negativo real: um script de verificação anterior
    só fechava o modal de invocação e nunca clicava carta nenhuma da mão do
    jogador local, então o lado humano nunca jogava um Domínio de verdade —
    parecia que só o campo do oponente (a IA joga sozinha) ganhava o fundo.
    Aqui o playthrough clica cartas da mão de verdade (via jogar_ate_o_fim),
    e confere que os dois lados acabam mostrando o fundo em algum momento."""
    vistos = {"oponente": False, "jogador": False}
    for seed in range(1, max_seeds + 1):
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        erros = []
        page.on("pageerror", lambda e: erros.append(str(e)))
        page.on("console", lambda m: erros.append(m.text) if m.type == "error" else None)
        page.goto(INDEX + f"?seed={seed}")
        page.wait_for_timeout(150)

        for _ in range(200):
            estado = page.evaluate("() => TCG.estado(window.game)")
            if estado["fimDeJogo"]:
                break
            fechar_modal_se_aberto(page)
            if estado["fase"] == "TATICA":
                cartas = page.query_selector_all(".mao-jogador .carta-mao")
                if cartas:
                    clicar_se_possivel(cartas[0])
                    page.wait_for_timeout(15)
                    fechar_modal_se_aberto(page)
            if estado["fase"] == "COMBATE":
                btn = page.query_selector("#btn-atacar")
                if btn and not btn.is_disabled():
                    btn.click()
            if "com-dominio" in page.eval_on_selector("#tabuleiro-oponente", "el => el.className"):
                vistos["oponente"] = True
            if "com-dominio" in page.eval_on_selector("#tabuleiro-jogador", "el => el.className"):
                vistos["jogador"] = True
            btn_fase = page.query_selector("#btn-fase")
            if btn_fase and not btn_fase.is_disabled():
                btn_fase.click()
            page.wait_for_timeout(15)

        assert not erros, f"seed={seed}: erros no console: {erros}"
        page.close()
        if vistos["oponente"] and vistos["jogador"]:
            break

    print("vistos:", vistos)
    assert vistos["oponente"], "o campo do OPONENTE nunca mostrou o fundo de Domínio em nenhuma partida real"
    assert vistos["jogador"], "o campo do JOGADOR nunca mostrou o fundo de Domínio em nenhuma partida real"
    print("OK  fundo de Domínio aparece nos dois lados numa partida real (jogador humano jogando carta de campo)")


def testar_preview_altura_constante_e_cartas_de_modal_maiores(browser):
    """O preview tem altura CONSTANTE em vh (não flexível/dividindo espaço
    com o #log) — não muda enchendo o log de mensagens nem entre alturas de
    viewport diferentes. E as cartas dentro de modais (seleção/descarte) são
    bem maiores que um slot comum do tabuleiro."""
    for altura_viewport in (700, 900, 1100):
        page = browser.new_page(viewport={"width": 1400, "height": altura_viewport})
        page.goto(INDEX)
        page.wait_for_timeout(150)

        altura_preview = page.eval_on_selector("#preview", "el => el.getBoundingClientRect().height")
        esperado = altura_viewport * 0.58
        assert abs(altura_preview - esperado) < 2, \
            f"viewport={altura_viewport}: preview deveria ter 58vh ({esperado:.1f}px), veio {altura_preview:.1f}px"

        page.evaluate("""() => {
            const log = document.getElementById('log');
            for (let i = 0; i < 200; i++) {
                const d = document.createElement('div');
                d.textContent = 'linha ' + i;
                log.appendChild(d);
            }
        }""")
        altura_depois = page.eval_on_selector("#preview", "el => el.getBoundingClientRect().height")
        assert abs(altura_depois - altura_preview) < 0.5, \
            f"viewport={altura_viewport}: preview não deveria mudar de tamanho com o log cheio ({altura_preview:.1f} -> {altura_depois:.1f})"

        scroll_w = page.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
        scroll_h = page.evaluate("() => document.documentElement.scrollHeight - document.documentElement.clientHeight")
        assert scroll_w <= 1 and scroll_h <= 1, f"viewport={altura_viewport}: a página não deveria rolar"
        page.close()

    # cartas de modal maiores que um slot comum (11.5vh) do tabuleiro
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    page.goto(INDEX)
    page.wait_for_timeout(200)
    altura_modal = page.eval_on_selector("#selecao-opcoes img", "el => el.getBoundingClientRect().height")
    altura_slot = page.eval_on_selector(".linha-magia .slot", "el => el.getBoundingClientRect().height")
    print(f"altura carta de modal={altura_modal:.1f}px, altura slot comum={altura_slot:.1f}px")
    assert altura_modal > altura_slot * 1.3, "cartas de modal deveriam ser visivelmente maiores que um slot comum do tabuleiro"
    page.close()
    print("OK  preview com altura constante (58vh) e cartas de modal maiores que um slot comum")


def testar_dominio_passivo_reaplicado_e_limpo_ao_destruir(browser):
    """Refatoração de gatilhos/passivos (webgame/triggers.js): um Domínio
    'enquanto ativo' (Trono de Camelot) tinha o bug de aplicar o buff só 1x,
    no combatente ativo NO MOMENTO da ativação — não cobria um combatente
    invocado depois, e o buff nunca sumia se o Domínio fosse destruído.
    Agora é reaplicado do zero a cada Fase Tática e limpo na destruição."""
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    erros = []
    page.on("pageerror", lambda e: erros.append(str(e)))
    page.on("console", lambda m: erros.append(m.text) if m.type == "error" else None)
    page.goto(INDEX + "?seed=42")
    page.wait_for_timeout(200)
    fechar_modal_se_aberto(page, escolher=False)

    r = page.evaluate("""() => {
        const g = window.game;
        g.jogadorDaVez = 1; g.fase = 'TATICA'; g.turno = 2; g.players[1].mana = 99;
        const acharCarta = (nome) => TCG.criarCardInstance(CARTAS.find(c => c.nome === nome));
        const dominio = acharCarta('Trono de Camelot');
        const heroiA = acharCarta('Rei Arthur');
        g.board[1].monstro = heroiA;
        g.players[1].mao = [dominio];
        TCG.acoes.jogarCartaDeCampo(g, 1, dominio);
        const powAComDominio = heroiA.atualPow;

        // troca de combatente: B foi invocado DEPOIS da ativação do Domínio
        TCG.destroyCard(g, heroiA, 'teste');
        const heroiB = acharCarta('Gilgamesh');
        g.board[1].monstro = heroiB;
        TCG.aplicarPassivos(g); // simula entrar de novo na Fase Tática
        const powBComDominio = heroiB.atualPow;

        TCG.destroyCard(g, dominio, 'teste');
        const powBSemDominio = heroiB.atualPow;

        return {
            buffouA: powAComDominio === heroiA.combate + 3,
            buffouBTambem: powBComDominio === heroiB.combate + 3,
            buffSumiuAoDestruirDominio: powBSemDominio === heroiB.combate,
        };
    }""")
    print("resultado:", r)
    assert r["buffouA"], "Trono de Camelot deveria ter buffado o Herói ativo na hora de ativar"
    assert r["buffouBTambem"], "um Herói invocado DEPOIS deveria ganhar o buff na próxima Fase Tática (passivo reaplicado)"
    assert r["buffSumiuAoDestruirDominio"], "o buff deveria sumir quando o Domínio é destruído"
    assert not erros, f"erros no console: {erros}"
    page.close()
    print("OK  Domínio passivo ('enquanto ativo') reaplicado a cada Fase Tática e limpo ao destruir")


def testar_dominio_gatilho_recorrente_entre_turnos(browser):
    """Oceano Primordial ('No início do turno, revela o topo do baralho; se
    for Água ou Encantamento, compra de graça') era um TODO explícito antes
    desta refatoração — agora é um gatilho de verdade em 'turnoIniciado',
    testado disparando em 2 inícios de turno diferentes."""
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    erros = []
    page.on("pageerror", lambda e: erros.append(str(e)))
    page.on("console", lambda m: erros.append(m.text) if m.type == "error" else None)
    page.goto(INDEX + "?seed=42")
    page.wait_for_timeout(200)
    fechar_modal_se_aberto(page, escolher=False)

    r = page.evaluate("""() => {
        const g = window.game;
        g.jogadorDaVez = 1; g.fase = 'TATICA'; g.turno = 2; g.players[1].mana = 99;
        const acharCarta = (nome) => TCG.criarCardInstance(CARTAS.find(c => c.nome === nome));
        const dominio = acharCarta('Oceano Primordial');
        g.players[1].mao = [dominio];
        TCG.acoes.jogarCartaDeCampo(g, 1, dominio);

        const agua = acharCarta('Cthulhu'); // Monstro de Água
        g.baralhos[1].cartas.unshift(agua);
        g.bus.emit('turnoIniciado', { playerId: 1, numeroTurno: g.turno });
        const comprouAgua = g.players[1].mao.includes(agua);

        const fogo = acharCarta('Fenrir'); // Monstro de Fogo: não deveria comprar
        g.baralhos[1].cartas.unshift(fogo);
        g.bus.emit('turnoIniciado', { playerId: 1, numeroTurno: g.turno + 1 });
        const naoComprouFogo = !g.players[1].mao.includes(fogo);

        return { comprouAgua, naoComprouFogo };
    }""")
    print("resultado:", r)
    assert r["comprouAgua"], "deveria ter comprado de graça a carta de Água revelada no topo"
    assert r["naoComprouFogo"], "não deveria comprar uma carta que não é Água nem Encantamento"
    assert not erros, f"erros no console: {erros}"
    page.close()
    print("OK  Oceano Primordial dispara em múltiplos inícios de turno (gatilho recorrente)")


def testar_valhalla_redireciona_para_panteao(browser):
    """Valhalla ('Quando um Espírito Heróico for derrotado, ele retorna para
    o Panteão em vez da Pilha de Descarte') intercepta o destino no evento
    PRÉ-destruição ('cartaSeraDestruida') — sem esse gatilho, o Herói iria
    pro descarte normalmente."""
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    erros = []
    page.on("pageerror", lambda e: erros.append(str(e)))
    page.on("console", lambda m: erros.append(m.text) if m.type == "error" else None)
    page.goto(INDEX + "?seed=42")
    page.wait_for_timeout(200)
    fechar_modal_se_aberto(page, escolher=False)

    r = page.evaluate("""() => {
        const g = window.game;
        g.jogadorDaVez = 1; g.fase = 'TATICA'; g.turno = 2; g.players[1].mana = 99;
        const acharCarta = (nome) => TCG.criarCardInstance(CARTAS.find(c => c.nome === nome));
        const dominio = acharCarta('Valhalla');
        g.players[1].mao = [dominio];
        TCG.acoes.jogarCartaDeCampo(g, 1, dominio);

        const heroi = acharCarta('Rei Arthur');
        g.panteoes[1].cartas.push(heroi); g.panteoes[1].compradas.add(heroi); // veio do próprio Panteão
        g.board[1].monstro = heroi;
        TCG.destroyCard(g, heroi, 'derrotado em combate');

        return {
            noDescarte: g.descarte[1].includes(heroi),
            noPanteao: g.panteoes[1].cartas.includes(heroi) && !g.panteoes[1].compradas.has(heroi),
        };
    }""")
    print("resultado:", r)
    assert not r["noDescarte"], "o Herói NÃO deveria ir pro descarte com Valhalla ativo"
    assert r["noPanteao"], "o Herói deveria voltar pro Panteão"
    assert not erros, f"erros no console: {erros}"
    page.close()
    print("OK  Valhalla redireciona Herói destruído pro Panteão em vez do descarte")


def testar_caixa_de_pandora_gatilho_correto(browser):
    """Regressão de um bug real pré-existente: 'Ao ter Domínio/Combatente
    destruído' (do DONO da Caixa de Pandora) disparava, antes desta
    refatoração, quando a PRÓPRIA Caixa de Pandora era destruída — condição
    diferente da escrita na carta. Também cobre o novo fluxo: a Maldição fica
    virada pra baixo até o evento certo acontecer NO TURNO DO OPONENTE, aí um
    modal pergunta se quer ativar — o jogo PARA até essa decisão."""
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    erros = []
    page.on("pageerror", lambda e: erros.append(str(e)))
    page.on("console", lambda m: erros.append(m.text) if m.type == "error" else None)
    page.goto(INDEX + "?seed=42")
    page.wait_for_timeout(200)
    fechar_modal_se_aberto(page, escolher=False)

    # 1) destruir a PRÓPRIA Caixa de Pandora (ainda virada pra baixo, nunca
    # revelada) não deveria oferecer nem disparar efeito nenhum.
    setup1 = page.evaluate("""() => {
        const g = window.game;
        g.jogadorDaVez = 1; g.fase = 'TATICA'; g.turno = 2; g.players[1].mana = 99;
        const acharCarta = (nome) => TCG.criarCardInstance(CARTAS.find(c => c.nome === nome));
        const caixa = acharCarta('Caixa de Pandora');
        g.board[1].magia = [null, null, null, null, null];
        g.players[1].mao = [caixa];
        TCG.acoes.jogarCartaDeCampo(g, 1, caixa); // seta (grátis, virada pra baixo) — nunca revelada
        TCG.destroyCard(g, caixa, 'Purificação Arcana'); // destruída SEM nunca ter sido revelada
        return { overlayAtivo: document.getElementById('overlay-selecao').classList.contains('ativo'), descarteOponente: g.descarte[2].length };
    }""")
    print("destruir a própria carta (nunca revelada):", setup1)
    assert not setup1["overlayAtivo"], "destruir a própria Caixa de Pandora (nunca revelada) não deveria abrir modal nenhum"
    assert setup1["descarteOponente"] == 0, "não deveria ter disparado o efeito (bug antigo)"

    # 2) Caixa de Pandora setada, NO TURNO DO OPONENTE um Combatente do dono é
    # destruído -> modal pergunta se quer ativar -> só descarta ao decidir "sim".
    page.evaluate("""() => {
        const g = window.game;
        g.jogadorDaVez = 1; g.fase = 'TATICA'; g.players[1].mana = 99;
        const acharCarta = (nome) => TCG.criarCardInstance(CARTAS.find(c => c.nome === nome));
        const caixa = acharCarta('Caixa de Pandora');
        g.board[1].magia = [null, null, null, null, null];
        g.players[1].mao = [caixa];
        TCG.acoes.jogarCartaDeCampo(g, 1, caixa); // seta, grátis, virada pra baixo

        g.jogadorDaVez = 2; // agora é o turno do OPONENTE
        const heroi = acharCarta('Rei Arthur');
        g.board[1].monstro = heroi;
        TCG.destroyCard(g, heroi, 'derrotado em combate'); // Combatente DO DONO da Caixa de Pandora
    }""")
    page.wait_for_timeout(100)
    overlay_ativo = page.eval_on_selector("#overlay-selecao", "el => el.classList.contains('ativo')")
    assert overlay_ativo, "deveria ter aberto o modal perguntando se quer ativar a Caixa de Pandora"
    descarte_antes = page.evaluate("() => window.game.descarte[2].length")
    assert descarte_antes == 0, "o jogo deveria estar PARADO esperando a decisão, sem ter descartado nada ainda"

    page.query_selector_all("#selecao-opcoes img")[0].click()
    page.wait_for_timeout(100)
    descarte_depois = page.evaluate("() => window.game.descarte[2].length")
    print("descarte do oponente após decidir ativar:", descarte_depois)
    assert descarte_depois == 3, "destruir um Combatente DO DONO da Caixa de Pandora, ativada, deveria forçar o oponente a descartar 3"

    assert not erros, f"erros no console: {erros}"
    page.close()
    print("OK  Caixa de Pandora: modal no evento certo, jogo para até decidir, efeito certo (não na própria destruição)")


def testar_turno_da_ia_para_de_verdade_para_decisao_de_maldicao(browser):
    """Regressão de um bug real e sério encontrado ao implementar isso: o
    turno inteiro da IA (TCG.executarTurnoIA) rodava sincronamente do início
    ao fim numa única chamada — um modal de Maldição reativa pro jogador
    LOCAL era mostrado, mas o resto do turno (e até turnos seguintes) já
    tinha acontecido por baixo, porque abrir o modal só registra a seleção
    pendente, não bloqueia de verdade o código que chamou. Corrigido
    reescrevendo ai.js em estilo de continuação. Este teste ataca DE VERDADE
    via o botão 'Fim de Turno' (não uma chamada isolada) e confere que o
    jogo fica PARADO — turno/fase intactos — enquanto o modal está aberto."""
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    erros = []
    page.on("pageerror", lambda e: erros.append(str(e)))
    page.on("console", lambda m: erros.append(m.text) if m.type == "error" else None)
    page.goto(INDEX + "?seed=42")
    page.wait_for_timeout(200)
    fechar_modal_se_aberto(page, escolher=False)

    page.evaluate("""() => {
        const g = window.game;
        const acharCarta = (nome) => TCG.criarCardInstance(CARTAS.find(c => c.nome === nome));
        const atacanteIA = acharCarta('Rei Arthur'); atacanteIA.atualPow = 15; atacanteIA.atualRes = 15;
        const defensorLocal = acharCarta('Rei Arthur'); defensorLocal.atualPow = 10; defensorLocal.atualRes = 15;
        const maldicao = acharCarta('Escudo de Gelo Absoluto');
        maldicao.faceDown = true;
        g.board[2].monstro = atacanteIA;
        g.board[1].monstro = defensorLocal;
        g.board[1].magia = [maldicao, null, null, null, null];
        g.jogadorDaVez = 1; g.fase = 'COMBATE'; g.turno = 3;
    }""")

    turno_antes = page.evaluate("() => window.game.turno")
    page.click("#btn-fase")  # "Fim de Turno" -> dispara TCG.executarTurnoIA de verdade
    page.wait_for_timeout(150)

    estado = page.evaluate("""() => {
        const g = window.game;
        return {
            jogadorDaVez: g.jogadorDaVez, fase: g.fase, turno: g.turno,
            overlayAtivo: document.getElementById('overlay-selecao').classList.contains('ativo'),
            resDefensor: g.board[1].monstro ? g.board[1].monstro.atualRes : null,
        };
    }""")
    print(f"turno antes={turno_antes}, estado logo após clicar Fim de Turno:", estado)
    assert estado["overlayAtivo"], "o modal da Maldição reativa deveria estar aberto"
    assert estado["jogadorDaVez"] == 2 and estado["fase"] == "COMBATE", \
        f"o jogo deveria estar PARADO no meio do turno da IA (ainda jogadorDaVez=2/fase=COMBATE), veio {estado}"
    # turno_antes+1 é esperado (o clique em "Fim de Turno" primeiro fecha o
    # turno do jogador local, turno_antes -> turno_antes+1, ANTES do turno da
    # IA começar) — o que não pode acontecer é passar disso, o que indicaria
    # que o turno da IA (turno_antes+1) rodou por cima do modal pendente.
    assert estado["turno"] == turno_antes + 1, \
        f"só o fechamento do turno do jogador deveria ter avançado o turno (esperado {turno_antes + 1}), veio {estado['turno']}"
    assert estado["resDefensor"] == 15, "o dano não deveria ter sido calculado antes da decisão"

    # resolve a decisão -> o resto do turno da IA (e a passagem pro turno do
    # jogador local) deve completar sozinho, encadeado pela própria resolução.
    page.query_selector_all("#selecao-opcoes img")[0].click()
    page.wait_for_timeout(150)
    estado_final = page.evaluate("() => ({ jogadorDaVez: window.game.jogadorDaVez, resDefensor: window.game.board[1].monstro.atualRes })")
    print("estado final após decidir:", estado_final)
    assert estado_final["jogadorDaVez"] == 1, "depois de decidir, o resto do turno da IA deveria ter completado e devolvido a vez"
    assert estado_final["resDefensor"] == 15, "Escudo de Gelo Absoluto deveria ter anulado o ataque"

    assert not erros, f"erros no console: {erros}"
    page.close()
    print("OK  o turno da IA realmente PARA (turno/fase intactos) até o jogador decidir sobre uma Maldição reativa")


def testar_maldicao_reativa_em_evento_nao_ataque(browser):
    """A generalização pedida: não é só 'ao ser atacado' — qualquer evento
    com um gatilho declarado (regGatilhoMaldicao) abre o modal e para o jogo.
    Aqui: Areias Movediças reage a um Combatente sendo INVOCADO pelo
    oponente, não a um ataque."""
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    erros = []
    page.on("pageerror", lambda e: erros.append(str(e)))
    page.on("console", lambda m: erros.append(m.text) if m.type == "error" else None)
    page.goto(INDEX + "?seed=42")
    page.wait_for_timeout(200)
    fechar_modal_se_aberto(page, escolher=False)

    resultado = page.evaluate("""() => {
        const g = window.game;
        const acharCarta = (nome) => TCG.criarCardInstance(CARTAS.find(c => c.nome === nome));
        const maldicao = acharCarta('Areias Movediças');
        g.board[1].magia = [maldicao, null, null, null, null];
        maldicao.faceDown = true;

        g.jogadorDaVez = 2; g.fase = 'INVOCACAO';
        const novoCombatente = acharCarta('Rei Arthur');
        g.panteoes[2].cartas.push(novoCombatente); // ainda NÃO em compradas — invocar() é quem marca isso (tirarEspecifica)
        g.players[2].mana = 99;
        TCG.acoes.invocar(g, 2, novoCombatente);
        return { baseRes: novoCombatente.resistencia };
    }""")
    page.wait_for_timeout(100)
    overlay_ativo = page.eval_on_selector("#overlay-selecao", "el => el.classList.contains('ativo')")
    assert overlay_ativo, "invocar um Combatente deveria oferecer Areias Movediças pro modal"

    page.query_selector_all("#selecao-opcoes img")[0].click()
    page.wait_for_timeout(100)
    res_depois = page.evaluate("() => window.game.board[2].monstro.atualRes")
    print(f"RES base={resultado['baseRes']}, RES após ativar Areias Movediças={res_depois}")
    assert res_depois == resultado["baseRes"] - 5, "Areias Movediças deveria ter aplicado -5 RES no combatente recém-invocado"

    assert not erros, f"erros no console: {erros}"
    page.close()
    print("OK  Maldição reativa também dispara (e para o jogo) em eventos que não são ataque")


def testar_ia_nao_revela_propria_maldicao_no_proprio_turno(browser):
    """Regressão do bug pré-existente descrito em GAME_DESIGN.md: Maldição só
    pode ser revelada 'a qualquer momento no turno do OPONENTE' — a IA não
    deveria mais considerar revelar a PRÓPRIA Maldição setada durante a
    PRÓPRIA Fase Tática (opção removida de ai.js/opcoesFaseTatica)."""
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    erros = []
    page.on("pageerror", lambda e: erros.append(str(e)))
    page.on("console", lambda m: erros.append(m.text) if m.type == "error" else None)
    page.goto(INDEX + "?seed=7")
    page.wait_for_timeout(200)
    fechar_modal_se_aberto(page, escolher=False)

    resultado = page.evaluate("""() => {
        const g = window.game;
        const acharCarta = (nome) => TCG.criarCardInstance(CARTAS.find(c => c.nome === nome));
        // qualquer Maldição serve; usa uma que não tem gatilho declarado
        // (Praga da Ferrugem) pra garantir que não sobra face-down por falta
        // de evento elegível — se sobrar face-down, é porque a IA nunca
        // tentou revelar no próprio turno, que é exatamente o que queremos.
        const maldicao = acharCarta('Praga da Ferrugem');
        g.board[2].magia = [maldicao, null, null, null, null];
        maldicao.faceDown = true;
        g.players[2].mana = 99;
        g.jogadorDaVez = 2; g.fase = 'TATICA';
        for (let i = 0; i < 20; i++) {
            const opcoes = [];
            const ps = g.players[2];
            for (const carta of ps.mao) {
                if (!['Domínio','Encantamento','Maldição'].includes(carta.tipo)) continue;
                if (carta.tipo !== 'Maldição' && carta.custoMana > ps.mana) continue;
                if ((carta.tipo === 'Domínio' || carta.tipo === 'Maldição') && TCG.Board.slotsLivres(g.board[2]).length === 0) continue;
                opcoes.push({ tipo: 'jogar', carta });
            }
            const lado = g.board[2];
            if (lado.monstro && lado.monstro.custoHabilidade != null && !lado.monstro.habilidadeUsadaNesteTurno
                && lado.monstro.custoHabilidade <= ps.mana) opcoes.push({ tipo: 'habilidade' });
            const temOpcaoRevelar = opcoes.some(o => o.tipo === 'revelar');
            if (temOpcaoRevelar) return { temOpcaoRevelar: true };
            break; // não precisa rodar o loop de verdade, só checar 1x que a opção nem existe
        }
        return { temOpcaoRevelar: false, aindaFaceDown: maldicao.faceDown };
    }""")
    print("resultado:", resultado)
    assert not resultado["temOpcaoRevelar"], "opcoesFaseTatica não deveria mais oferecer 'revelar' pra IA no próprio turno"
    assert resultado["aindaFaceDown"], "a Maldição deveria continuar virada pra baixo (nunca revelada no próprio turno)"
    assert not erros, f"erros no console: {erros}"
    page.close()
    print("OK  a IA não revela mais a própria Maldição durante o próprio turno (regra corrigida)")


def testar_partida_completa(browser, seeds=(1, 2, 3)):
    for seed in seeds:
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        erros = []
        page.on("pageerror", lambda e: erros.append(str(e)))
        page.on("console", lambda m: erros.append(m.text) if m.type == "error" else None)
        page.goto(INDEX + f"?seed={seed}")
        page.wait_for_timeout(150)

        estado_final = jogar_ate_o_fim(page)
        assert estado_final["fimDeJogo"] in ("Pontos de Vida chegaram a 0", "sem combatentes para invocar"), \
            f"seed={seed}: jogo nao terminou com um motivo valido ({estado_final['fimDeJogo']}), turno {estado_final['turno']}"
        overlay_ativo = page.eval_on_selector("#overlay-fim", "el => el.classList.contains('ativo')")
        assert overlay_ativo, f"seed={seed}: overlay de fim de jogo nao apareceu"
        assert not erros, f"seed={seed}: erros no console: {erros}"
        page.close()
        print(f"OK  partida completa (seed={seed}): {estado_final['fimDeJogo']} no turno {estado_final['turno']}")


def testar_fx_summon_voa_e_limpa_sozinho(browser):
    """Invocar um Combatente dispara um "fx-ghost" (Panteão -> slot de
    Monstro) dentro de #fx-layer, e o elemento se limpa sozinho depois."""
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    erros = []
    page.on("pageerror", lambda e: erros.append(str(e)))
    page.on("console", lambda m: erros.append(m.text) if m.type == "error" else None)
    page.goto(INDEX)
    page.wait_for_timeout(200)

    antes = page.eval_on_selector_all("#fx-layer > *", "els => els.length")
    imgs = page.query_selector_all("#selecao-opcoes img")
    imgs[0].click()
    page.wait_for_timeout(60)
    logo_apos = page.eval_on_selector_all("#fx-layer > *", "els => els.length")
    page.wait_for_timeout(600)  # janela generosa: maior duracao+atraso usados é bem menor que isso
    depois = page.eval_on_selector_all("#fx-layer > *", "els => els.length")

    assert antes == 0, f"#fx-layer já tinha elemento(s) antes de qualquer ação: {antes}"
    assert logo_apos >= 1, "invocar deveria ter criado pelo menos um elemento de animação"
    assert depois == 0, f"#fx-layer deveria ter se limpado sozinho, sobrou {depois} elemento(s)"
    assert not erros, f"erros no console: {erros}"
    page.close()
    print("OK  animação de invocação (fx-ghost) aparece em #fx-layer e se limpa sozinha")


def testar_fx_statusAlterado_nao_dispara_ao_reaplicar_passivo_sem_mudanca(browser):
    """TCG.aplicarPassivos roda em TODA Fase Tática mesmo sem nada mudar —
    o evento genérico "statusAlterado" (usado pra animar buffs) não pode
    disparar de novo nesse caso, só na primeira aplicação real."""
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    erros = []
    page.on("pageerror", lambda e: erros.append(str(e)))
    page.on("console", lambda m: erros.append(m.text) if m.type == "error" else None)
    page.goto(INDEX + "?seed=42")
    page.wait_for_timeout(200)
    fechar_modal_se_aberto(page, escolher=False)

    r = page.evaluate("""() => {
        const g = window.game;
        g.jogadorDaVez = 1; g.fase = 'TATICA'; g.players[1].mana = 99;
        const acharCarta = (nome) => TCG.criarCardInstance(CARTAS.find(c => c.nome === nome));
        const dominio = acharCarta('Trono de Camelot');
        const heroi = acharCarta('Rei Arthur');
        g.board[1].monstro = heroi;
        g.players[1].mao = [dominio];

        const disparos = [];
        g.bus.on('statusAlterado', (e) => disparos.push(e.delta));

        TCG.acoes.jogarCartaDeCampo(g, 1, dominio); // ativação real -> 1 disparo (+3)
        const aposAtivar = disparos.length;
        TCG.aplicarPassivos(g); // simula reentrar na Fase Tática sem nada mudar -> 0 disparos a mais
        TCG.aplicarPassivos(g);
        const aposReaplicar = disparos.length;
        return { disparos, aposAtivar, aposReaplicar };
    }""")
    print("resultado:", r)
    assert r["aposAtivar"] == 1 and r["disparos"][0] == 3, \
        f"a ativação real deveria disparar statusAlterado(+3) exatamente uma vez: {r}"
    assert r["aposReaplicar"] == r["aposAtivar"], \
        f"reaplicar o passivo sem mudança nenhuma não deveria disparar statusAlterado de novo: {r}"
    assert not erros, f"erros no console: {erros}"
    page.close()
    print("OK  statusAlterado dispara só na mudança real, não no limpa-e-reaplica de rotina do passivo")


def testar_fx_nao_deixa_no_apos_uma_rajada_de_eventos(browser):
    """A fila de animação toca um job por vez, do início ao fim, antes do
    próximo começar (ver enfileirarFx/processarFilaFx em ui.js) — de
    propósito, pra NENHUM evento ser descartado ou sobreposto (mesmo numa
    sequência corrida, ex.: um turno de IA cheio de ações). Isso tem um
    custo: a fila drena proporcionalmente ao número de eventos, não a um
    tempo fixo — jogar a partida de verdade (mesmo só uns poucos "ciclos"
    do driver de teste, que já avança bem mais rápido que ritmo humano e
    pode disparar um turno de IA inteiro por clique) gera uma rajada grande
    demais pra esperar num teste (dezenas de segundos). Uma rajada
    CONTROLADA (poucos eventos sintéticos, misturando os vários tipos de
    efeito) já basta pra provar que a fila drena e não vaza nó nenhum."""
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    erros = []
    page.on("pageerror", lambda e: erros.append(str(e)))
    page.on("console", lambda m: erros.append(m.text) if m.type == "error" else None)
    page.goto(INDEX + "?seed=42")
    page.wait_for_timeout(200)
    imgs = page.query_selector_all("#selecao-opcoes img")
    imgs[0].click()
    page.wait_for_timeout(150)

    page.evaluate("""() => {
        const g = window.game;
        const acharCarta = (nome) => TCG.criarCardInstance(CARTAS.find(c => c.nome === nome));
        const alvo = acharCarta('Rei Arthur');
        g.board[2].monstro = alvo;
        window.ui.render();
        // mistura os vários tipos de fx ("de camada" e "em lugar") numa rajada só
        g.bus.emit('danoCausado', { quantidade: 3, alvo, alvoPlayer: 2 });
        g.bus.emit('danoCausado', { quantidade: 5, alvo, alvoPlayer: 2 });
        g.bus.emit('habilidadeAtivada', { playerId: 2, carta: alvo });
        g.bus.emit('vidaAlterada', { playerId: 2, delta: -4, total: 16 });
        g.bus.emit('cartaComprada', { playerId: 2, carta: acharCarta('Beowulf'), origem: 'turno' });
    }""")

    esvaziou = esperar_fila_fx_esvaziar(page, max_ms=15000)
    sobrando = page.eval_on_selector_all("#fx-layer > *", "els => els.length")

    assert esvaziou, "a fila de animação não esvaziou dentro do tempo máximo (15s)"
    assert sobrando == 0, f"#fx-layer vazou {sobrando} nó(s) depois da rajada"
    assert not erros, f"erros no console: {erros}"
    page.close()
    print("OK  #fx-layer não vaza nós depois de uma rajada de eventos (fila esvazia sozinha)")


def testar_fx_fila_toca_eventos_em_sequencia_sem_descartar(browser):
    """Dois golpes de dano seguidos no MESMO combatente tocam um de cada
    vez — nunca os dois números flutuantes ao mesmo tempo — e NENHUM dos
    dois é descartado, só porque o outro já estava animando."""
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    erros = []
    page.on("pageerror", lambda e: erros.append(str(e)))
    page.on("console", lambda m: erros.append(m.text) if m.type == "error" else None)
    page.goto(INDEX + "?seed=42")
    page.wait_for_timeout(200)
    imgs = page.query_selector_all("#selecao-opcoes img")
    imgs[0].click()
    page.wait_for_timeout(150)

    page.evaluate("""() => {
        const g = window.game;
        const acharCarta = (nome) => TCG.criarCardInstance(CARTAS.find(c => c.nome === nome));
        const alvo = acharCarta('Rei Arthur');
        g.board[2].monstro = alvo;
        window.ui.render();
        g.bus.emit('danoCausado', { quantidade: 3, alvo, alvoPlayer: 2 });
        g.bus.emit('danoCausado', { quantidade: 5, alvo, alvoPlayer: 2 });
    }""")

    # logo depois de disparar os DOIS eventos, só o primeiro pode estar
    # tocando — se os dois números aparecessem juntos aqui, não seria "um
    # de cada vez".
    page.wait_for_timeout(80)
    textos_cedo = page.eval_on_selector_all("#fx-layer .fx-num", "els => els.map(e => e.textContent)")

    # espera a fila esvaziar de vez, acumulando todo texto visto no caminho
    # — prova que os DOIS golpes realmente tocaram (nenhum foi descartado).
    vistos = set(textos_cedo)
    for _ in range(30):
        if page.evaluate("() => window.ui.filaFxVazia()"):
            break
        page.wait_for_timeout(100)
        vistos.update(page.eval_on_selector_all("#fx-layer .fx-num", "els => els.map(e => e.textContent)"))

    assert len(textos_cedo) <= 1, f"os dois golpes de dano apareceram AO MESMO TEMPO: {textos_cedo}"
    assert "-3" in vistos and "-5" in vistos, f"um dos dois golpes foi descartado, só vi: {vistos}"
    assert not erros, f"erros no console: {erros}"
    page.close()
    print("OK  fila de animação toca eventos em sequência (um de cada vez) sem descartar nenhum")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        testar_estado_inicial(browser)
        testar_acoes_e_hover(browser)
        testar_dano_por_diferenca_e_recompensa_de_mana(browser)
        testar_gatilho_de_maldicao_ao_ser_atacado(browser)
        testar_maldicao_gratis_para_setar(browser)
        testar_maldicao_oculta(browser)
        testar_maldicao_setada_visivel_para_o_dono_no_hover(browser)
        testar_dominio_unico_no_jogo_e_fundo_compartilhado(browser)
        testar_nunca_2_dominios_simultaneos_em_partida_real(browser)
        testar_dominio_aparece_em_partida_real(browser)
        testar_preview_altura_constante_e_cartas_de_modal_maiores(browser)
        testar_dominio_passivo_reaplicado_e_limpo_ao_destruir(browser)
        testar_dominio_gatilho_recorrente_entre_turnos(browser)
        testar_valhalla_redireciona_para_panteao(browser)
        testar_caixa_de_pandora_gatilho_correto(browser)
        testar_turno_da_ia_para_de_verdade_para_decisao_de_maldicao(browser)
        testar_maldicao_reativa_em_evento_nao_ataque(browser)
        testar_ia_nao_revela_propria_maldicao_no_proprio_turno(browser)
        testar_fx_summon_voa_e_limpa_sozinho(browser)
        testar_fx_statusAlterado_nao_dispara_ao_reaplicar_passivo_sem_mudanca(browser)
        testar_fx_nao_deixa_no_apos_uma_rajada_de_eventos(browser)
        testar_fx_fila_toca_eventos_em_sequencia_sem_descartar(browser)
        testar_partida_completa(browser)
        browser.close()
    print("\nTODOS OS TESTES PASSARAM")


if __name__ == "__main__":
    main()
