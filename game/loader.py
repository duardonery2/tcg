# -*- coding: utf-8 -*-
"""Carrega o CSV do projeto (a mesma fonte de verdade usada por
scripts/renderizar_cartas.py) e cria as entidades ECS.

Decisao de design: o CSV e uma lista de 60 CARTAS UNICAS (um "pool"), nao uma
lista de copias de um deck construido. Pra um duelo de 2 jogadores, cada
jogador recebe seu PROPRIO conjunto de entidades a partir do mesmo pool
(mao espelhada) — assim cada carta em campo pertence sem ambiguidade a um
unico jogador, sem precisar inventar uma regra de deck-building que
GAME_DESIGN.md nao especifica.
"""
from __future__ import annotations

import os
import random

import pandas as pd

from .components import (
    AbilityCost, CardInfo, Combatente, CombatStats, Elemento, Location,
    ManaCost, Owner, Tipo, Zona,
)
from .ecs import World

DEFAULT_CSV_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "Cartas do Jogo de Duelo de Feiticeiros - Cartas do Jogo de Duelo de Feiticeiros.csv",
)

_TIPO_MAP = {
    "Herói": Tipo.HEROI,
    "Monstro": Tipo.MONSTRO,
    "Domínio": Tipo.DOMINIO,
    "Encantamento": Tipo.ENCANTAMENTO,
    "Maldição": Tipo.MALDICAO,
}

_ELEMENTO_MAP = {
    "Fogo": Elemento.FOGO,
    "Água": Elemento.AGUA,
    "Terra": Elemento.TERRA,
    "Vento": Elemento.VENTO,
    "-": Elemento.NENHUM,
}

COMBATENTES = {Tipo.HEROI, Tipo.MONSTRO}


PANTEAO_TAMANHO = 5


def carregar_csv_para_jogador(
    world: World, csv_path: str, player_id: int,
    dominio_cards: set[int], owner_map: dict[int, int],
    rng: random.Random | None = None,
) -> tuple[list[int], list[int]]:
    """Cria as entidades desse jogador a partir do CSV (Owner(player_id)).
    O CSV e um POOL de 60 cartas unicas, nao uma lista de decks prontos —
    cada jogador recebe copias proprias (mao espelhada) de todo o Baralho
    Arcano (Domínio/Encantamento/Maldição, 40 cartas), mas o Panteão exige
    EXATAMENTE 5 Combatentes (GAME_DESIGN.md), entao sorteamos 5 dos 20
    Heróis/Monstros do pool pra esse jogador — cada jogador sorteia o seu,
    entao os dois lados normalmente saem com Panteões diferentes.

    Devolve (ids_do_panteao, ids_do_baralho_arcano)."""
    rng = rng or random
    df = pd.read_csv(csv_path)
    panteao_ids: list[int] = []
    baralho_ids: list[int] = []

    combatente_rows = [row for _, row in df.iterrows() if row["Tipo"] in ("Herói", "Monstro")]
    apoio_rows = [row for _, row in df.iterrows() if row["Tipo"] not in ("Herói", "Monstro")]
    sorteados = rng.sample(combatente_rows, PANTEAO_TAMANHO)

    for row in sorteados + apoio_rows:
        tipo = _TIPO_MAP[row["Tipo"]]
        elemento = _ELEMENTO_MAP.get(row["Elemento"], Elemento.NENHUM)  # elementos compostos (ex. "Fogo/Vento") caem em NENHUM

        eid = world.create_entity()
        world.add_component(eid, CardInfo(nome=row["Nome"], tipo=tipo, elemento=elemento,
                                           efeito_texto=row["Efeito / Habilidade"]))
        world.add_component(eid, ManaCost(valor=int(row["Custo de Mana"])))
        world.add_component(eid, Owner(player_id=player_id))
        owner_map[eid] = player_id

        if tipo in COMBATENTES:
            world.add_component(eid, Combatente())
            world.add_component(eid, CombatStats(base_pow=int(row["Combate"]), base_res=int(row["Resistência"])))
            custo_hab = row.get("Custo de Habilidade")
            if pd.notna(custo_hab):
                world.add_component(eid, AbilityCost(valor=int(custo_hab)))
            world.add_component(eid, Location(zona=Zona.PANTEAO))
            panteao_ids.append(eid)
        else:
            if tipo is Tipo.DOMINIO:
                dominio_cards.add(eid)
            world.add_component(eid, Location(zona=Zona.BARALHO_ARCANO))
            baralho_ids.append(eid)

    return panteao_ids, baralho_ids
