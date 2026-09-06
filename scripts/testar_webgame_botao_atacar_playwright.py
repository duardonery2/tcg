# -*- coding: utf-8 -*-
"""Regressão: o GUEST clicando "Próxima Fase" pra sair de PRINCIPAL e
entrar em BATALHA no PRÓPRIO turno não via o botão "Atacar" aparecer —
`game.fase` no objeto `game` do guest já estava correto
(rede.js/aplicarSnapshot já tinha aplicado o snapshot), mas nada
disparava um render() depois, porque webgame/ui.js's handler de
"faseAlterada" só reage a esse evento pra INVOCACAO/SAQUE do próprio
jogador local — uma transição PRINCIPAL->BATALHA sozinha (sem
compra/mana envolvida) nunca teve nenhum handler que enfileirasse uma
animação e, de quebra, chamasse render() no final. O HOST nunca sofria
disso: o clique dele muda o `game` de verdade na hora, e tentar()
renderiza de qualquer forma, no mesmo instante, sem round-trip de rede.

Uso: python3 scripts/testar_webgame_botao_atacar_playwright.py
"""
import http.server
import os
import subprocess
import sys
import threading
import time

from playwright.sync_api import sync_playwright

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTTP_PORT = 8941
WS_PORT = 8942
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


def estado(page):
    return page.evaluate("() => window.game && ({fase: window.game.fase, jogadorDaVez: window.game.jogadorDaVez})")


def avancar_turno_proprio(page, jogador_da_vez, fase_alvo, tentativas=60):
    """Fecha modal de invocação se abrir, senão clica "Próxima Fase" —
    exatamente o que um jogador faria pra progredir o PRÓPRIO turno.
    `page.wait_for_function` (não um loop de `wait_for_timeout` fixo) pra
    cada micro-espera, já que renders concorrentes (ver match.js's novo
    render-de-segurança) podem substituir o DOM entre localizar e clicar
    um elemento — melhor confiar no retry embutido do Playwright."""
    for tentativa in range(tentativas):
        e = estado(page)
        ativo = page.eval_on_selector("#overlay-selecao", "el => el.classList.contains('ativo')")
        if e and e["fase"] == fase_alvo and e["jogadorDaVez"] == jogador_da_vez:
            return
        if ativo:
            n_opcoes = page.eval_on_selector_all("#selecao-opcoes img", "els => els.length")
            if n_opcoes:
                # A primeira opção pode ser um Combatente caro demais pra
                # mana atual (invocar recusa com AcaoInvalida e o modal
                # continua aberto, do jeito certo) — cicla pelas opções em
                # vez de martelar sempre a mesma que já falhou.
                page.click(f"#selecao-opcoes img >> nth={tentativa % n_opcoes}")
        elif e and e["jogadorDaVez"] == jogador_da_vez:
            page.click("#btn-fase")
        page.wait_for_timeout(300)
    raise AssertionError(f"nunca chegou em fase={fase_alvo} jogadorDaVez={jogador_da_vez}, último estado: {estado(page)}")


def testar_botao_atacar_aparece_pro_guest():
    proc = iniciar_relay()
    erros = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            ctx_host = browser.new_context()
            ctx_guest = browser.new_context()
            page_host = ctx_host.new_page()
            page_guest = ctx_guest.new_page()
            for nome, pg in [("host", page_host), ("guest", page_guest)]:
                pg.on("pageerror", lambda e, n=nome: erros.append(f"{n}: {e}"))
                pg.on("console", lambda m, n=nome: erros.append(f"{n}: {m.text}") if m.type == "error" else None)

            parear_por_codigo(page_host, page_guest)

            # Host joga o turno 1 inteiro: chega na PRÓPRIA Fase de
            # Batalha e clica de novo pra terminar o turno (sem atacar,
            # proibido no turno 1), passando a vez pro guest (J2).
            avancar_turno_proprio(page_host, 1, "BATALHA")
            for _ in range(30):
                if estado(page_host)["jogadorDaVez"] == 2:
                    break
                page_host.click("#btn-fase")
                page_host.wait_for_timeout(300)
            else:
                raise AssertionError(f"turno nunca passou pro guest: {estado(page_host)}")

            # Agora é o turno do GUEST: chega na PRÓPRIA Fase Principal
            # clicando na UI DELE (não a do host).
            avancar_turno_proprio(page_guest, 2, "PRINCIPAL")

            # Confere que o botão de Atacar está ESCONDIDO fora da Fase de
            # Batalha (sanity check da premissa do teste).
            display_antes = page_guest.eval_on_selector("#btn-atacar", "el => el.style.display")
            assert display_antes == "none", f"esperava #btn-atacar escondido em PRINCIPAL, veio {display_antes!r}"

            # O clique que reproduz o bug: PRINCIPAL -> BATALHA, no PRÓPRIO
            # turno do guest, clicado na UI DELE. `game.fase` já vira
            # BATALHA assim que o snapshot chega (aplicarSnapshot, ver
            # rede.js) independente do bug — o que está sob teste de
            # verdade é a TELA acompanhar isso sozinha, sem nenhuma ação
            # manual daqui alem do clique.
            page_guest.click("#btn-fase")
            page_guest.wait_for_function("() => window.game && window.game.fase === 'BATALHA'", timeout=5000)
            try:
                page_guest.wait_for_function(
                    "() => document.getElementById('btn-atacar').style.display !== 'none'", timeout=3000
                )
            except Exception:
                pass  # deixa a assert abaixo produzir a mensagem clara de falha
            display_depois = page_guest.eval_on_selector("#btn-atacar", "el => el.style.display")
            assert display_depois != "none", (
                "BUG: window.game.fase é BATALHA mas #btn-atacar continua escondido — "
                "a tela do guest não foi re-renderizada sozinha depois do evento de rede"
            )

            assert not erros, f"erros no console: {erros}"
            ctx_host.close()
            ctx_guest.close()
            browser.close()
    finally:
        parar_relay(proc)
    print("OK  botão de Atacar aparece pro guest ao entrar na própria Fase de Batalha")


def main():
    iniciar_servidor_estatico()
    testar_botao_atacar_aparece_pro_guest()
    print("\nTODOS OS TESTES DO BOTÃO DE ATACAR PASSARAM")


if __name__ == "__main__":
    main()
