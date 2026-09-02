# -*- coding: utf-8 -*-
"""Verificacao ponta-a-ponta da camada de partida (webgame/match.js): duas
partidas pareadas por sala de código (scripts/relay_server.py), igual
testar_webgame_sala_playwright.py, mas indo além do pareamento pra
exercitar contagem de vitórias + vida carregada entre duelos.

Forçar fim de duelo jogando pela UI de verdade seria frágil/lento demais
pra um teste (dezenas de ações até alguém chegar a 0 de vida ou esgotar o
Panteão); em vez disso o teste manipula `window.game` diretamente pra
simular o fim (`vida = 0` + TCG.checarFimDeJogo), que é exatamente o
gatilho real que webgame/match.js escuta (`game.bus.on("fimDeJogo", ...)`)
— o que está sob teste é a CAMADA DE PARTIDA (contagem de vitórias, vida
carregada, troca de duelo sincronizada pela rede), não o motor de jogo em
si (já coberto por outros testes).

Uso: python3 scripts/testar_webgame_partida_playwright.py
"""
import http.server
import os
import subprocess
import sys
import threading
import time

from playwright.sync_api import sync_playwright

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTTP_PORT = 8921
WS_PORT = 8922
URL_MENU = f"http://127.0.0.1:{HTTP_PORT}/webgame/menu.html?relay=ws://127.0.0.1:{WS_PORT}"


def iniciar_servidor_estatico():
    handler = lambda *args, **kwargs: http.server.SimpleHTTPRequestHandler(*args, directory=REPO, **kwargs)
    servidor = http.server.ThreadingHTTPServer(("127.0.0.1", HTTP_PORT), handler)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()


