# -*- coding: utf-8 -*-
"""Troca de fase, em ECS puro: o estado do turno vive num componente
(`TurnState`, numa entidade "singleton"), e `PhaseSystem.avancar()` e a UNICA
funcao que muda esse componente. Ela publica `PhaseChanged`; todo mundo mais
(compra de carta, reset de habilidade usada, expirar buffs 'neste turno')
reage a esse evento via EventBus — nenhum outro System sabe "que fase e",
so escuta a notificacao.

Ordem das fases por turno (GAME_DESIGN.md, 'A Estrutura do Turno'):
    SAQUE -> INVOCACAO -> PRINCIPAL -> BATALHA -> FINAL -> (troca de jogador) SAQUE
"""
from __future__ import annotations

from .components import (
    AbilityCost, AttackedThisTurn, CombatStats, DanoDobradoContraMonstro,
    Duracao, Fase, IgnoraFraquezaElemental, StatusEffects, TurnState,
)
from .ecs import System, World
from .events import EventBus, PhaseChanged, TurnStarted

_ORDEM = [Fase.SAQUE, Fase.INVOCACAO, Fase.PRINCIPAL, Fase.BATALHA, Fase.FINAL]


class PhaseSystem(System):
    """Dono do relogio do jogo. `avancar()` e chamado pelo Controller."""

    def __init__(self, bus: EventBus, jogadores: list[int]):
        self.bus = bus
        self.jogadores = jogadores

    def _turn_state(self, world: World) -> tuple[int, TurnState]:
        row = world.single(TurnState)
        if row is None:
            eid = world.create_entity()
            ts = world.add_component(eid, TurnState(jogador_da_vez=self.jogadores[0]))
            self.bus.publish(TurnStarted(player_id=ts.jogador_da_vez, numero_turno=ts.numero_turno))
            return eid, ts
        return row

    def estado_atual(self, world: World) -> TurnState:
        _, ts = self._turn_state(world)
        return ts

    def avancar(self, world: World) -> TurnState:
        """Avanca uma fase; se estava em FINAL, passa a vez e volta pra
        SAQUE do proximo jogador."""
        _, ts = self._turn_state(world)
        idx = _ORDEM.index(ts.fase)

        anterior = ts.fase
        if idx < len(_ORDEM) - 1:
            ts.fase = _ORDEM[idx + 1]
        else:
            # fim da Fase Final -> troca de jogador, novo turno
            i = self.jogadores.index(ts.jogador_da_vez)
            ts.jogador_da_vez = self.jogadores[(i + 1) % len(self.jogadores)]
            ts.numero_turno += 1
            ts.fase = Fase.SAQUE

        self.bus.publish(PhaseChanged(player_id=ts.jogador_da_vez, fase_anterior=anterior, fase_nova=ts.fase))
        if ts.fase is Fase.SAQUE and anterior is Fase.FINAL:
            self.bus.publish(TurnStarted(player_id=ts.jogador_da_vez, numero_turno=ts.numero_turno))
        return ts

    def update(self, world: World, **ctx) -> None:
        # PhaseSystem so muda de fase quando `avancar()` e chamado
        # explicitamente pelo Controller (a troca de fase e uma decisao de
        # jogo, nao algo que acontece sozinho a cada tick).
        pass


class UpkeepSystem(System):
    """Reage a PhaseChanged em dois momentos distintos do turno:
    - Fase de Saque (início do turno de quem entra): zera 'Habilidade
      usada neste turno' de TODOS os combatentes — turno novo, direito de
      usar Habilidade renovado pra quem quer que jogue a seguir.
    - Fase Final (fim do turno de quem está saindo dela — o jogador_da_vez
      ainda É esse jogador nesse instante, a troca só acontece no PRÓXIMO
      avancar()): expira todo StatusEffect com duração NESTE_TURNO/
      ATE_FIM_DE_TURNO, dos dois lados — "neste turno" significa até o
      fim do turno atual, não importa em qual combatente o efeito está."""

    def __init__(self, bus: EventBus):
        bus.subscribe(PhaseChanged, self._on_phase_changed)
        self._world_ref: World | None = None

    def bind(self, world: World) -> None:
        self._world_ref = world

    def _on_phase_changed(self, event: PhaseChanged) -> None:
        if self._world_ref is None:
            return
        world = self._world_ref
        if event.fase_nova is Fase.SAQUE:
            for eid, ability in world.query(AbilityCost):
                ability.usada_neste_turno = False
            for eid, _ in list(world.query(AttackedThisTurn)):
                world.remove_component(eid, AttackedThisTurn)
        elif event.fase_nova is Fase.FINAL:
            for eid, statuses in world.query(StatusEffects):
                restantes = []
                for st in statuses.itens:
                    if st.duracao in (Duracao.NESTE_TURNO, Duracao.ATE_FIM_DE_TURNO):
                        continue  # expira
                    restantes.append(st)
                if len(restantes) != len(statuses.itens):
                    statuses.itens = restantes
                    _recalcular_stats(world, eid)
            # DanoDobradoContraMonstro (Sigurd) e IgnoraFraquezaElemental
            # (Shoggoth: "Disforme... até o fim do turno") são sempre
            # NESTE_TURNO/ATE_FIM_DE_TURNO por natureza — a mera presença do
            # componente já significa "ainda não expirou"; removidos
            # incondicionalmente aqui, sem precisar reler o campo `duracao`
            # de IgnoraFraquezaElemental (que existia mas nunca era checado —
            # bug real: o Disforme de Shoggoth nunca expirava). Céus de
            # Valíria também usa IgnoraFraquezaElemental, mas via passivo
            # limpa-e-reaplica a cada Fase Principal — remover aqui não
            # atrapalha, só cria uma janela inofensiva até a próxima
            # Principal reaplicar.
            for eid, _ in list(world.query(DanoDobradoContraMonstro)):
                world.remove_component(eid, DanoDobradoContraMonstro)
            for eid, _ in list(world.query(IgnoraFraquezaElemental)):
                world.remove_component(eid, IgnoraFraquezaElemental)

    def update(self, world: World, **ctx) -> None:
        self.bind(world)


def _recalcular_stats(world: World, entity: int) -> None:
    stats = world.get_component(entity, CombatStats)
    statuses = world.get_component(entity, StatusEffects)
    if stats is None:
        return
    pow_, res_ = stats.base_pow, stats.base_res
    if statuses:
        for st in statuses.itens:
            if st.atributo == "pow":
                pow_ += st.magnitude
            elif st.atributo == "res":
                res_ += st.magnitude
    # sem teto de 20 aqui de proposito: qualquer alteracao de POW/RES vem de
    # Habilidade, Encantamento ou Maldição, e o teto "só pode ser quebrado
    # por feitiços" (GAME_DESIGN.md) — so um piso em 0.
    stats.atual_pow, stats.atual_res = max(pow_, 0), max(res_, 0)
