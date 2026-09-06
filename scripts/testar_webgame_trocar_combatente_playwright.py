# -*- coding: utf-8 -*-
"""Regressão: o GUEST não conseguia trocar o combatente ativo pelo
Panteão na Fase Principal (webgame/ui.js's abrirPanteaoParaTrocar chama
`acoes.trocarCombatente(...)`, mas webgame/rede.js's acoesDoGuest não
tinha esse método — o clique estourava um TypeError silencioso, sem
mandar intent nenhum pro host, e o host também não sabia tratar
`fn:"trocarCombatente"` mesmo se tivesse chegado). O HOST nunca sofria
disso: `acoes` pra ele é TCG.acoes de verdade, que sempre teve
trocarCombatente.

Uso: python3 scripts/testar_webgame_trocar_combatente_playwright.py
"""
import http.server
import os
import subprocess
import sys
import threading
import time

from playwright.sync_api import sync_playwright

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTTP_PORT = 8951
WS_PORT = 8952
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
    """Fecha modal de invocação se abrir (ciclando pelas opções, caso a
    primeira seja cara demais pra mana atual), senão clica "Próxima
    Fase" — exatamente o que um jogador faria pra progredir o PRÓPRIO
    turno."""
    for tentativa in range(tentativas):
        e = estado(page)
        ativo = page.eval_on_selector("#overlay-selecao", "el => el.classList.contains('ativo')")
        if e and e["fase"] == fase_alvo and e["jogadorDaVez"] == jogador_da_vez:
            return
        if ativo:
            n_opcoes = page.eval_on_selector_all("#selecao-opcoes img", "els => els.length")
            if n_opcoes:
                page.click(f"#selecao-opcoes img >> nth={tentativa % n_opcoes}")
        elif e and e["jogadorDaVez"] == jogador_da_vez and e["fase"] != "INVOCACAO":
            # A Fase de Invocação NUNCA precisa de um clique manual em
            # "Próxima Fase" — ela sempre se resolve sozinha (solicitarInvocacao,
            # ui.js), seja escolhendo uma carta no modal, seja pulando
            # automaticamente quando não há opção paga. O modal, porém,
            # abre dentro da fila de FX (enfileirarFx) — pode ficar
            # ENFILEIRADO por um instante atrás de uma animação anterior
            # (ex.: a compra automática da Fase de Saque) antes de
            # `overlay-selecao` de fato ganhar a classe "ativo". Clicar
            # "Próxima Fase" cegamente nesse intervalo (achando que "não
            # tem modal, então não tem nada a fazer aqui") avança a fase
            # ANTES do modal enfileirado abrir — a invocação nunca
            # acontece, e o combatente ativo fica None pro resto do
            # duelo. Fora da INVOCACAO, todas as outras fases exigem
            # mesmo um clique explícito.
            page.click("#btn-fase")
        page.wait_for_timeout(300)
    raise AssertionError(f"nunca chegou em fase={fase_alvo} jogadorDaVez={jogador_da_vez}, último estado: {estado(page)}")


