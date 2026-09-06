# -*- coding: utf-8 -*-
"""Prova que a correção de RNG (game/systems.py + game/actions.py agora
passam ctrl.rng pra baralho.draw_random()/embaralhar() em vez de caírem
no `random` GLOBAL do processo) realmente deixa o motor determinístico:
duas partidas com a MESMA seed, jogadas de forma idêntica, têm que
produzir exatamente o mesmo resultado — incluindo as compras automáticas
da Fase de Saque e um ShuffleAction explícito, os dois pontos que
bypassavam ctrl.rng antes da correção."""
from __future__ import annotations

from game.actions import ShuffleAction, SummonAction
from game.controller import GameController


def _jogar_alguns_turnos(seed: int) -> list:
    """Sequência fixa de ações (mesma pros dois lados do teste) que
    exercita: compra automática (SAQUE, repetida), invocação, e um
    ShuffleAction explícito — os dois pontos corrigidos."""
    ctrl = GameController(seed=seed)
    ctrl.iniciar_jogo()

    historico_maos = [list(ctrl.players[1].mao), list(ctrl.players[2].mao)]

    ctrl.avancar_fase()  # SAQUE -> INVOCACAO
    escolhido = ctrl.panteoes[1].restantes()[0]
    ctrl.players[1].mana = 20
    ctrl.submeter_acao(SummonAction(player_id=1, card=escolhido))
    ctrl.avancar_fase()  # INVOCACAO -> PRINCIPAL

    ShuffleAction(deck=ctrl.baralhos[1]).executar(ctrl)
    historico_maos.append(list(ctrl.baralhos[1].restantes()))

    # mais algumas voltas de SAQUE (compra automática) pros dois jogadores.
    for _ in range(3):
        ctrl.avancar_fase()  # BATALHA
        ctrl.avancar_fase()  # FINAL
        ctrl.avancar_fase()  # SAQUE do próximo jogador (compra automática)
        historico_maos.append(list(ctrl.players[ctrl.fase_atual().jogador_da_vez].mao))
        ctrl.avancar_fase()  # INVOCACAO
        ctrl.avancar_fase()  # PRINCIPAL

    return historico_maos


def test_mesma_seed_produz_resultado_identico():
    resultado_a = _jogar_alguns_turnos(seed=42)
    resultado_b = _jogar_alguns_turnos(seed=42)
    assert resultado_a == resultado_b


def test_seed_diferente_diverge():
    resultado_42 = _jogar_alguns_turnos(seed=42)
    resultado_43 = _jogar_alguns_turnos(seed=43)
    assert resultado_42 != resultado_43
