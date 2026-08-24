# -*- coding: utf-8 -*-
"""GameController: a API basica de estado de jogo. E o UNICO objeto que a
GUI (ou um bot, ou um script de teste) precisa conhecer — ele amarra World,
Board, Decks, Panteões, PhaseSystem, SelectionManager e EventBus.

Uso tipico:
    ctrl = GameController()
    ctrl.iniciar_jogo()
    ctrl.submeter_acao(SummonAction(player_id=1, card=algum_id))
    ctrl.avancar_fase()
    estado = ctrl.estado()
"""
from __future__ import annotations

import random

from .board import Board
from .components import CardInfo, Fase, PlayerState
from .deck import novo_deck_arcano, novo_panteao
from .ecs import World
from .effects import EFFECTS, comprar
from .events import EventBus, GameOver
from .loader import DEFAULT_CSV_PATH, carregar_csv_para_jogador
from .phases import PhaseSystem, UpkeepSystem
from .selection import SelectionManager
from .systems import CombatSystem, DestructionSystem, ResourceSystem

MAO_INICIAL = 4


class GameController:
    def __init__(self, csv_path: str = DEFAULT_CSV_PATH, jogadores: tuple[int, int] = (1, 2),
                 nomes: tuple[str, str] = ("Feiticeiro 1", "Feiticeiro 2"), seed: int | None = None):
        self.world = World()
        self.bus = EventBus()
        self.bus.ctrl = self  # ver EventBus.publish (events.py) -- dispara os gatilhos registrados a cada evento
        self.rng = random.Random(seed)
        self.jogadores = list(jogadores)

        self.players: dict[int, PlayerState] = {
            pid: PlayerState(player_id=pid, nome=nome) for pid, nome in zip(jogadores, nomes)
        }
        self.board = Board()
        self.baralhos = {}
        self.panteoes = {}
        self.dominio_cards: set[int] = set()
        self._owner_map: dict[int, int] = {}
        self.triggers: list = []  # ver triggers.py
        self.passivos: list = []  # ver triggers.py

        for pid in self.jogadores:
            panteao_ids, baralho_ids = carregar_csv_para_jogador(
                self.world, csv_path, pid, self.dominio_cards, self._owner_map, self.rng
            )
            self.panteoes[pid] = novo_panteao(f"Panteão de {self.players[pid].nome}", panteao_ids)
            self.baralhos[pid] = novo_deck_arcano(f"Baralho Arcano de {self.players[pid].nome}", baralho_ids)

        self.selection = SelectionManager(self.bus)
        self.effects = EFFECTS
        self.effects.ligar_gatilhos(self)

        self.fase_system = PhaseSystem(self.bus, self.jogadores)
        self.upkeep_system = UpkeepSystem(self.bus)
        self.resource_system = ResourceSystem(self.bus, self.baralhos, self.players)
        self.destruction_system = DestructionSystem(self.bus, self.board, self.dono_da_carta, self)
        self.combat_system = CombatSystem(self.bus, self.players, self.destruction_system, self)

        self.world.add_system(self.fase_system)
        self.world.add_system(self.upkeep_system)
        self.world.add_system(self.resource_system)

        self._iniciado = False
        self._fim_de_jogo: GameOver | None = None
        self.bus.subscribe(GameOver, self._on_game_over)

    # ---- ciclo de vida ---------------------------------------------------

    def iniciar_jogo(self) -> None:
        """Compra a mao inicial de 4 e liga o relogio (turno 1, Fase de
        Recurso do primeiro jogador). Chame uma vez, antes de qualquer acao."""
        if self._iniciado:
            return
        for pid in self.jogadores:
            comprar(self, pid, MAO_INICIAL)
        self.world.tick()  # cria a TurnState singleton e publica o 1o TurnStarted
        self._iniciado = True

    def dono_da_carta(self, card: int) -> int | None:
        return self._owner_map.get(card)

    def oponente_de(self, player_id: int) -> int:
        return next(p for p in self.jogadores if p != player_id)

    # ---- acoes / fases ---------------------------------------------------

    def submeter_acao(self, acao) -> None:
        """Ponto unico de entrada pra qualquer Acao do Jogador (game/actions.py)."""
        acao.executar(self)
        self._checar_fim_de_jogo()

    def avancar_fase(self):
        ts = self.fase_system.avancar(self.world)
        if ts.fase is Fase.PRINCIPAL:
            from .triggers import aplicar_passivos
            aplicar_passivos(self)
        self._checar_fim_de_jogo()
        return ts

    def fase_atual(self):
        return self.fase_system.estado_atual(self.world)

    # ---- selecao -----------------------------------------------------

    def solicitar_selecao(self, player_id, prompt, opcoes, on_resolved, minimo=1, maximo=1) -> int:
        return self.selection.solicitar(player_id, prompt, opcoes, on_resolved, minimo, maximo)

    def resolver_selecao(self, request_id: int, escolha: list[int]) -> None:
        self.selection.resolver(request_id, escolha)
        self._checar_fim_de_jogo()

    # ---- fim de jogo -----------------------------------------------------

    def _checar_fim_de_jogo(self) -> None:
        if self._fim_de_jogo is not None:
            return
        for pid in self.jogadores:
            ps = self.players[pid]
            if ps.vida <= 0:
                self.bus.publish(GameOver(perdedor_player=pid, motivo="Pontos de Vida chegaram a 0"))
                return
            ts = self.fase_atual()
            sem_combatentes = self.board.lado(pid).monstro is None and self.panteoes[pid].esta_vazio()
            if sem_combatentes and ts.jogador_da_vez == pid and ts.fase.name == "INVOCACAO":
                self.bus.publish(GameOver(perdedor_player=pid, motivo="sem combatentes para invocar"))
                return

    def _on_game_over(self, event: GameOver) -> None:
        self._fim_de_jogo = event

    def fim_de_jogo(self) -> GameOver | None:
        return self._fim_de_jogo

    # ---- snapshot pra GUI/depuracao ---------------------------------------

    def nome_da_carta(self, card: int) -> str:
        info = self.world.get_component(card, CardInfo)
        return info.nome if info else f"<entidade {card}>"

    def estado(self) -> dict:
        ts = self.fase_atual()
        return {
            "turno": ts.numero_turno,
            "jogador_da_vez": ts.jogador_da_vez,
            "fase": ts.fase.name,
            "jogadores": {
                pid: {
                    "nome": ps.nome, "mana": ps.mana, "vida": ps.vida,
                    "mao": [self.nome_da_carta(c) for c in ps.mao],
                }
                for pid, ps in self.players.items()
            },
            "tabuleiro": {
                pid: {
                    "monstro": self.nome_da_carta(lado.monstro) if lado.monstro else None,
                    "magia": [self.nome_da_carta(c) if c else None for c in lado.magia],
                }
                for pid, lado in self.board.lados.items()
            },
            "fim_de_jogo": (self._fim_de_jogo.motivo if self._fim_de_jogo else None),
        }
