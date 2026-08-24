# -*- coding: utf-8 -*-
"""Simulacao de texto do motor — prova que ECS + Deck/Panteão + selecao +
notificacao + controller + efeitos funcionam juntos, sem precisar de GUI.
Rode com: python3 -m game.demo_sim
"""
from __future__ import annotations

from .actions import (
    ActivateAbilityAction, DeclareAttackAction, SummonAction,
)
from .controller import GameController
from .events import (
    AttackDeclared, CardDestroyed, CardDrawn, CombatantSummoned, DamageDealt,
    GameOver, LifeChanged, ManaChanged, PhaseChanged, SelectionRequested,
)


def _log_listeners(ctrl: GameController) -> None:
    ctrl.bus.subscribe(PhaseChanged, lambda e: print(
        f"  [fase] J{e.player_id} -> {e.fase_nova.name}"))
    ctrl.bus.subscribe(CardDrawn, lambda e: print(
        f"  [compra] J{e.player_id} comprou {ctrl.nome_da_carta(e.card)}"))
    ctrl.bus.subscribe(CombatantSummoned, lambda e: print(
        f"  [invocação] J{e.player_id} invocou {ctrl.nome_da_carta(e.card)}"))
    ctrl.bus.subscribe(ManaChanged, lambda e: print(
        f"  [mana] J{e.player_id} {'+' if e.delta >= 0 else ''}{e.delta} (total {e.total})"))
    ctrl.bus.subscribe(AttackDeclared, lambda e: print(
        f"  [ataque] J{e.atacante_player} ({ctrl.nome_da_carta(e.atacante_card)}) ataca "
        f"J{e.defensor_player} ({ctrl.nome_da_carta(e.defensor_card) if e.defensor_card else 'sem combatente'})"))
    ctrl.bus.subscribe(DamageDealt, lambda e: print(
        f"  [dano] {e.quantidade} em {'jogador ' + str(e.alvo_player) if e.alvo is None else ctrl.nome_da_carta(e.alvo)} ({e.origem})"))
    ctrl.bus.subscribe(CardDestroyed, lambda e: print(
        f"  [destruída] {ctrl.nome_da_carta(e.card)} ({e.motivo})"))
    ctrl.bus.subscribe(LifeChanged, lambda e: print(
        f"  [vida] J{e.player_id} {'+' if e.delta >= 0 else ''}{e.delta} (total {e.total})"))
    ctrl.bus.subscribe(SelectionRequested, lambda e: print(
        f"  [seleção pedida #{e.request_id}] J{e.player_id}: {e.prompt} — opções: "
        f"{[ctrl.nome_da_carta(c) for c in e.opcoes]}"))
    ctrl.bus.subscribe(GameOver, lambda e: print(
        f"  [FIM DE JOGO] J{e.perdedor_player} perdeu ({e.motivo})"))


def _achar_na_mao(ctrl: GameController, player_id: int, nome: str) -> int | None:
    for c in ctrl.players[player_id].mao:
        if ctrl.nome_da_carta(c) == nome:
            return c
    return None


def _achar_no_panteao(ctrl: GameController, player_id: int, nome: str) -> int | None:
    for c in ctrl.panteoes[player_id].restantes():
        if ctrl.nome_da_carta(c) == nome:
            return c
    return None


def main() -> None:
    ctrl = GameController(seed=42)
    _log_listeners(ctrl)

    print("=== iniciando jogo (compra mão inicial de 4, liga o relógio) ===")
    ctrl.iniciar_jogo()
    print(ctrl.estado())

    print("\n=== Fase de Invocação: J1 invoca o primeiro combatente do Panteão ===")
    ctrl.avancar_fase()  # SAQUE -> INVOCACAO
    p1_panteao_ids = ctrl.panteoes[1].restantes()
    escolhido = p1_panteao_ids[0]
    print(f"  escolhendo {ctrl.nome_da_carta(escolhido)} (custo "
          f"{ctrl.world.get_component(escolhido, __import__('game.components', fromlist=['ManaCost']).ManaCost).valor})")
    ctrl.submeter_acao(SummonAction(player_id=1, card=escolhido))

    print("\n=== Fase Principal: (nada a fazer neste exemplo) ===")
    ctrl.avancar_fase()  # INVOCACAO -> PRINCIPAL

    print("\n=== Fase de Batalha: ativa a Habilidade (se houver) e ataca ===")
    ctrl.avancar_fase()  # PRINCIPAL -> BATALHA
    from .components import AbilityCost
    if ctrl.world.has_component(escolhido, AbilityCost):
        ctrl.submeter_acao(ActivateAbilityAction(player_id=1, card=escolhido))
    ctrl.submeter_acao(DeclareAttackAction(player_id=1, oponente_id=2))

    print("\n=== passa a vez pra J2 (BATALHA -> SAQUE do J2) ===")
    ctrl.avancar_fase()
    print(ctrl.estado())

    print("\n=== rodando mais alguns turnos automaticamente ===")
    for _ in range(12):
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
                    custo = ctrl.world.get_component(carta, __import__("game.components", fromlist=["ManaCost"]).ManaCost).valor
                    if ctrl.players[jogador].mana >= custo:
                        ctrl.submeter_acao(SummonAction(player_id=jogador, card=carta))
        elif ts.fase.name == "BATALHA":
            if ctrl.board.lado(jogador).monstro is not None:
                ctrl.submeter_acao(DeclareAttackAction(player_id=jogador, oponente_id=ctrl.oponente_de(jogador)))
        ctrl.avancar_fase()

    print("\n=== estado final ===")
    print(ctrl.estado())


if __name__ == "__main__":
    main()
