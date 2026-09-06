# -*- coding: utf-8 -*-
"""Versão com assert de game/demo_mecanismos.py: seleção/notificação,
shuffle, e o fluxo de Domínio/Encantamento/Maldição."""
from __future__ import annotations

from game.actions import (
    ActivateDomainAction, ActivateSetCurseAction, PlayEnchantmentAction,
    SetCurseAction, ShuffleAction, SummonAction,
)
from game.components import CardInfo, FaceDown, Location, Tipo, Zona
from game.controller import GameController
from game.events import CardDiscarded, DeckShuffled, SelectionMade, SelectionRequested


def _achar_na_mao(ctrl, player_id, tipo: Tipo):
    for c in ctrl.players[player_id].mao:
        info = ctrl.world.get_component(c, CardInfo)
        if info.tipo is tipo:
            return c
    return None


def test_selecao_pedida_e_resolvida_via_callback():
    ctrl = GameController(seed=7)
    ctrl.iniciar_jogo()
    mao_j1 = list(ctrl.players[1].mao)

    pedidos = []
    escolhas = []
    ctrl.bus.subscribe(SelectionRequested, lambda e: pedidos.append(e))
    ctrl.bus.subscribe(SelectionMade, lambda e: escolhas.append(e))

    resolvido_com = []

    def _on_resolvido(escolha):
        resolvido_com.append(escolha)
        carta = escolha[0]
        ps = ctrl.players[1]
        ps.mao.remove(carta)
        ctrl.world.get_component(carta, Location).zona = Zona.PILHA_DESCARTE
        ctrl.bus.publish(CardDiscarded(player_id=1, card=carta))

    req_id = ctrl.solicitar_selecao(
        player_id=1, prompt="Escolha 1 carta da mão para descartar",
        opcoes=mao_j1, on_resolved=_on_resolvido,
    )
    assert len(pedidos) == 1
    assert pedidos[0].request_id == req_id
    assert pedidos[0].opcoes == mao_j1

    # on_resolved NÃO roda até resolver_selecao ser chamado — é assim que o
    # motor consegue "esperar" uma resposta que pode vir de qualquer lugar,
    # a qualquer momento depois, sem bloquear (game/selection.py:1-11).
    assert resolvido_com == []

    ctrl.resolver_selecao(req_id, [mao_j1[0]])
    assert resolvido_com == [[mao_j1[0]]]
    assert mao_j1[0] not in ctrl.players[1].mao
    assert len(escolhas) == 1


def test_shuffle_action_publica_evento_e_preserva_conjunto_de_cartas():
    ctrl = GameController(seed=7)
    ctrl.iniciar_jogo()
    baralho = ctrl.baralhos[1]
    antes = set(baralho.restantes())

    eventos = []
    ctrl.bus.subscribe(DeckShuffled, lambda e: eventos.append(e))

    ShuffleAction(deck=baralho).executar(ctrl)

    assert len(eventos) == 1
    assert eventos[0].deck_nome == baralho.nome
    # embaralhar reordena, nunca perde/duplica carta.
    assert set(baralho.restantes()) == antes


def test_dominio_encantamento_maldicao_fluxo_completo():
    ctrl = GameController(seed=7)
    ctrl.iniciar_jogo()
    ctrl.avancar_fase()  # SAQUE -> INVOCACAO
    algum = ctrl.panteoes[1].restantes()[0]
    ctrl.players[1].mana = 20
    ctrl.submeter_acao(SummonAction(player_id=1, card=algum))
    ctrl.avancar_fase()  # INVOCACAO -> PRINCIPAL

    ctrl.players[1].mana = 10
    dominio = _achar_na_mao(ctrl, 1, Tipo.DOMINIO)
    if dominio:
        ctrl.submeter_acao(ActivateDomainAction(player_id=1, card=dominio))
        assert dominio in ctrl.board.lado(1).magia
        assert ctrl.ultimo_dominio_ativado_por == 1

    encantamento = _achar_na_mao(ctrl, 1, Tipo.ENCANTAMENTO)
    if encantamento:
        ctrl.submeter_acao(PlayEnchantmentAction(player_id=1, card=encantamento))

    while ctrl.fase_atual().jogador_da_vez != 2 or ctrl.fase_atual().fase.name != "PRINCIPAL":
        ctrl.avancar_fase()

    maldicao = _achar_na_mao(ctrl, 2, Tipo.MALDICAO)
    if maldicao:
        ctrl.players[2].mana = 10
        ctrl.submeter_acao(SetCurseAction(player_id=2, card=maldicao))
        assert maldicao in ctrl.board.lado(2).magia
        fd = ctrl.world.get_component(maldicao, FaceDown)
        assert fd is not None and fd.virada_para_baixo
        ctrl.submeter_acao(ActivateSetCurseAction(player_id=2, card=maldicao))
