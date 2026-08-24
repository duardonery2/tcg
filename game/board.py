# -*- coding: utf-8 -*-
"""O tabuleiro: por jogador, 1 slot de Monstro (o combatente ativo) e 5 slots
de Magia (Dominio ativo + Maldicoes setadas ocupam slots de magia)."""
from __future__ import annotations

from dataclasses import dataclass, field

N_SLOTS_MAGIA = 5


class SlotOcupadoError(RuntimeError):
    pass


class SlotVazioError(RuntimeError):
    pass


@dataclass
class BoardSide:
    player_id: int
    monstro: int | None = None
    magia: list[int | None] = field(default_factory=lambda: [None] * N_SLOTS_MAGIA)

    def slots_livres(self) -> list[int]:
        return [i for i, v in enumerate(self.magia) if v is None]

    def colocar_monstro(self, card: int) -> None:
        if self.monstro is not None:
            raise SlotOcupadoError("Ja existe um combatente ativo neste lado do tabuleiro.")
        self.monstro = card

    def remover_monstro(self) -> int | None:
        card, self.monstro = self.monstro, None
        return card

    def colocar_magia(self, card: int, slot: int | None = None) -> int:
        if slot is None:
            livres = self.slots_livres()
            if not livres:
                raise SlotOcupadoError("Nao ha slot de magia livre (limite de 5).")
            slot = livres[0]
        elif self.magia[slot] is not None:
            raise SlotOcupadoError(f"Slot de magia {slot} ja ocupado.")
        self.magia[slot] = card
        return slot

    def remover_magia(self, card: int) -> int:
        for i, v in enumerate(self.magia):
            if v == card:
                self.magia[i] = None
                return i
        raise SlotVazioError(f"{card} nao esta em nenhum slot de magia deste lado.")

    def dominio_ativo(self, world, dominio_cards: set[int]) -> int | None:
        """Ajuda a achar qual carta nos slots de magia e o Domínio ativo
        (so pode haver 1 por vez, GAME_DESIGN.md — Fase Principal)."""
        for v in self.magia:
            if v is not None and v in dominio_cards:
                return v
        return None


@dataclass
class Board:
    lados: dict[int, BoardSide] = field(default_factory=dict)

    def lado(self, player_id: int) -> BoardSide:
        if player_id not in self.lados:
            self.lados[player_id] = BoardSide(player_id=player_id)
        return self.lados[player_id]
