# -*- coding: utf-8 -*-
"""Mecanismo de selecao: quando o motor precisa que um jogador escolha algo
(carta do Panteao pra invocar, slot de magia, alvo de efeito...), ele NAO
bloqueia esperando input — ele publica `SelectionRequested` pelo EventBus e
guarda um callback pendente. Quem estiver ouvindo (a GUI, um bot, um script
de teste) devolve a escolha chamando `resolve()`, o que publica
`SelectionMade` e dispara o callback.

Isso e o que permite o mesmo motor rodar tanto numa GUI interativa (o
callback so roda quando o jogador clica) quanto numa simulacao automatica de
testes (resolve() e chamado na hora, sincrono)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .events import EventBus, SelectionMade, SelectionRequested


@dataclass
class _Pending:
    player_id: int
    minimo: int
    maximo: int
    opcoes: list[int]
    on_resolved: Callable[[list[int]], None]


class SelectionManager:
    def __init__(self, bus: EventBus):
        self.bus = bus
        self._next_id = 1
        self._pendentes: dict[int, _Pending] = {}

    def solicitar(
        self,
        player_id: int,
        prompt: str,
        opcoes: list[int],
        on_resolved: Callable[[list[int]], None],
        minimo: int = 1,
        maximo: int = 1,
    ) -> int:
        """Pede uma escolha ao jogador. Devolve o request_id (util pra GUI
        casar o clique certo com o pedido certo)."""
        request_id = self._next_id
        self._next_id += 1
        self._pendentes[request_id] = _Pending(player_id, minimo, maximo, list(opcoes), on_resolved)
        self.bus.publish(SelectionRequested(
            request_id=request_id, player_id=player_id, prompt=prompt,
            opcoes=list(opcoes), minimo=minimo, maximo=maximo,
        ))
        return request_id

    def pendente(self, request_id: int) -> bool:
        return request_id in self._pendentes

    def resolver(self, request_id: int, escolha: list[int]) -> None:
        pend = self._pendentes.pop(request_id, None)
        if pend is None:
            raise KeyError(f"Nao ha selecao pendente com id {request_id}.")
        for c in escolha:
            if c not in pend.opcoes:
                raise ValueError(f"{c} nao e uma opcao valida para a selecao {request_id}.")
        if not (pend.minimo <= len(escolha) <= pend.maximo):
            raise ValueError(
                f"Selecao {request_id} exige entre {pend.minimo} e {pend.maximo} escolhas, recebi {len(escolha)}."
            )
        self.bus.publish(SelectionMade(request_id=request_id, player_id=pend.player_id, escolha=escolha))
        pend.on_resolved(escolha)
