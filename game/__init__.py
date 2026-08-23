# -*- coding: utf-8 -*-
"""Motor do Duelo dos Feiticeiros — ECS puro em Python.

Modulos:
    ecs         - Entity/Component/System, o framework generico.
    components  - os componentes do jogo (dado puro).
    events      - EventBus + eventos (a "notificacao").
    deck        - Deck (compra aleatoria) — o Panteão e um Deck tambem.
    board       - tabuleiro: 1 slot de Monstro + 5 de Magia por jogador.
    selection   - mecanismo de selecao (pede escolha, resolve depois).
    phases      - troca de fase do turno.
    systems     - regras gerais (recurso, combate, destruicao).
    actions     - Acoes do Jogador (Invocar, Atacar, Ativar Habilidade...).
    effects     - efeito de cada uma das 60 cartas.
    loader      - le o CSV do projeto e cria as entidades.
    controller  - GameController: a API publica.
    gui         - interface grafica em Pygame.
"""
from .controller import GameController

__all__ = ["GameController"]
