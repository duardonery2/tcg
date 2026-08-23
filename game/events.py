# -*- coding: utf-8 -*-
"""Sistema de notificacao (Observer/Event Bus).

Toda mudanca de estado relevante (fase virou, carta comprada, carta destruida,
selecao pedida ao jogador, selecao respondida...) publica um Evento aqui.
Systems, efeitos de carta E a GUI assinam os eventos que importam pra cada um
— a GUI nunca especula sobre o estado, ela so redesenha quando notificada.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, DefaultDict
from collections import defaultdict


# ---------------------------------------------------------------------------
# Eventos
# ---------------------------------------------------------------------------

@dataclass
class Event:
    """Classe-base. Cada evento concreto e um dataclass que herda daqui."""


@dataclass
class PhaseChanged(Event):
    player_id: int
    fase_anterior: Any
    fase_nova: Any


@dataclass
class TurnStarted(Event):
    player_id: int
    numero_turno: int


@dataclass
class ManaChanged(Event):
    player_id: int
    delta: int
    total: int


@dataclass
class LifeChanged(Event):
    player_id: int
    delta: int
    total: int


@dataclass
class CardDrawn(Event):
    player_id: int
    card: int
    # "turno" = compra automática da Fase de Recurso, "efeito" = Encantamento/
    # Habilidade tipo Tomo do Oráculo — alguns gatilhos (Nevoeiro do Pânico,
    # Mente Fraturada) só disparam pra um dos dois casos (ver triggers.py).
    origem: str = "efeito"


@dataclass
class CardDiscarded(Event):
    player_id: int
    card: int


@dataclass
class CardMoved(Event):
    card: int
    zona_anterior: Any
    zona_nova: Any


@dataclass
class CardAboutToBeDestroyed(Event):
    """Publicado ANTES de `CardDestroyed`, com um `contexto` mutável — dá pra
    um gatilho (ex.: Valhalla) sobrescrever `contexto["destino"]` pra
    "panteao" antes de `DestructionSystem.destruir` decidir pra onde a carta
    vai, sem precisar de um caso especial só pra essa carta."""
    card: int
    motivo: str
    player_id: int | None
    contexto: dict


@dataclass
class CardDestroyed(Event):
    card: int
    motivo: str = ""


@dataclass
class CombatantSummoned(Event):
    player_id: int
    card: int


@dataclass
class AbilityActivated(Event):
    player_id: int
    card: int


@dataclass
class AttackDeclared(Event):
    atacante_player: int
    atacante_card: int
    defensor_player: int
    defensor_card: int | None


@dataclass
class AttackResolved(Event):
    """Publicado ao FIM de `CombatSystem.resolver_ataque` (com ou sem dano/
    destruição) — usado por gatilhos "logo após atacar" (Cânion dos Ventos)."""
    atacante_player: int
    atacante_card: int
    defensor_player: int
    defensor_card: int | None


@dataclass
class DamageDealt(Event):
    alvo: int | None       # entity id de um combatente, ou None se foi no jogador
    alvo_player: int | None
    quantidade: int
    origem: str = ""


@dataclass
class SelectionRequested(Event):
    """Publicado quando o motor precisa que um jogador escolha algo (qual
    carta invocar do Panteao, em qual slot de magia colocar, qual alvo de um
    efeito, etc.). A GUI (ou um bot/CLI) assina esse evento, mostra as
    `opcoes` pro `player_id` e devolve a escolha via
    `GameController.resolve_selection(...)`."""
    request_id: int
    player_id: int
    prompt: str
    opcoes: list[int]           # entity ids validos pra essa escolha
    minimo: int = 1
    maximo: int = 1


@dataclass
class SelectionMade(Event):
    request_id: int
    player_id: int
    escolha: list[int]


@dataclass
class DomainActivated(Event):
    player_id: int
    card: int
    dominio_substituido: int | None = None


@dataclass
class EnchantmentPlayed(Event):
    player_id: int
    card: int


@dataclass
class CursePlaced(Event):
    player_id: int
    card: int
    slot: int


@dataclass
class CurseTriggered(Event):
    player_id: int
    card: int


@dataclass
class DeckShuffled(Event):
    deck_nome: str


@dataclass
class GameOver(Event):
    perdedor_player: int
    motivo: str


# ---------------------------------------------------------------------------
# Barramento
# ---------------------------------------------------------------------------

class EventBus:
    def __init__(self) -> None:
        self._listeners: DefaultDict[type, list[Callable[[Event], None]]] = defaultdict(list)
        self.historico: list[Event] = []
        self.ctrl = None  # ligado pelo GameController — ver disparar_triggers abaixo

    def subscribe(self, event_type: type, callback: Callable[[Event], None]) -> None:
        self._listeners[event_type].append(callback)

    def unsubscribe(self, event_type: type, callback: Callable[[Event], None]) -> None:
        if callback in self._listeners.get(event_type, []):
            self._listeners[event_type].remove(callback)

    def publish(self, event: Event) -> None:
        self.historico.append(event)
        for callback in self._listeners.get(type(event), []):
            callback(event)
        # A "pilha de eventos" é o próprio `historico` acima; a cada evento
        # publicado, roda a lista de gatilhos registrados (ver triggers.py)
        # pra ver se algum bate com este tipo de evento. Import tardio pra
        # evitar import circular (triggers.py não precisa de events.py).
        if self.ctrl is not None:
            from .triggers import disparar_triggers
            disparar_triggers(self.ctrl, event)
