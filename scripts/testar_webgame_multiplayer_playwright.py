# -*- coding: utf-8 -*-
"""Verificacao ponta-a-ponta do multiplayer LAN (scripts/relay_lan.py +
webgame/rede.js), no mesmo espirito de testar_webgame_playwright.py — roda
o relay de verdade e DOIS BrowserContext Playwright totalmente isolados
(nao duas abas do mesmo contexto — pra garantir que o proprio teste nao
esta compartilhando estado por fora da rede), um como host e outro como
guest, e joga uma partida de verdade clicando nos dois lados.

Uso: python3 scripts/testar_webgame_multiplayer_playwright.py
"""
import os
import subprocess
import sys
import time

from playwright.sync_api import sync_playwright

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTTP_PORT = 8901
WS_PORT = 8902
URL_BASE = f"http://127.0.0.1:{HTTP_PORT}/webgame/index.html?servidor=127.0.0.1:{WS_PORT}"


def iniciar_relay():
    proc = subprocess.Popen(
        [sys.executable, "scripts/relay_lan.py", "--http-port", str(HTTP_PORT), "--ws-port", str(WS_PORT)],
        cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    time.sleep(1.0)  # da tempo do servidor HTTP/WS subir antes do primeiro goto()
    return proc


def parar_relay(proc):
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def fechar_modal_se_aberto(page, escolher=True):
    ativo = page.eval_on_selector("#overlay-selecao", "el => el.classList.contains('ativo')")
    if not ativo:
        return False
    if escolher:
        imgs = page.query_selector_all("#selecao-opcoes img")
        if imgs:
            imgs[0].click()
            return True
    btn_pular = page.query_selector("#selecao-pular")
    if btn_pular:
        btn_pular.click()
        return True
    return False


def testar_conexao_e_papeis(browser):
    """A primeira conexão no relay vira host, a segunda vira guest — cada
    navegador aprende seu papel sozinho (mensagem "papel" do relay) e cria
    o `game` certo (host: simulação de verdade; guest: espelho)."""
    proc = iniciar_relay()
    erros = []
    try:
        ctx_host = browser.new_context()
        ctx_guest = browser.new_context()
        page_host = ctx_host.new_page()
        page_guest = ctx_guest.new_page()
        for nome, pg in [("host", page_host), ("guest", page_guest)]:
            pg.on("pageerror", lambda e, n=nome: erros.append(f"{n}: {e}"))
            pg.on("console", lambda m, n=nome: erros.append(f"{n}: {m.text}") if m.type == "error" else None)

        page_host.goto(URL_BASE + "&seed=7")
        page_host.wait_for_timeout(500)
        page_guest.goto(URL_BASE)
        page_guest.wait_for_timeout(1500)

        assert page_host.evaluate("() => !!window.game") and page_host.evaluate("() => !!window.ui"), \
            "host deveria ter window.game/window.ui prontos"
        assert page_guest.evaluate("() => !!window.game") and page_guest.evaluate("() => !!window.ui"), \
            "guest deveria ter window.game/window.ui prontos"
        assert not erros, f"erros no console: {erros}"
        ctx_host.close()
        ctx_guest.close()
    finally:
        parar_relay(proc)
    print("OK  host e guest conectam no relay e cada um recebe o papel certo")


def testar_sincronizacao_e_ocultacao(browser):
    """O host invoca um Combatente -> o guest vê o resultado sincronizado.
    A mão do HOST nunca aparece com identidade real pro GUEST (e vice-versa)
    — a filtragem é no DADO (TCG.estadoCompletoPara), não só na tela."""
    proc = iniciar_relay()
    erros = []
    try:
        ctx_host = browser.new_context()
        ctx_guest = browser.new_context()
        page_host = ctx_host.new_page()
        page_guest = ctx_guest.new_page()
        for nome, pg in [("host", page_host), ("guest", page_guest)]:
            pg.on("pageerror", lambda e, n=nome: erros.append(f"{n}: {e}"))
            pg.on("console", lambda m, n=nome: erros.append(f"{n}: {m.text}") if m.type == "error" else None)

        page_host.goto(URL_BASE + "&seed=7")
        page_host.wait_for_timeout(500)
        page_guest.goto(URL_BASE)
        page_guest.wait_for_timeout(1500)

        fechar_modal_se_aberto(page_host)  # host invoca o 1o combatente da modal
        page_host.wait_for_timeout(1500)

        monstro_host = page_host.evaluate("() => window.game.board[1].monstro?.nome")
        monstro_pelo_guest = page_guest.evaluate("() => window.game.board[1].monstro?.nome")
        assert monstro_host and monstro_host == monstro_pelo_guest, \
            f"o combatente invocado pelo host deveria sincronizar pro guest: host={monstro_host!r} guest={monstro_pelo_guest!r}"

        mao_host_vista_pelo_guest = page_guest.evaluate("() => window.game.players[1].mao.map(c => c.oculto ? 'OCULTO' : c.nome)")
        assert mao_host_vista_pelo_guest and all(v == "OCULTO" for v in mao_host_vista_pelo_guest), \
            f"a mão do host nunca deveria aparecer com identidade real pro guest: {mao_host_vista_pelo_guest}"

        assert not erros, f"erros no console: {erros}"
        ctx_host.close()
        ctx_guest.close()
    finally:
        parar_relay(proc)
    print("OK  ação do host sincroniza pro guest; mão do host nunca vaza identidade pro guest")


def testar_acao_do_guest_chega_no_host(browser):
    """O turno inteiro do host termina, chega a vez do guest — ele invoca
    de verdade clicando na PRÓPRIA UI (não window.game direto), a intenção
    viaja pela rede, o host aplica de verdade, e o resultado volta
    sincronizado pro guest."""
    proc = iniciar_relay()
    erros = []
    try:
        ctx_host = browser.new_context()
        ctx_guest = browser.new_context()
        page_host = ctx_host.new_page()
        page_guest = ctx_guest.new_page()
        for nome, pg in [("host", page_host), ("guest", page_guest)]:
            pg.on("pageerror", lambda e, n=nome: erros.append(f"{n}: {e}"))
            pg.on("console", lambda m, n=nome: erros.append(f"{n}: {m.text}") if m.type == "error" else None)

        page_host.goto(URL_BASE + "&seed=7")
        page_host.wait_for_timeout(500)
        page_guest.goto(URL_BASE)
        page_guest.wait_for_timeout(1500)

        fechar_modal_se_aberto(page_host)  # host invoca
        page_host.wait_for_timeout(1500)
        page_host.click("#btn-fase")  # PRINCIPAL -> BATALHA
        page_host.wait_for_timeout(1500)
        page_host.click("#btn-fase")  # BATALHA -> termina o turno do host
        page_host.wait_for_timeout(2500)

        # espera o modal de invocação abrir de verdade na TELA do guest
        abriu = False
        for _ in range(30):
            ativo = page_guest.eval_on_selector("#overlay-selecao", "el => el.classList.contains('ativo')")
            estado = page_guest.evaluate("() => ({ jogadorDaVez: window.game.jogadorDaVez, fase: window.game.fase })")
            if ativo and estado["jogadorDaVez"] == 2:
                abriu = True
                break
            page_guest.wait_for_timeout(300)
        assert abriu, f"o modal de invocação deveria abrir pro guest quando é a vez dele (estado={estado})"

        imgs = page_guest.query_selector_all("#selecao-opcoes img")
        assert imgs, "modal de invocação do guest deveria ter opções"
        imgs[0].click()
        page_guest.wait_for_timeout(1500)

        monstro_guest = page_guest.evaluate("() => window.game.board[2].monstro?.nome")
        monstro_visto_pelo_host = page_host.evaluate("() => window.game.board[2].monstro?.nome")
        assert monstro_guest and monstro_guest == monstro_visto_pelo_host, \
            f"a invocação do guest (clicada na própria UI dele) deveria refletir no host: guest={monstro_guest!r} host={monstro_visto_pelo_host!r}"

        assert not erros, f"erros no console: {erros}"
        ctx_host.close()
        ctx_guest.close()
    finally:
        parar_relay(proc)
    print("OK  ação do guest (clicada na UI de verdade) chega no host e sincroniza de volta")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        testar_conexao_e_papeis(browser)
        testar_sincronizacao_e_ocultacao(browser)
        testar_acao_do_guest_chega_no_host(browser)
        browser.close()
    print("\nTODOS OS TESTES DE MULTIPLAYER PASSARAM")


if __name__ == "__main__":
    main()
