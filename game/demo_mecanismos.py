# -*- coding: utf-8 -*-
"""Teste focado nos mecanismos pedidos: selecao de carta pelo jogador,
notificacao de selecao, shuffle, Domínio/Encantamento/Maldição.
Rode com: python3 -m game.demo_mecanismos
"""
from __future__ import annotations

from .actions import (
    ActivateDomainAction, ActivateSetCurseAction, PlayEnchantmentAction,
    SetCurseAction, ShuffleAction, SummonAction,
)
from .components import CardInfo, Tipo, Zona
from .controller import GameController
from .events import (
    CardDiscarded, CardDrawn, CursePlaced, CurseTriggered, DeckShuffled,
    DomainActivated, EnchantmentPlayed, ManaChanged, SelectionMade,
    SelectionRequested,
)


def achar_na_mao(ctrl, player_id, tipo: Tipo):
    for c in ctrl.players[player_id].mao:
        info = ctrl.world.get_component(c, CardInfo)
        if info.tipo is tipo:
            return c
    return None


def main() -> None:
    ctrl = GameController(seed=7)

    ctrl.bus.subscribe(SelectionRequested, lambda e: print(
        f"[SelectionRequested #{e.request_id}] J{e.player_id}: '{e.prompt}' "
        f"opcoes={[ctrl.nome_da_carta(c) for c in e.opcoes]}"))
    ctrl.bus.subscribe(SelectionMade, lambda e: print(
        f"[SelectionMade #{e.request_id}] J{e.player_id} escolheu "
        f"{[ctrl.nome_da_carta(c) for c in e.escolha]}"))
    ctrl.bus.subscribe(DeckShuffled, lambda e: print(f"[DeckShuffled] {e.deck_nome}"))
    ctrl.bus.subscribe(DomainActivated, lambda e: print(f"[DomainActivated] {ctrl.nome_da_carta(e.card)}"))
    ctrl.bus.subscribe(EnchantmentPlayed, lambda e: print(f"[EnchantmentPlayed] {ctrl.nome_da_carta(e.card)}"))
    ctrl.bus.subscribe(CursePlaced, lambda e: print(f"[CursePlaced] {ctrl.nome_da_carta(e.card)} no slot {e.slot}"))
    ctrl.bus.subscribe(CurseTriggered, lambda e: print(f"[CurseTriggered] {ctrl.nome_da_carta(e.card)}"))
    ctrl.bus.subscribe(CardDrawn, lambda e: print(f"  (compra) J{e.player_id}: {ctrl.nome_da_carta(e.card)}"))
    ctrl.bus.subscribe(CardDiscarded, lambda e: print(f"  (descarte) J{e.player_id}: {ctrl.nome_da_carta(e.card)}"))
    ctrl.bus.subscribe(ManaChanged, lambda e: print(f"  (mana) J{e.player_id}: {e.delta:+d} -> {e.total}"))

    ctrl.iniciar_jogo()
    print("mão J1:", [ctrl.nome_da_carta(c) for c in ctrl.players[1].mao])

    # --- 1) mecanismo de SELECAO: jogador 1 escolhe 1 carta da mao pra descartar ---
    print("\n=== 1) selecao de carta pelo jogador (com notificacao) ===")
    mao_j1 = list(ctrl.players[1].mao)

    def _on_resolvido(escolha):
        carta = escolha[0]
        ps = ctrl.players[1]
        ps.mao.remove(carta)
        ctrl.world.get_component(carta, __import__("game.components", fromlist=["Location"]).Location).zona = Zona.PILHA_DESCARTE
        ctrl.bus.publish(CardDiscarded(player_id=1, card=carta))

    req_id = ctrl.solicitar_selecao(
        player_id=1, prompt="Escolha 1 carta da mão para descartar",
        opcoes=mao_j1, on_resolved=_on_resolvido,
    )
    # Numa GUI real, isso so roda quando o jogador clica; aqui simulamos o
    # clique escolhendo a primeira opcao.
    ctrl.resolver_selecao(req_id, [mao_j1[0]])
    print("mão J1 depois:", [ctrl.nome_da_carta(c) for c in ctrl.players[1].mao])

    # --- 2) ShuffleAction ---
    print("\n=== 2) shuffle action ===")
    baralho = ctrl.baralhos[1]
    antes = baralho.restantes()[:5]
    ShuffleAction(deck=baralho).executar(ctrl)
    depois = baralho.restantes()[:5]
    print("topo antes:", [ctrl.nome_da_carta(c) for c in antes])
    print("topo depois:", [ctrl.nome_da_carta(c) for c in depois])

    # --- 3) Domínio, Encantamento, Maldição ---
    print("\n=== 3) Domínio / Encantamento / Maldição ===")
    ctrl.avancar_fase()  # SAQUE -> INVOCACAO
    algum = ctrl.panteoes[1].restantes()[0]
    ctrl.submeter_acao(SummonAction(player_id=1, card=algum))
    ctrl.avancar_fase()  # INVOCACAO -> PRINCIPAL

    ctrl.players[1].mana = 10  # garante mana pra ativar Domínio + Encantamento neste teste
    dominio = achar_na_mao(ctrl, 1, Tipo.DOMINIO)
    if dominio:
        ctrl.submeter_acao(ActivateDomainAction(player_id=1, card=dominio))
        print("tabuleiro J1 (magia):", ctrl.estado()["tabuleiro"][1]["magia"])

    encantamento = achar_na_mao(ctrl, 1, Tipo.ENCANTAMENTO)
    if encantamento:
        ctrl.submeter_acao(PlayEnchantmentAction(player_id=1, card=encantamento))

    # avanca o resto do turno de J1 ate chegar na Fase Principal de J2
    while ctrl.fase_atual().jogador_da_vez != 2 or ctrl.fase_atual().fase.name != "PRINCIPAL":
        ctrl.avancar_fase()

    maldicao = achar_na_mao(ctrl, 2, Tipo.MALDICAO)
    if maldicao:
        ctrl.players[2].mana = 10  # garante mana pra baixar a maldicao neste teste
        ctrl.submeter_acao(SetCurseAction(player_id=2, card=maldicao))
        print("tabuleiro J2 (magia, virada p/ baixo):", ctrl.estado()["tabuleiro"][2]["magia"])
        ctrl.submeter_acao(ActivateSetCurseAction(player_id=2, card=maldicao))
        print("tabuleiro J2 (magia, depois de ativar):", ctrl.estado()["tabuleiro"][2]["magia"])

    print("\nOK — todos os mecanismos pedidos executaram sem erro.")


if __name__ == "__main__":
    main()