def iniciar_relay():
    proc = subprocess.Popen(
        [sys.executable, "-u", "scripts/relay_server.py", "--ws-port", str(WS_PORT)],
        cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    time.sleep(1.0)
    return proc


def parar_relay(proc):
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def parear_por_codigo(page_host, page_guest):
    page_host.goto(URL_MENU)
    page_host.click("#btn-criar-sala")
    codigo = None
    for _ in range(30):
        texto = page_host.eval_on_selector("#menu-sala-status", "el => el.textContent")
        if "Código:" in texto:
            codigo = texto.split("Código:")[1].strip().split(" ")[0].rstrip(".—-")
            break
        page_host.wait_for_timeout(300)
    assert codigo, "sala deveria ter mostrado um código"

    page_guest.goto(URL_MENU)
    page_guest.fill("#input-codigo-sala", codigo)
    page_guest.click("#btn-entrar-sala")

    page_host.wait_for_url("**/index.html*", timeout=10_000)
    page_guest.wait_for_url("**/index.html*", timeout=10_000)
    page_host.wait_for_timeout(1000)
    page_guest.wait_for_timeout(1000)


def forcar_fim_de_duelo(page_host, perdedor):
    """Só o HOST pode mexer no `game` de verdade (ver rede.js) — força a
    vida do `perdedor` a 0 e chama TCG.checarFimDeJogo, exatamente o
    gatilho que webgame/match.js escuta pra contar a vitória."""
    page_host.evaluate(
        """(perdedor) => {
            window.game.players[perdedor].vida = 0;
            TCG.checarFimDeJogo(window.game);
        }""",
        perdedor,
    )


def testar_vitorias_e_vida_carregada_entre_duelos(browser):
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

        parear_por_codigo(page_host, page_guest)

        # Duelo 1: guest (playerId 2) perde. Vencedor = host (playerId 1).
        vida_vencedor_no_fim = page_host.evaluate("() => (window.game.players[1].vida = 13)")
        forcar_fim_de_duelo(page_host, perdedor=2)
        page_host.wait_for_timeout(500)
        page_guest.wait_for_timeout(500)

        placar_host = page_host.evaluate("() => window.partida.vitoriasDuelo")
        placar_guest = page_guest.evaluate("() => window.partida.vitoriasDuelo")
        assert placar_host == {"1": 1, "2": 0} or placar_host == {1: 1, 2: 0}, placar_host
        assert placar_guest == placar_host, f"host e guest deveriam contar o placar igual: {placar_host} vs {placar_guest}"

        vida_carregada_host = page_host.evaluate("() => window.partida.vidaCarregada")
        assert vida_carregada_host["1"] == vida_vencedor_no_fim or vida_carregada_host[1] == vida_vencedor_no_fim, vida_carregada_host

        # Host inicia o duelo 2 (ver ui.js/match.js: só o host decide).
        page_host.evaluate("() => window.partida.iniciarProximoDuelo()")
        page_host.wait_for_timeout(800)
        page_guest.wait_for_timeout(800)

        duelo_host = page_host.evaluate("() => window.partida.duelo")
        duelo_guest = page_guest.evaluate("() => window.partida.duelo")
        assert duelo_host == 2, duelo_host
        assert duelo_guest == 2, duelo_guest

        vida_1_host = page_host.evaluate("() => window.game.players[1].vida")
        vida_2_host = page_host.evaluate("() => window.game.players[2].vida")
        assert vida_1_host == vida_vencedor_no_fim, f"vencedor deveria começar o duelo 2 com a vida carregada ({vida_vencedor_no_fim}), tem {vida_1_host}"
        assert vida_2_host == 20, f"perdedor deveria começar o duelo 2 com vida cheia (20), tem {vida_2_host}"

        vida_1_guest = page_guest.evaluate("() => window.game.players[1].vida")
        vida_2_guest = page_guest.evaluate("() => window.game.players[2].vida")
        assert vida_1_guest == vida_1_host and vida_2_guest == vida_2_host, \
            f"guest deveria ver a mesma vida do host no duelo 2: host=({vida_1_host},{vida_2_host}) guest=({vida_1_guest},{vida_2_guest})"

        # Duelo 2: host (playerId 1) perde -> vitória 1x1, sem fim de partida ainda.
        vida_vencedor_duelo2 = page_host.evaluate("() => (window.game.players[2].vida = 7)")
        forcar_fim_de_duelo(page_host, perdedor=1)
        page_host.wait_for_timeout(500)
        page_guest.wait_for_timeout(500)
        placar_host = page_host.evaluate("() => window.partida.vitoriasDuelo")
        assert placar_host == {"1": 1, "2": 1} or placar_host == {1: 1, 2: 1}, placar_host
        assert page_host.evaluate("() => window.partida.fimDePartida") is None

        # Duelos 3 e 4: host perde os dois -> guest chega a
        # TCG.VITORIAS_PARA_VENCER_PARTIDA (3) e vence a PARTIDA.
        for _ in range(2):
            page_host.evaluate("() => window.partida.iniciarProximoDuelo()")
            page_host.wait_for_timeout(800)
            page_guest.wait_for_timeout(800)
            forcar_fim_de_duelo(page_host, perdedor=1)
            page_host.wait_for_timeout(500)
            page_guest.wait_for_timeout(500)

        fim_host = page_host.evaluate("() => window.partida.fimDePartida")
        fim_guest = page_guest.evaluate("() => window.partida.fimDePartida")
        assert fim_host and (fim_host.get("vencedor") == 2), fim_host
        assert fim_guest == fim_host, f"host e guest deveriam concordar sobre o fim da partida: {fim_host} vs {fim_guest}"

        assert not erros, f"erros no console: {erros}"
        ctx_host.close()
        ctx_guest.close()
    finally:
        parar_relay(proc)
    print("OK  vitórias contadas nos dois lados, vida carregada pro vencedor/cheia pro perdedor, e fim de partida em 3 vitórias")


def main():
    iniciar_servidor_estatico()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        testar_vitorias_e_vida_carregada_entre_duelos(browser)
        browser.close()
    print("\nTODOS OS TESTES DE PARTIDA PASSARAM")


if __name__ == "__main__":
    main()
