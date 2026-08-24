# -*- coding: utf-8 -*-
"""Componentes do jogo — puro dado, sem metodo com logica de regra.

Nomes seguem o vocabulario de GAME_DESIGN.md (Custo de Mana, Resistencia,
Combate, Elemento, Zona, etc.) para o codigo ficar rastreavel ate a regra
escrita em portugues.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto


# ---------------------------------------------------------------------------
# Enums de vocabulario do jogo
# ---------------------------------------------------------------------------

class Tipo(Enum):
    HEROI = "Herói"
    MONSTRO = "Monstro"
    DOMINIO = "Domínio"
    ENCANTAMENTO = "Encantamento"
    MALDICAO = "Maldição"


class Elemento(Enum):
    FOGO = "Fogo"
    AGUA = "Água"
    TERRA = "Terra"
    VENTO = "Vento"
    NENHUM = "-"


# Água > Fogo > Vento > Terra > Água (GAME_DESIGN.md, "Combate e Sistema Elemental")
VANTAGEM_ELEMENTAL = {
    Elemento.AGUA: Elemento.FOGO,
    Elemento.FOGO: Elemento.VENTO,
    Elemento.VENTO: Elemento.TERRA,
    Elemento.TERRA: Elemento.AGUA,
}


class Zona(Enum):
    BARALHO_ARCANO = auto()
    MAO = auto()
    PILHA_DESCARTE = auto()
    PANTEAO = auto()
    CAMPO_MONSTRO = auto()   # o unico slot de combatente ativo
    CAMPO_MAGIA = auto()     # um dos 5 slots de magia (Dominio / Maldicao setada)
    EXILADA = auto()


class Fase(Enum):
    SAQUE = auto()       # compra automatica (era "Recurso")
    INVOCACAO = auto()   # credita 2 de Mana + invocar um combatente do Panteão
    PRINCIPAL = auto()   # magias: Dominio/Encantamento/Maldicao (era "Tatica")
    BATALHA = auto()     # declarar ataque (era "Combate")
    FINAL = auto()       # limpeza de fim de turno: expira buffs "neste turno"


class Duracao(Enum):
    NESTE_TURNO = auto()          # expira no fim do turno de quem ativou
    ATE_FIM_DE_TURNO = auto()     # mesma janela, nomeada como nas cartas
    PERMANENTE = auto()
    ATE_PROXIMO_TURNO_PROPRIO = auto()


# ---------------------------------------------------------------------------
# Componentes de carta
# ---------------------------------------------------------------------------

@dataclass
class CardInfo:
    nome: str
    tipo: Tipo
    elemento: Elemento
    efeito_texto: str = ""


@dataclass
class ManaCost:
    valor: int


@dataclass
class AbilityCost:
    """Custo de Habilidade (losango) — so Herói/Monstro. Ver GAME_DESIGN.md,
    secao 'Habilidades dos Combatentes'."""
    valor: int
    usada_neste_turno: bool = False


@dataclass
class CombatStats:
    """Atributos de combate. `base_*` e o valor impresso na carta; `atual_*`
    e o que conta pra combate, depois de buffs/debuffs. O teto de 20 pontos
    (GAME_DESIGN.md) e so pro valor BASE impresso na carta — "só pode ser
    quebrado por feitiços" quer dizer exatamente que Habilidade, Encantamento
    ou Maldição PODEM levar o valor atual acima de 20 sem restrição nenhuma;
    so ha piso em 0 (nao da pra ficar negativo), aplicado em `_recalcular_stats`
    (game/phases.py)."""
    base_pow: int
    base_res: int
    atual_pow: int = 0
    atual_res: int = 0

    def __post_init__(self):
        if self.atual_pow == 0:
            self.atual_pow = self.base_pow
        if self.atual_res == 0:
            self.atual_res = self.base_res


@dataclass
class StatusEffect:
    """Um modificador temporario/permanente aplicado por um efeito de carta."""
    atributo: str          # "pow" | "res"
    magnitude: int         # pode ser negativo
    duracao: Duracao
    origem: str = ""        # nome da carta/efeito que aplicou, p/ debug e Fio do Destino Cortado


@dataclass
class StatusEffects:
    itens: list[StatusEffect] = field(default_factory=list)


@dataclass
class Owner:
    player_id: int


@dataclass
class Location:
    zona: Zona
    slot: int | None = None   # indice 0-4 quando zona == CAMPO_MAGIA


@dataclass
class FaceDown:
    """Maldicao setada virada pra baixo — so revela/ativa no turno do inimigo."""
    virada_para_baixo: bool = True


@dataclass
class ElementoOverride:
    """Transmutacao Elemental / Escudo de Gelo Absoluto mexem no elemento
    "efetivo" de um combatente sem mudar o CardInfo original."""
    elemento: Elemento
    duracao: Duracao


# ---------------------------------------------------------------------------
# Componentes de jogador
# ---------------------------------------------------------------------------

@dataclass
class PlayerState:
    player_id: int
    nome: str
    mana: int = 5
    vida: int = 20                 # Pontos de Vida do Feiticeiro (GAME_DESIGN.md)
    mao: list[int] = field(default_factory=list)     # entity ids
    limite_mao: int = 6


@dataclass
class Combatente:
    """Marca uma entidade-carta como Herói/Monstro (facilita queries)."""
    pass


# ---------------------------------------------------------------------------
# Estado de turno — vive numa entidade "singleton" (a unica com esse componente)
# ---------------------------------------------------------------------------

@dataclass
class AttackNegated:
    """Flag de 1 uso: o proximo ataque contra esta carta e anulado
    (Escudo de Gelo Absoluto, Barreira de Vento Cortante)."""
    pass


@dataclass
class DamageReflected:
    """Flag: enquanto presente, dano de ataque contra esta carta e
    redirecionado pro atacante em vez de reduzir a Resistencia dela
    (Espelho das Ilusões, Retribuição Kármica)."""
    pass


@dataclass
class NextCurseNullified:
    """Flag no JOGADOR: a proxima Maldição sofrida e ignorada (Odisseu)."""
    pass


@dataclass
class IgnoraFraquezaElemental:
    """Enquanto presente, esta carta nao sofre o bonus de dano de vantagem
    elemental contra ela (Shoggoth)."""
    duracao: Duracao = Duracao.ATE_FIM_DE_TURNO


@dataclass
class DanoDobradoContraMonstro:
    """Flag NESTE_TURNO no ATACANTE (Sigurd, "Matador de Feras: Dano em
    dobro contra Monstros"): ativar a Habilidade so prepara o buff — o dano
    dobrado só sai de verdade se esse combatente ATACAR um Monstro antes do
    fim do turno (CombatSystem.resolver). Removida incondicionalmente na
    entrada da Fase Final (UpkeepSystem), sem precisar de um campo de
    duracao proprio — sempre dura só até lá."""
    pass


@dataclass
class TurnState:
    jogador_da_vez: int
    fase: Fase = Fase.SAQUE
    numero_turno: int = 1
