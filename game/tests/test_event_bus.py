# -*- coding: utf-8 -*-
"""EventBus.subscribe_all — a peça que faltava pra um servidor de rede
poder "ouvir tudo" e transmitir cada evento aos clientes, espelhando
webgame/events.js's onQualquer (usado hoje por webgame/rede.js)."""
from __future__ import annotations

from game.actions import SummonAction
from game.controller import GameController
from game.events import PhaseChanged


def test_subscribe_all_recebe_todo_evento_na_ordem_do_historico():
    ctrl = GameController(seed=42)
    recebidos = []
    ctrl.bus.subscribe_all(lambda e: recebidos.append(e))

    ctrl.iniciar_jogo()
    ctrl.avancar_fase()  # SAQUE -> INVOCACAO
    escolhido = ctrl.panteoes[1].restantes()[0]
    ctrl.players[1].mana = 20
    ctrl.submeter_acao(SummonAction(player_id=1, card=escolhido))

    assert len(recebidos) > 0
    # subscribe_all viu exatamente os mesmos eventos, na mesma ordem, que o
    # historico interno do bus (a "pilha de eventos" oficial).
    assert recebidos == ctrl.bus.historico


def test_subscribe_all_nao_impede_ouvintes_especificos():
    ctrl = GameController(seed=42)
    especificos = []
    globais = []
    ctrl.bus.subscribe(PhaseChanged, lambda e: especificos.append(e))
    ctrl.bus.subscribe_all(lambda e: globais.append(e))

    ctrl.iniciar_jogo()
    ctrl.avancar_fase()

    assert len(especificos) >= 1
    assert all(isinstance(e, PhaseChanged) for e in especificos)
    # o ouvinte global viu TODOS os tipos, não só PhaseChanged.
    assert len(globais) >= len(especificos)
    assert any(isinstance(e, PhaseChanged) for e in globais)


def test_unsubscribe_all_para_de_receber():
    ctrl = GameController(seed=42)
    recebidos = []
    callback = lambda e: recebidos.append(e)
    ctrl.bus.subscribe_all(callback)

    ctrl.iniciar_jogo()
    quantidade_apos_iniciar = len(recebidos)
    assert quantidade_apos_iniciar > 0

    ctrl.bus.unsubscribe_all(callback)
    ctrl.avancar_fase()
    assert len(recebidos) == quantidade_apos_iniciar


def test_multiplos_ouvintes_globais_recebem_independentemente():
    ctrl = GameController(seed=42)
    a, b = [], []
    ctrl.bus.subscribe_all(lambda e: a.append(e))
    ctrl.bus.subscribe_all(lambda e: b.append(e))

    ctrl.iniciar_jogo()

    assert len(a) == len(b) == len(ctrl.bus.historico)
