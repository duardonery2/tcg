# -*- coding: utf-8 -*-
"""Versão com assert de game/demo_sim.py — mesmo cenário (invocar, ativar
Habilidade, checar rejeição de ataque no turno 1, rodar turnos até o fim),
mas como regressão de verdade em vez de só imprimir na tela."""
from __future__ import annotations

import pytest

from game.actions import (
    ActivateAbilityAction, AcaoInvalida, DeclareAttackAction, SummonAction,
)
from game.components import AbilityCost, ManaCost
from game.controller import GameController


def test_iniciar_jogo_compra_mao_inicial_e_liga_relogio():
    ctrl = GameController(seed=42)
    ctrl.iniciar_jogo()
    for pid in ctrl.jogadores:
        assert len(ctrl.players[pid].mao) == 4
    ts = ctrl.fase_atual()
    assert ts.numero_turno == 1
    assert ts.jogador_da_vez == ctrl.jogadores[0]
    assert ts.fase.name == "SAQUE"


def test_invocar_combatente_do_panteao():
    ctrl = GameController(seed=42)
    ctrl.iniciar_jogo()
    ctrl.avancar_fase()  # SAQUE -> INVOCACAO
    escolhido = ctrl.panteoes[1].restantes()[0]
    ctrl.players[1].mana = 20  # cobre até o Custo de Mana mais caro do Panteão sorteado
    ctrl.submeter_acao(SummonAction(player_id=1, card=escolhido))
    assert ctrl.board.lado(1).monstro == escolhido
    assert escolhido not in ctrl.panteoes[1].restantes()


def test_ataque_recusado_no_primeiro_turno():
    """GAME_DESIGN.md, 'Declarar um ataque': nunca no 1º turno da partida."""
    ctrl = GameController(seed=42)
    ctrl.iniciar_jogo()
    ctrl.avancar_fase()  # SAQUE -> INVOCACAO
    escolhido = ctrl.panteoes[1].restantes()[0]
    ctrl.players[1].mana = 20
    ctrl.submeter_acao(SummonAction(player_id=1, card=escolhido))
    ctrl.avancar_fase()  # INVOCACAO -> PRINCIPAL
    ctrl.avancar_fase()  # PRINCIPAL -> BATALHA

    with pytest.raises(AcaoInvalida):
        ctrl.submeter_acao(DeclareAttackAction(player_id=1, oponente_id=2))


def test_ativar_habilidade_se_disponivel():
    ctrl = GameController(seed=42)
    ctrl.iniciar_jogo()
    ctrl.avancar_fase()  # SAQUE -> INVOCACAO
    escolhido = ctrl.panteoes[1].restantes()[0]
    ctrl.players[1].mana = 20
    ctrl.submeter_acao(SummonAction(player_id=1, card=escolhido))
    ctrl.avancar_fase()  # INVOCACAO -> PRINCIPAL
    ctrl.avancar_fase()  # PRINCIPAL -> BATALHA

    if ctrl.world.has_component(escolhido, AbilityCost):
        # Não afirma o total final de mana: o CUSTO é pago adiantado
        # (_pagar_mana), mas o EFEITO da Habilidade em si pode devolver mana
        # (algumas são "+Mana com contrapartida") — o que a Ação garante de
        # verdade é só que o custo foi cobrado e a Habilidade marcada como
        # usada, não o saldo líquido final (que varia por carta).
        ctrl.submeter_acao(ActivateAbilityAction(player_id=1, card=escolhido))
        assert ctrl.world.get_component(escolhido, AbilityCost).usada_neste_turno


def test_partida_completa_termina_em_fim_de_jogo_ou_turno_limite():
    """Mesmo loop de auto-jogo de demo_sim.py (invoca quando possível, ataca
    quando possível) — prova que uma partida inteira roda sem estourar
    exceção alguma até um GameOver ou um teto razoável de turnos."""
    ctrl = GameController(seed=42)
    ctrl.iniciar_jogo()
    ctrl.avancar_fase()
    escolhido = ctrl.panteoes[1].restantes()[0]
    ctrl.players[1].mana = 20
    ctrl.submeter_acao(SummonAction(player_id=1, card=escolhido))
    ctrl.avancar_fase()
    ctrl.avancar_fase()
    ctrl.avancar_fase()  # passa pra J2

    for _ in range(200):
        if ctrl.fim_de_jogo():
            break
        ts = ctrl.fase_atual()
        jogador = ts.jogador_da_vez
        if ts.fase.name == "INVOCACAO":
            lado = ctrl.board.lado(jogador)
            if lado.monstro is None:
                restantes = ctrl.panteoes[jogador].restantes()
                if restantes:
                    carta = restantes[0]
                    custo = ctrl.world.get_component(carta, ManaCost).valor
                    if ctrl.players[jogador].mana >= custo:
                        ctrl.submeter_acao(SummonAction(player_id=jogador, card=carta))
        elif ts.fase.name == "BATALHA":
            if ctrl.board.lado(jogador).monstro is not None and ts.numero_turno > 1:
                ctrl.submeter_acao(DeclareAttackAction(player_id=jogador, oponente_id=ctrl.oponente_de(jogador)))
        ctrl.avancar_fase()

    # não afirmamos QUEM vence (depende do sorteio de Panteão) — só que o
    # motor rodou sem levantar nada além do fim de jogo esperado.
    assert ctrl.fim_de_jogo() is not None
