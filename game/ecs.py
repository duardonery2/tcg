# -*- coding: utf-8 -*-
"""Micro-framework ECS (Entity-Component-System).

- Entity  : so um inteiro (id). Nao carrega dado nem comportamento.
- Component: dataclass "burra", so dado (ex.: CombatStats, Owner, Zone).
- System  : classe com `update(world, **ctx)`, contem a LOGICA que le/escreve
            componentes. O `World` roda os systems na ordem em que foram
            registrados a cada `world.tick()`.

Isso separa "o que uma carta E" (componentes) de "o que acontece no jogo"
(systems), o que e exatamente o que a secao "Vocabulario de Mecanicas" de
GAME_DESIGN.md pede: Acoes do Jogador e Gatilhos de Evento viram Systems que
leem/escrevem Componentes, nunca metodos dentro de uma classe "Carta".
"""
from __future__ import annotations

from typing import Any, Iterator, Type, TypeVar

C = TypeVar("C")

Entity = int


class World:
    """Guarda todas as entidades e seus componentes, e roda os Systems."""

    def __init__(self) -> None:
        self._next_id: Entity = 1
        self._entities: set[Entity] = set()
        # tipo do componente -> {entity: instancia}
        self._components: dict[Type, dict[Entity, Any]] = {}
        self._systems: list["System"] = []

    # ---- entidades ---------------------------------------------------

    def create_entity(self) -> Entity:
        eid = self._next_id
        self._next_id += 1
        self._entities.add(eid)
        return eid

    def destroy_entity(self, entity: Entity) -> None:
        self._entities.discard(entity)
        for store in self._components.values():
            store.pop(entity, None)

    def entities(self) -> Iterator[Entity]:
        return iter(self._entities)

    # ---- componentes ---------------------------------------------------

    def add_component(self, entity: Entity, component: C) -> C:
        store = self._components.setdefault(type(component), {})
        store[entity] = component
        return component

    def get_component(self, entity: Entity, ctype: Type[C]) -> C | None:
        return self._components.get(ctype, {}).get(entity)

    def has_component(self, entity: Entity, ctype: Type) -> bool:
        return entity in self._components.get(ctype, {})

    def remove_component(self, entity: Entity, ctype: Type) -> None:
        self._components.get(ctype, {}).pop(entity, None)

    def query(self, *ctypes: Type) -> Iterator[tuple[Entity, ...]]:
        """Itera entidades que possuem TODOS os tipos de componente pedidos,
        devolvendo (entity, comp1, comp2, ...) na mesma ordem de `ctypes`."""
        if not ctypes:
            return
        base = self._components.get(ctypes[0], {})
        for entity in list(base.keys()):
            comps = []
            ok = True
            for ct in ctypes:
                c = self._components.get(ct, {}).get(entity)
                if c is None:
                    ok = False
                    break
                comps.append(c)
            if ok:
                yield (entity, *comps)

    def single(self, *ctypes: Type) -> tuple[Entity, ...] | None:
        for row in self.query(*ctypes):
            return row
        return None

    # ---- systems ---------------------------------------------------

    def add_system(self, system: "System") -> None:
        self._systems.append(system)

    def tick(self, **ctx) -> None:
        for system in self._systems:
            system.update(self, **ctx)


class System:
    """Classe-base de um System. Sobrescreva `update`."""

    def update(self, world: World, **ctx) -> None:  # pragma: no cover - interface
        raise NotImplementedError
