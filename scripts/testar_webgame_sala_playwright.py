# -*- coding: utf-8 -*-
"""Verificacao ponta-a-ponta do fluxo de sala por código (menu.html +
scripts/relay_server.py), no mesmo espirito de
testar_webgame_multiplayer_playwright.py (que cobre o relay LAN por
?servidor=): roda o relay de código de sala de verdade + um servidor HTTP
estático servindo a raiz do repo, abre DOIS BrowserContext isolados a
partir de menu.html, um clica "Criar Sala de Duelo" e lê o código exibido
na tela, o outro digita esse código e clica "Entrar" — exatamente como um
jogador faria — e confere que os dois terminam pareados em index.html.

Uso: python3 scripts/testar_webgame_sala_playwright.py
"""
import http.server
import os
import subprocess
import sys
import threading
import time

from playwright.sync_api import sync_playwright

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTTP_PORT = 8911
WS_PORT = 8912
URL_MENU = f"http://127.0.0.1:{HTTP_PORT}/webgame/menu.html?relay=ws://127.0.0.1:{WS_PORT}"


def iniciar_servidor_estatico():
    handler = lambda *args, **kwargs: http.server.SimpleHTTPRequestHandler(*args, directory=REPO, **kwargs)
    servidor = http.server.ThreadingHTTPServer(("127.0.0.1", HTTP_PORT), handler)
    thread = threading.Thread(target=servidor.serve_forever, daemon=True)
    thread.start()
    return servidor


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


def testar_criar_e_entrar_por_codigo(browser):
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

        page_host.goto(URL_MENU)
        page_host.click("#btn-criar-sala")

        # espera o código aparecer no status (texto: "...Código: XXXXX...")
        codigo = None
        for _ in range(30):
            texto = page_host.eval_on_selector("#menu-sala-status", "el => el.textContent")
            if "Código:" in texto:
                codigo = texto.split("Código:")[1].strip().split(" ")[0].rstrip(".—-")
                break
            page_host.wait_for_timeout(300)
        assert codigo and len(codigo) == 5, f"deveria ter mostrado um código de 5 caracteres, texto visto: {texto!r}"

        page_guest.goto(URL_MENU)
        page_guest.fill("#input-codigo-sala", codigo)
        page_guest.click("#btn-entrar-sala")

        # os dois devem navegar pra index.html e terminar com window.game/ui prontos
        page_host.wait_for_url("**/index.html*", timeout=10_000)
        page_guest.wait_for_url("**/index.html*", timeout=10_000)
        page_host.wait_for_timeout(1000)
        page_guest.wait_for_timeout(1000)

        assert page_host.evaluate("() => !!window.game && !!window.ui"), "host deveria ter window.game/window.ui prontos"
        assert page_guest.evaluate("() => !!window.game && !!window.ui"), "guest deveria ter window.game/window.ui prontos"

        # o código na URL de cada lado deve bater com o que foi criado/digitado
        assert codigo in page_host.url and "papel=host" in page_host.url, page_host.url
        assert codigo in page_guest.url and "papel=guest" in page_guest.url, page_guest.url

        # Cada lado deve ver os rótulos "Você"/"Oponente" do PRÓPRIO ponto
        # de vista, não copiados do host pela sincronização de estado (ver
        # rede.js aplicarSnapshot — nome não é sincronizado de propósito).
        nome_local_host = page_host.evaluate("() => window.game.players[1].nome")
        nome_local_guest = page_guest.evaluate("() => window.game.players[2].nome")
        assert "Você" in nome_local_host, f"host deveria se ver como 'Você': {nome_local_host}"
        assert "Você" in nome_local_guest, f"guest deveria se ver como 'Você': {nome_local_guest}"
        assert nome_local_host != page_host.evaluate("() => window.game.players[2].nome")
        assert nome_local_guest != page_guest.evaluate("() => window.game.players[1].nome")

        assert not erros, f"erros no console: {erros}"
        ctx_host.close()
        ctx_guest.close()
    finally:
        parar_relay(proc)
    print("OK  criar sala (menu) -> código exibido -> entrar por código -> ambos pareiam em index.html")


def testar_codigo_invalido_mostra_erro(browser):
    proc = iniciar_relay()
    try:
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(URL_MENU)
        page.fill("#input-codigo-sala", "ZZZZZ")
        page.click("#btn-entrar-sala")
        page.wait_for_timeout(1500)
        texto = page.eval_on_selector("#menu-sala-status", "el => el.textContent")
        tem_classe_erro = page.eval_on_selector("#menu-sala-status", "el => el.classList.contains('erro')")
        assert tem_classe_erro, f"status deveria estar marcado como erro, texto: {texto!r}"
        assert "index.html" not in page.url, "não deveria navegar pra index.html com um código inválido"
        ctx.close()
    finally:
        parar_relay(proc)
    print("OK  código inválido mostra erro no menu e não navega")


def main():
    iniciar_servidor_estatico()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        testar_criar_e_entrar_por_codigo(browser)
        testar_codigo_invalido_mostra_erro(browser)
        browser.close()
    print("\nTODOS OS TESTES DE SALA POR CÓDIGO PASSARAM")


if __name__ == "__main__":
    main()
