# -*- coding: utf-8 -*-
"""Pilha de gatilhos + efeitos passivos — espelha webgame/triggers.js.

Gatilhos: uma carta em campo (Domínio, Maldição revelada) pode registrar um
gatilho que fica esperando um EVENTO futuro em vez de mudar o estado na hora
(`registrar_trigger`). Toda vez que QUALQUER evento é publicado no EventBus
(ver events.py — `EventBus.publish` chama `disparar_triggers` logo depois de
empilhar no historico), roda a lista de gatilhos pra ver se algum bate com o
TIPO do evento e, se a condição aceitar, dispara o efeito. É o único lugar
onde "Quando X"/"Sempre que X" são resolvidos — nada bespoke espalhado.

Passivos: um Domínio "enquanto ativo" registra um efeito PASSIVO
(`registrar_passivo`), reaplicado do zero — limpa e reaplica — a cada Fase
Principal de QUALQUER jogador (`aplicar_passivos`, chamado por
`GameController.avancar_fase`), e removido (com limpeza) assim que a
carta-fonte sai de campo, pelo único ponto de destruição
(`DestructionSystem.destruir`).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .components import StatusEffects
from .phases import _recalcular_stats


@dataclass
class Trigger:
    evento_tipo: type
    efeito: Callable[[Any, "GameController"], None]
    origem_card: int | None = None
    owner_player_id: int | None = None
    condicao: Callable[[Any, "GameController"], bool] = lambda evento, ctrl: True
    persistente: bool = True


@dataclass
class Passivo:
    player_id: int
    card: int
    aplicar: Callable[["GameController", int, int], None]
    limpar: Callable[["GameController", int], None]


def registrar_trigger(ctrl, evento_tipo: type, efeito: Callable, *,
                       origem_card: int | None = None, owner_player_id: int | None = None,
                       condicao: Callable = lambda evento, ctrl: True, persistente: bool = True) -> Trigger:
    t = Trigger(evento_tipo=evento_tipo, efeito=efeito, origem_card=origem_card,
                owner_player_id=owner_player_id, condicao=condicao, persistente=persistente)
    ctrl.triggers.append(t)
    return t


def remover_triggers_de(ctrl, origem_card: int) -> None:
    ctrl.triggers = [t for t in ctrl.triggers if t.origem_card != origem_card]


def disparar_triggers(ctrl, evento) -> None:
    candidatos = [t for t in ctrl.triggers if t.evento_tipo is type(evento)]
    for t in candidatos:
        if t not in ctrl.triggers:
            continue  # pode ter sido removido por um trigger anterior neste mesmo lote
        if t.condicao(evento, ctrl):
            t.efeito(evento, ctrl)
            if not t.persistente:
                ctrl.triggers = [x for x in ctrl.triggers if x is not t]


def limpar_status_por_origem(ctrl, origem: str) -> None:
    """Percorre os dois lados e remove todo StatusEffect com essa `origem`
    (nome da carta-fonte), recalculando stats de quem foi afetado — usado
    tanto pra limpar um passivo removido quanto como o "limpar" padrão antes
    de reaplicar (ver `aplicar_passivos`)."""
    for pid in ctrl.jogadores:
        carta = ctrl.board.lado(pid).monstro
        if carta is None:
            continue
        statuses = ctrl.world.get_component(carta, StatusEffects)
        if statuses is None:
            continue
        antes = len(statuses.itens)
        statuses.itens = [s for s in statuses.itens if s.origem != origem]
        if len(statuses.itens) != antes:
            _recalcular_stats(ctrl.world, carta)


def registrar_passivo(ctrl, player_id: int, card: int, aplicar: Callable, limpar: Callable | None = None) -> None:
    limpar = limpar or (lambda ctrl, card: limpar_status_por_origem(ctrl, ctrl.nome_da_carta(card)))
    ctrl.passivos.append(Passivo(player_id=player_id, card=card, aplicar=aplicar, limpar=limpar))


def remover_passivos_de(ctrl, card: int) -> None:
    restantes = []
    for p in ctrl.passivos:
        if p.card == card:
            p.limpar(ctrl, card)
        else:
            restantes.append(p)
    ctrl.passivos = restantes


def aplicar_passivos(ctrl) -> None:
    for p in ctrl.passivos:
        p.limpar(ctrl, p.card)
        p.aplicar(ctrl, p.player_id, p.card)
