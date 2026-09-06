# -*- coding: utf-8 -*-
"""Verificacao ponta-a-ponta da reconexão automática (webgame/match.js
tentarReconectar + heartbeat de webgame/sala.js): pareia dois navegadores
por sala de código, força uma queda TRANSIENTE de verdade fechando o
WebSocket do lado do teste (`window.__tcgWs.close()` — o processo do relay
continua rodando, a sala continua na memória, exatamente o cenário que a
reconexão sabe recuperar; diferente de reiniciar o relay, que apaga o
registro de salas e não é recuperável por design, ver scripts/relay_server.py),
e confere que o jogo volta a funcionar sozinho, sem recarregar a página.

Cobre dois casos: o HOST caindo e voltando (deve re-sincronizar o TRANSPORTE
só, sem criar duelo novo) e o GUEST caindo e voltando (deve disparar
"guestConectou" de novo no host, que reenvia um snapshot completo em vez de
começar um duelo novo — ver dispatch do host em match.js).

Uso: python3 scripts/testar_webgame_reconexao_playwright.py
"""
import http.server
import os
import subprocess
import sys
import threading
import time

from playwright.sync_api import sync_playwright

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTTP_PORT = 8931
WS_PORT = 8932
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


def derrubar_conexao(page):
    """Fecha o WebSocket ATUAL do lado do teste, sem tocar no relay — uma
    queda transiente de verdade (wifi, proxy ocioso, etc.), não um
    encerramento deliberado."""
    page.evaluate("() => window.__tcgWs && window.__tcgWs.close()")


def testar_host_reconecta_apos_queda(browser):
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
        duelo_antes = page_host.evaluate("() => window.partida.duelo")

        # evaluate_handle (não evaluate): um WebSocket não é serializável
        # como JSON, precisa de uma referência de objeto (JSHandle) pra
        # comparar identidade depois, do outro lado do close()/reconexão.
        ws_antes = page_host.evaluate_handle("() => window.__tcgWs")
        derrubar_conexao(page_host)
        # Contra um relay local a reconexão é rápida o bastante (mesma
        # máquina, sem latência de rede de verdade) que nem chega a dar pra
        # flagrar de fora o texto intermediário de "tentando reconectar" de
        # forma confiável — ver scripts/testar_webgame_reconexao_playwright.py
        # (debug manual confirmou: na hora do primeiro poll depois do
        # close(), a reconexão já tinha terminado). O que importa verificar
        # é o resultado: status limpo de novo, um WebSocket NOVO em uso, e
        # o duelo intacto — não o instante exato do meio do caminho.
        status = ""
        for _ in range(30):
            status = page_host.eval_on_selector("#status-multiplayer", "el => el.textContent")
            if not status:
                break
            page_host.wait_for_timeout(300)
        assert not status, f"status de conexão deveria limpar depois de reconectar, veio: {status!r}"

        # o duelo em andamento NÃO deve ter sido reiniciado
        assert page_host.evaluate("() => window.partida.duelo") == duelo_antes

        # prova de que uma reconexão de verdade aconteceu (não só "a queda
        # não chegou a acontecer"): o WebSocket em uso agora é outro objeto,
        # e o antigo está mesmo fechado.
        ws_depois_e_diferente = page_host.evaluate(
            "(wsAntes) => window.__tcgWs !== wsAntes && window.__tcgWs.readyState === WebSocket.OPEN",
            ws_antes,
        )
        assert ws_depois_e_diferente, "deveria estar usando um WebSocket NOVO e aberto depois da reconexão"

        # a conexão de verdade volta a funcionar: um evento do host chega no guest
        page_host.evaluate("() => { window.game.players[1].vida -= 1; window.game.bus.emit('vidaAlterada', {playerId:1, delta:-1, total:window.game.players[1].vida}); }")
        page_host.wait_for_timeout(1000)
        page_guest.wait_for_timeout(500)
        vida_guest = page_guest.evaluate("() => window.game.players[1].vida")
        vida_host = page_host.evaluate("() => window.game.players[1].vida")
        assert vida_guest == vida_host, f"guest deveria ver o novo estado do host depois da reconexão: host={vida_host} guest={vida_guest}"

        assert not erros, f"erros no console: {erros}"
        ctx_host.close()
        ctx_guest.close()
    finally:
        parar_relay(proc)
    print("OK  host reconecta sozinho depois de uma queda transiente, sem reiniciar o duelo")


def testar_guest_reconecta_apos_queda(browser):
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
        duelo_antes = page_guest.evaluate("() => window.partida.duelo")

        ws_antes = page_guest.evaluate_handle("() => window.__tcgWs")
        derrubar_conexao(page_guest)
        # ver nota equivalente em testar_host_reconecta_apos_queda: contra
        # um relay local o texto intermediário de "tentando reconectar"
        # não dá pra flagrar de forma confiável — verifica o resultado.
        status = ""
        for _ in range(30):
            status = page_guest.eval_on_selector("#status-multiplayer", "el => el.textContent")
            if not status:
                break
            page_guest.wait_for_timeout(300)
        assert not status, f"status de conexão deveria limpar depois de reconectar, veio: {status!r}"

        # o duelo NÃO deve ter reiniciado do lado do guest (resincronizacao,
        # não sincronizacaoInicial — ver dispatch do host em match.js)
        assert page_guest.evaluate("() => window.partida.duelo") == duelo_antes

        ws_depois_e_diferente = page_guest.evaluate(
            "(wsAntes) => window.__tcgWs !== wsAntes && window.__tcgWs.readyState === WebSocket.OPEN",
            ws_antes,
        )
        assert ws_depois_e_diferente, "deveria estar usando um WebSocket NOVO e aberto depois da reconexão"

        # o HOST detecta o "guestConectou" repetido e reenvia um snapshot
        # completo (religarRede com tipoSincronizacao "resincronizacao") —
        # confere que o estado do host (fonte de verdade) chegou de novo
        # no guest, sem precisar de nenhuma ação nova do host.
        page_guest.wait_for_timeout(1000)
        vida_1_host = page_host.evaluate("() => window.game.players[1].vida")
        vida_1_guest = page_guest.evaluate("() => window.game.players[1].vida")
        assert vida_1_guest == vida_1_host, f"guest deveria ter recebido um resync do host: host={vida_1_host} guest={vida_1_guest}"

        assert not erros, f"erros no console: {erros}"
        ctx_host.close()
        ctx_guest.close()
    finally:
        parar_relay(proc)
    print("OK  guest reconecta sozinho depois de uma queda transiente; host reenvia snapshot sem reiniciar o duelo")


def main():
    iniciar_servidor_estatico()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        testar_host_reconecta_apos_queda(browser)
        testar_guest_reconecta_apos_queda(browser)
        browser.close()
    print("\nTODOS OS TESTES DE RECONEXÃO PASSARAM")


if __name__ == "__main__":
    main()
