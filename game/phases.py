# -*- coding: utf-8 -*-
"""Troca de fase, em ECS puro: o estado do turno vive num componente
(`TurnState`, numa entidade "singleton"), e `PhaseSystem.avancar()` e a UNICA
funcao que muda esse componente. Ela publica `PhaseChanged`; todo mundo mais
(compra de carta, reset de habilidade usada, expirar buffs 'neste turno')
reage a esse evento via EventBus — nenhum outro System sabe "que fase e",
so escuta a notificacao.

Ordem das fases por turno (GAME_DESIGN.md, 'A Estrutura do Turno'):
    RECURSO -> INVOCACAO -> TATICA -> COMBATE -> (troca de jogador) RECURSO
"""
from __future__ import annotations

from .components import (
    AbilityCost, CombatStats, Duracao, Fase, StatusEffects, TurnState,
)
from .ecs import System, World
from .events import EventBus, PhaseChanged, TurnStarted

_ORDEM = [Fase.RECURSO, Fase.INVOCACAO, Fase.TATICA, Fase.COMBATE]


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
        """Avanca uma fase; se estava em COMBATE, passa a vez e volta pra
        RECURSO do proximo jogador."""
        _, ts = self._turn_state(world)
        idx = _ORDEM.index(ts.fase)

        anterior = ts.fase
        if idx < len(_ORDEM) - 1:
            ts.fase = _ORDEM[idx + 1]
        else:
            # fim da Fase de Combate -> troca de jogador, novo turno
            i = self.jogadores.index(ts.jogador_da_vez)
            ts.jogador_da_vez = self.jogadores[(i + 1) % len(self.jogadores)]
            ts.numero_turno += 1
            ts.fase = Fase.RECURSO

        self.bus.publish(PhaseChanged(player_id=ts.jogador_da_vez, fase_anterior=anterior, fase_nova=ts.fase))
        if ts.fase is Fase.RECURSO and anterior is Fase.COMBATE:
            self.bus.publish(TurnStarted(player_id=ts.jogador_da_vez, numero_turno=ts.numero_turno))
        return ts

    def update(self, world: World, **ctx) -> None:
        # PhaseSystem so muda de fase quando `avancar()` e chamado
        # explicitamente pelo Controller (a troca de fase e uma decisao de
        # jogo, nao algo que acontece sozinho a cada tick).
        pass


class UpkeepSystem(System):
    """Reage a PhaseChanged: zera 'Habilidade usada neste turno' e expira
    StatusEffects com duracao NESTE_TURNO/ATE_FIM_DE_TURNO sempre que o
    jogador DA VEZ entra na Fase de Recurso (ou seja, no inicio do turno
    dele — os buffs postos por ELE no turno anterior caem)."""

    def __init__(self, bus: EventBus):
        bus.subscribe(PhaseChanged, self._on_phase_changed)
        self._world_ref: World | None = None

    def bind(self, world: World) -> None:
        self._world_ref = world

    def _on_phase_changed(self, event: PhaseChanged) -> None:
        if event.fase_nova is not Fase.RECURSO or self._world_ref is None:
            return
        world = self._world_ref
        for eid, ability in world.query(AbilityCost):
            ability.usada_neste_turno = False
        for eid, statuses in world.query(StatusEffects):
            restantes = []
            for st in statuses.itens:
                if st.duracao in (Duracao.NESTE_TURNO, Duracao.ATE_FIM_DE_TURNO):
                    continue  # expira
                restantes.append(st)
            if len(restantes) != len(statuses.itens):
                statuses.itens = restantes
                _recalcular_stats(world, eid)

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
