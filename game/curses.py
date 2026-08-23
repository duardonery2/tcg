# -*- coding: utf-8 -*-
"""Oferece, no momento certo, a decisão de ativar uma Maldição virada para
baixo em reação a um evento específico — espelha webgame/curses.js.

GAME_DESIGN.md: "Revelar/ativar uma Maldição já setada: a qualquer momento
no turno do OPONENTE." O jogo nunca revela uma Maldição sozinho: sempre que
um evento bate com o gatilho declarado (EFFECTS.registrar_gatilho_maldicao,
game/effects.py) de alguma Maldição virada pra baixo de quem NÃO está na
vez, um pedido de seleção pergunta pro dono se quer ativá-la agora — o motor
espera essa decisão (mesmo mecanismo de `ctrl.solicitar_selecao` de sempre)
antes de continuar."""
from __future__ import annotations

from typing import Callable

from .components import CardInfo, FaceDown, ManaCost


def maldicoes_elegiveis(ctrl, evento) -> list[tuple[int, int]]:
    """Devolve [(dono_id, card), ...] entre as Maldições viradas pra baixo de
    quem NÃO está na vez, com um gatilho declarado batendo com o TIPO do
    evento, cuja condição aceita, e que o dono ainda tem mana pra pagar."""
    elegiveis: list[tuple[int, int]] = []
    ts = ctrl.fase_atual()
    for pid in ctrl.jogadores:
        if pid == ts.jogador_da_vez:
            continue  # só quem NÃO está na vez pode reagir
        lado = ctrl.board.lado(pid)
        for card in lado.magia:
            if card is None or not ctrl.world.has_component(card, FaceDown):
                continue
            custo = ctrl.world.get_component(card, ManaCost).valor
            if custo > ctrl.players[pid].mana:
                continue
            info = ctrl.world.get_component(card, CardInfo)
            gatilho = ctrl.effects.gatilho_maldicao(info.nome)
            if gatilho is None:
                continue
            evento_tipo, condicao = gatilho
            if evento_tipo is not type(evento):
                continue
            if condicao(evento, ctrl, pid):
                elegiveis.append((pid, card))
    return elegiveis


def ofertar_maldicoes_reativas(ctrl, evento, continuar: Callable[[], None] = lambda: None) -> None:
    """Pausa o fluxo — mesmo `ctrl.solicitar_selecao` de sempre — até que
    cada dono elegível decida ativar uma Maldição (ou nenhuma). `continuar`
    só roda depois de TODAS as decisões resolvidas (na prática, quase
    sempre um único dono)."""
    from .actions import AcaoInvalida, ActivateSetCurseAction  # import tardio: evita ciclo com actions.py

    elegiveis = maldicoes_elegiveis(ctrl, evento)
    donos = list(dict.fromkeys(pid for pid, _ in elegiveis))

    def processar(i: int) -> None:
        if i >= len(donos):
            continuar()
            return
        dono_id = donos[i]
        lado = ctrl.board.lado(dono_id)
        cartas = [c for pid, c in elegiveis
                  if pid == dono_id and c in lado.magia and ctrl.world.has_component(c, FaceDown)]
        if not cartas:
            processar(i + 1)
            return

        def _ao_escolher(escolha: list[int]) -> None:
            if escolha:
                try:
                    ActivateSetCurseAction(player_id=dono_id, card=escolha[0], evento=evento).executar(ctrl)
                except AcaoInvalida:
                    pass  # defensivo: estado pode ter mudado entre a oferta e a escolha
            processar(i + 1)

        ctrl.solicitar_selecao(
            player_id=dono_id,
            prompt="Uma Maldição virada para baixo pode ser ativada agora. Ativar uma delas?",
            opcoes=cartas,
            on_resolved=_ao_escolher,
            minimo=0, maximo=1,
        )

    processar(0)