def testar_guest_troca_combatente_pelo_panteao():
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

            # Dá mana de sobra pro guest (J2) BEM cedo, antes de qualquer
            # turno rodar — nos DOIS lados: o HOST valida/executa as ações
            # de verdade contra a PRÓPRIA cópia, mas solicitarInvocacao
            # (ui.js) decide se ABRE o modal de invocação com base na mana
            # LOCAL do próprio guest, no exato instante síncrono em que
            # "faseAlterada" chega — corrigir depois que esse evento já
            # disparou o auto-skip (mana insuficiente) chega tarde demais.
            # Fazendo isso ANTES do turno 1 do host (não há ganho de mana
            # no PRIMEIRO turno de cada jogador, e nada mais mexe na mana
            # de J2 até ser a vez dele), não existe janela de corrida
            # nenhuma pra perder.
            page_host.evaluate("() => { window.game.players[2].mana = 20; }")
            page_guest.evaluate("() => { window.game.players[2].mana = 20; }")

            # Host joga o turno 1 inteiro e passa a vez pro guest (J2).
            avancar_turno_proprio(page_host, 1, "BATALHA")
            for _ in range(30):
                if estado(page_host)["jogadorDaVez"] == 2:
                    break
                page_host.click("#btn-fase")
                page_host.wait_for_timeout(300)
            else:
                raise AssertionError(f"turno nunca passou pro guest: {estado(page_host)}")

            # Guest joga a própria Fase de Invocação (summon normal, via o
            # modal automático de solicitarInvocacao) e chega na própria
            # Fase Principal com um combatente ativo em campo.
            page_guest.wait_for_function(
                "() => window.game && window.game.jogadorDaVez === 2 && window.game.fase === 'INVOCACAO'",
                timeout=10_000,
            )
            avancar_turno_proprio(page_guest, 2, "PRINCIPAL")
            # `window.game.fase` já reflete PRINCIPAL nesse ponto
            # (aplicarSnapshot é incondicional), mas o DOM (inclusive o
            # onClick da pilha do Panteão, que só existe quando
            # podeTrocarCombatente bate no render ATUAL) pode ainda estar
            # atrasado atrás de uma animação em andamento (ex.: o combatente
            # acabado de invocar ainda "voando" até o slot) — espera a fila
            # de FX esvaziar (e o render que vem junto) antes de interagir
            # com qualquer elemento clicável.
            for _ in range(20):
                if page_guest.evaluate("() => window.ui.filaFxVazia()"):
                    break
                page_guest.wait_for_timeout(300)
            else:
                raise AssertionError("fila de FX nunca esvaziou depois da invocação inicial do guest")

            monstro_antes = page_guest.evaluate("() => window.game.board[2].monstro && window.game.board[2].monstro.instanceId")
            assert monstro_antes is not None, "guest deveria ter um combatente ativo antes da troca"

            # Abre o Panteão (pilha do PRÓPRIO lado do guest) pra trocar —
            # exatamente o clique relatado como quebrado.
            page_guest.click("#tabuleiro-jogador [data-pilha='panteao'] .slot")
            page_guest.wait_for_function(
                "() => document.getElementById('overlay-selecao').classList.contains('ativo')", timeout=3000
            )
            n_opcoes = page_guest.eval_on_selector_all("#selecao-opcoes img", "els => els.length")
            assert n_opcoes > 0, "modal de troca deveria oferecer opções do Panteão restante"
            page_guest.click("#selecao-opcoes img >> nth=0")

            # Sem a correção, nada disto acontece: o clique acima estoura
            # um TypeError local (acoes.trocarCombatente indefinido) e
            # NENHUM intent chega no host — o combatente ativo nunca muda,
            # nos dois lados.
            page_guest.wait_for_function(
                f"() => window.game.board[2].monstro && window.game.board[2].monstro.instanceId !== {monstro_antes}",
                timeout=5000,
            )
            monstro_depois_guest = page_guest.evaluate("() => window.game.board[2].monstro.instanceId")
            page_host.wait_for_timeout(500)
            monstro_depois_host = page_host.evaluate("() => window.game.board[2].monstro && window.game.board[2].monstro.instanceId")
            assert monstro_depois_host == monstro_depois_guest, (
                f"host e guest deveriam concordar sobre o novo combatente ativo: "
                f"host={monstro_depois_host} guest={monstro_depois_guest}"
            )

            assert not erros, f"erros no console: {erros}"
            ctx_host.close()
            ctx_guest.close()
            browser.close()
    finally:
        parar_relay(proc)
    print("OK  guest troca o combatente ativo pelo Panteão na própria Fase Principal")


def main():
    iniciar_servidor_estatico()
    testar_guest_troca_combatente_pelo_panteao()
    print("\nTODOS OS TESTES DE TROCA DE COMBATENTE PASSARAM")


if __name__ == "__main__":
    main()
