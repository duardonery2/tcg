# -*- coding: utf-8 -*-
"""Deck: um baralho generico que sorteia aleatoriamente 1 carta ainda nao
comprada da sua lista. O Panteao (Pantheon) e um Deck separado — mesma
interface, lista diferente (so os 5 Combatentes do jogador).

Escolha de design: `draw_random()` e o mecanismo de COMPRA automatica do
Baralho Arcano (Fase de Saque). Invocar um combatente especifico do
Panteao, por outro lado, e uma ESCOLHA do jogador — isso passa pelo sistema
de selecao (events.SelectionRequested), nao por `draw_random()`. O Panteao
ainda e um Deck (mesma classe) porque semanticamente e "uma lista da qual se
tira uma carta ainda nao tirada"; so a forma de tirar (aleatoria vs.
escolhida) muda por acao de jogo, nao por classe.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field


class DeckEmptyError(RuntimeError):
    pass


class CardNotInDeckError(RuntimeError):
    pass


@dataclass
class Deck:
    nome: str
    cartas: list[int] = field(default_factory=list)     # todas as entidades pertencentes a este deck
    compradas: set[int] = field(default_factory=set)     # ja tiradas (nao voltam sozinhas)

    def restantes(self) -> list[int]:
        return [c for c in self.cartas if c not in self.compradas]

    def esta_vazio(self) -> bool:
        return len(self.restantes()) == 0

    def draw_random(self, rng: random.Random | None = None) -> int:
        """Sorteia aleatoriamente 1 card ainda nao comprado. Levanta
        DeckEmptyError se nao sobrar nenhum."""
        rng = rng or random
        opcoes = self.restantes()
        if not opcoes:
            raise DeckEmptyError(f"O deck '{self.nome}' esta vazio.")
        carta = rng.choice(opcoes)
        self.compradas.add(carta)
        return carta

    def tirar_especifica(self, card: int) -> int:
        """Retira uma carta especifica (usado quando quem escolhe e o
        jogador, ex.: invocar um Combatente certo do Panteao)."""
        if card not in self.cartas:
            raise CardNotInDeckError(f"{card} nao pertence ao deck '{self.nome}'.")
        if card in self.compradas:
            raise CardNotInDeckError(f"{card} ja foi retirada de '{self.nome}'.")
        self.compradas.add(card)
        return card

    def devolver(self, card: int) -> None:
        """Desfaz uma compra: a carta volta a contar como 'nao comprada'
        (ex.: Tífon/Vórtice Dimensional devolvem um combatente pro Panteão)."""
        self.compradas.discard(card)

    def adicionar(self, card: int) -> None:
        """Bota uma carta nova nesse deck (ex.: Ressurreicao Arcana devolve
        uma carta da Pilha de Descarte pra mao, nao pro deck — mas Troca
        Equivalente embaralha cartas da mao DE VOLTA pro Baralho Arcano)."""
        if card not in self.cartas:
            self.cartas.append(card)
        self.compradas.discard(card)

    def embaralhar(self, rng: random.Random | None = None) -> None:
        """Acao de embaralhar: reordena a lista interna. Como a compra e por
        sorteio uniforme entre as restantes, embaralhar nao muda a
        PROBABILIDADE de compra — mas e a acao de jogo formal (ex.: depois de
        devolver cartas ao baralho com Troca Equivalente) e mantem a ordem
        interna sem vies para qualquer futuro mecanismo posicional
        (ex.: 'olhe as 3 do topo')."""
        rng = rng or random
        restantes = self.restantes()
        rng.shuffle(restantes)
        compradas_ordem = [c for c in self.cartas if c in self.compradas]
        self.cartas = compradas_ordem + restantes

    def topo(self, n: int = 1) -> list[int]:
        """Espia as `n` cartas do topo sem tirar (Merlin: Clarividencia,
        Nyarlathotep: Caos, etc.). Convencao: o "topo" e o inicio da lista
        de restantes, que `embaralhar()` mistura."""
        return self.restantes()[:n]


def novo_deck_arcano(nome: str, cartas: list[int]) -> Deck:
    return Deck(nome=nome, cartas=list(cartas))


def novo_panteao(nome: str, combatentes: list[int]) -> Deck:
    assert len(combatentes) == 5, "O Panteao precisa de exatamente 5 Combatentes (GAME_DESIGN.md)."
    return Deck(nome=nome, cartas=list(combatentes))
