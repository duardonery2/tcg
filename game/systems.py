# -*- coding: utf-8 -*-
"""Systems de regra geral (nao ligados a uma carta especifica):
- ResourceSystem: compra + mana na entrada da Fase de Saque (exceto o
  primeiro turno de cada jogador, que ja comeca com a Mana inicial).
- CombatSystem: resolve um ataque (vantagem elemental + POW vs RES).
- DestructionSystem: move uma carta pro destino certo e avisa geral.
"""
from __future__ import annotations

from .components import (
    AttackNegated, CardInfo, CombatStats, DamageReflected, DanoDobradoContraMonstro,
    Elemento, ElementoOverride, Fase, IgnoraFraquezaElemental, Location,
    PlayerState, Tipo, TurnState, VANTAGEM_ELEMENTAL, Zona,
)
from .deck import Deck, DeckEmptyError
from .ecs import System, World
from .events import (
    AttackDeclared, AttackResolved, CardAboutToBeDestroyed, CardDiscarded,
    CardDrawn, CardDestroyed, CardMoved, DamageDealt, EventBus, LifeChanged,
    ManaChanged, PhaseChanged,
)
from .phases import _recalcular_stats

MANA_POR_TURNO = 2


class ResourceSystem(System):
    """Fase de Saque: compra 1 carta do Baralho Arcano e credita 2 de Mana
    na reserva do jogador da vez — exceto no PRIMEIRO turno de cada
    jogador (eles já começam com MANA_INICIAL, sem bônus adicional nessa
    primeira vez). Com N jogadores em rodízio, os primeiros N números de
    turno correspondem exatamente ao primeiro turno de cada um."""

    def __init__(self, bus: EventBus, baralhos: dict[int, Deck], players: dict[int, PlayerState], ctrl=None):
        self.baralhos = baralhos
        self.players = players
        self.ctrl = ctrl  # ver Encantamentos Contínuos (game/effects.py) -- bonus_mana_por_turno
        bus.subscribe(PhaseChanged, self._on_phase_changed)
        self.bus = bus
        self._world_ref: World | None = None

    def bind(self, world: World) -> None:
        self._world_ref = world

    def _on_phase_changed(self, event: PhaseChanged) -> None:
        if event.fase_nova is not Fase.SAQUE or self._world_ref is None:
            return
        world = self._world_ref
        player_id = event.player_id
        ps = self.players[player_id]

        turn_row = world.single(TurnState)
        numero_turno = turn_row[1].numero_turno if turn_row else None
        primeiro_turno_do_jogador = numero_turno is not None and numero_turno <= len(self.players)
        if not primeiro_turno_do_jogador:
            bonus = getattr(self.ctrl, "bonus_mana_por_turno", {}).get(player_id, 0) if self.ctrl is not None else 0
            ganho = MANA_POR_TURNO + bonus
            ps.mana += ganho
            self.bus.publish(ManaChanged(player_id=player_id, delta=ganho, total=ps.mana))

        baralho = self.baralhos[player_id]
        rng = getattr(self.ctrl, "rng", None) if self.ctrl is not None else None
        try:
            carta = baralho.draw_random(rng)
        except DeckEmptyError:
            return  # baralho vazio: nao compra (regra de "sem carta" fica pro chamador decidir)

        loc = world.get_component(carta, Location)
        if loc:
            loc.zona = Zona.MAO
        else:
            world.add_component(carta, Location(zona=Zona.MAO))

        if len(ps.mao) < ps.limite_mao:
            ps.mao.append(carta)
            self.bus.publish(CardDrawn(player_id=player_id, card=carta, origem="turno"))
        else:
            # mao cheia: carta comprada e descartada na hora (nao existe regra
            # escrita pra isso em GAME_DESIGN.md; essa e a decisao mais segura
            # pra nao perder a carta silenciosamente nem estourar o limite de 6)
            loc.zona = Zona.PILHA_DESCARTE
            self.bus.publish(CardDiscarded(player_id=player_id, card=carta))

    def update(self, world: World, **ctx) -> None:
        self.bind(world)


def elemento_efetivo(world: World, card: int) -> Elemento:
    override = world.get_component(card, ElementoOverride)
    if override is not None:
        return override.elemento
    info = world.get_component(card, CardInfo)
    return info.elemento if info else Elemento.NENHUM


class CombatSystem:
    """Nao e um System "passivo" (nao reage a evento sozinho) porque um
    ataque e uma Acao do Jogador explicita — quem chama `resolver_ataque`
    e a DeclareAttackAction (game/actions.py)."""

    def __init__(self, bus: EventBus, players: dict[int, PlayerState], destruction: "DestructionSystem", ctrl=None):
        self.bus = bus
        self.players = players
        self.destruction = destruction
        self.ctrl = ctrl  # ver Jardins Suspensos (game/effects.py) -- reducao_dano_terra

    def resolver_ataque(self, world: World, atacante_player: int, atacante: int,
                         defensor_player: int, defensor: int | None,
                         multiplicador: float = 1) -> None:
        """`multiplicador` (default 1): escala o dano final do ataque, sem
        mexer no resto da fórmula (vantagem elemental, Sigurd, redução de
        Jardins Suspensos, reflexão) — usado por Aquiles ("Rapidez: ataca
        duas vezes, mas o dano é reduzido à metade"), que chama isto DUAS
        vezes com 0.5 em vez de causar dano avulso fora da fórmula normal."""
        self.bus.publish(AttackDeclared(
            atacante_player=atacante_player, atacante_card=atacante,
            defensor_player=defensor_player, defensor_card=defensor,
        ))

        stats_a = world.get_component(atacante, CombatStats)
        dano = int(stats_a.atual_pow * multiplicador)

        elem_a = elemento_efetivo(world, atacante)

        def _emitir_resolvido():
            self.bus.publish(AttackResolved(
                atacante_player=atacante_player, atacante_card=atacante,
                defensor_player=defensor_player, defensor_card=defensor,
            ))

        if defensor is None:
            # nao ha combatente pra bloquear: dano vai pros Pontos de Vida
            # do feiticeiro adversario (GAME_DESIGN.md, 'Pontos de Vida do
            # Feiticeiro e Condicao de Vitoria')
            ps = self.players[defensor_player]
            ps.vida = max(ps.vida - dano, 0)
            # DamageDealt ANTES de LifeChanged: espelha webgame/engine.js —
            # a UI web deduplica o numero flutuante de LifeChanged contra o
            # DamageDealt "gemeo" que acabou de aparecer, e só funciona
            # nessa ordem (o listener de FX ainda não existe aqui em Python,
            # mas a ordem dos dois eventos é parte do contrato espelhado).
            self.bus.publish(DamageDealt(alvo=None, alvo_player=defensor_player, quantidade=dano, origem="ataque"))
            self.bus.publish(LifeChanged(player_id=defensor_player, delta=-dano, total=ps.vida))
            _emitir_resolvido()
            return

        if world.has_component(defensor, AttackNegated):
            world.remove_component(defensor, AttackNegated)
            _emitir_resolvido()
            return  # ataque completamente anulado, sem dano nenhum

        stats_d = world.get_component(defensor, CombatStats)

        # Vantagem elemental: quem tiver vantagem sobre o elemento do OUTRO
        # ganha +2 de Combate NESTE combate — nos dois papeis (atacando OU
        # defendendo), nao so quando e o atacante. Nunca os dois ao mesmo
        # tempo (VANTAGEM_ELEMENTAL nao tem ciclo de 2 vias).
        # IgnoraFraquezaElemental nega a vantagem do OPONENTE contra quem
        # tem o componente, nos dois papeis.
        elem_d = elemento_efetivo(world, defensor)
        pow_atacante = stats_a.atual_pow
        pow_defensor = stats_d.atual_pow
        if VANTAGEM_ELEMENTAL.get(elem_a) == elem_d and not world.has_component(defensor, IgnoraFraquezaElemental):
            pow_atacante += 2
        elif VANTAGEM_ELEMENTAL.get(elem_d) == elem_a and not world.has_component(atacante, IgnoraFraquezaElemental):
            pow_defensor += 2

        # A diferenca de Combate entre os dois combatentes (ja com a
        # vantagem elemental somada) acerta quem tiver o POW MENOR — nao
        # sempre o defensor: atacar um combatente mais forte machuca o
        # proprio ATACANTE (contra-ataque). Combatentes parelhos nao se
        # machucam (diferenca 0).
        dano = abs(pow_atacante - pow_defensor)

        # Sigurd ("Matador de Feras"): a Habilidade dele so prepara o buff
        # (DanoDobradoContraMonstro, NESTE_TURNO); o dano so dobra de verdade
        # se ele ATACAR um Monstro antes do buff expirar na Fase Final.
        if world.has_component(atacante, DanoDobradoContraMonstro):
            info_d = world.get_component(defensor, CardInfo)
            if info_d and info_d.tipo is Tipo.MONSTRO:
                dano *= 2

        dano = int(dano * multiplicador)

        # Quem leva o dano: quem tiver o POW efetivo (ja com a vantagem
        # elemental) menor (empate cai pro atacante, mas dano ja e 0 nesse
        # caso — tanto faz).
        if pow_atacante <= pow_defensor:
            alvo_dano, alvo_dano_player = atacante, atacante_player
        else:
            alvo_dano, alvo_dano_player = defensor, defensor_player

        # Reflexao: se quem IA levar o dano tem o escudo, ele volta pro
        # OUTRO participante do combate (Espelho das Ilusões, Retribuição
        # Kármica).
        if world.has_component(alvo_dano, DamageReflected):
            if alvo_dano == atacante:
                alvo_dano, alvo_dano_player = defensor, defensor_player
            else:
                alvo_dano, alvo_dano_player = atacante, atacante_player

        # Jardins Suspensos: "todo dano recebido por combatentes de Terra é
        # reduzido em 3" (passivo) — vale pra quem quer que esteja levando o
        # dano agora, nao so o defensor de costume.
        reducao_terra = getattr(self.ctrl, "reducao_dano_terra", None) if self.ctrl is not None else None
        if reducao_terra and elemento_efetivo(world, alvo_dano) is Elemento.TERRA:
            dano = max(dano - reducao_terra, 0)

        # O dano que passar da Resistencia da criatura vaza pra vida do
        # PROPRIO dono dela — antes esse excedente era simplesmente descartado.
        stats_alvo = world.get_component(alvo_dano, CombatStats)
        res_antes = stats_alvo.atual_res
        dano_na_criatura = min(dano, res_antes)
        excedente = dano - dano_na_criatura
        # dano_acumulado (não mutar atual_res direto): sobrevive a qualquer
        # recálculo futuro por outro motivo (ver CombatStats, components.py —
        # bug real que isso corrige: um buff não relacionado nessa mesma
        # carta, depois, silenciosamente "curava" o dano de combate).
        stats_alvo.dano_acumulado += dano_na_criatura
        _recalcular_stats(world, alvo_dano)
        self.bus.publish(DamageDealt(alvo=alvo_dano, alvo_player=alvo_dano_player, quantidade=dano_na_criatura, origem="ataque"))
        if excedente > 0:
            ps_alvo = self.players[alvo_dano_player]
            ps_alvo.vida = max(ps_alvo.vida - excedente, 0)
            # mesma ordem DamageDealt-antes-de-LifeChanged do dano direto (dedup de FX).
            self.bus.publish(DamageDealt(alvo=None, alvo_player=alvo_dano_player, quantidade=excedente, origem="ataque"))
            self.bus.publish(LifeChanged(player_id=alvo_dano_player, delta=-excedente, total=ps_alvo.vida))

        if stats_alvo.atual_res <= 0:
            self.destruction.destruir(world, alvo_dano, motivo="derrotado em combate")
            # quem CAUSOU o dano ganha +1 de mana — vale pro atacante de
            # costume, pro defensor quando o dano volta por reflexao (Espelho
            # das Ilusões, Retribuição Kármica), e agora também pro defensor
            # quando o próprio atacante morre de contra-ataque por atacar
            # algo mais forte.
            beneficiario = defensor_player if alvo_dano_player == atacante_player else atacante_player
            ps_beneficiario = self.players[beneficiario]
            ps_beneficiario.mana += 1
            self.bus.publish(ManaChanged(player_id=beneficiario, delta=1, total=ps_beneficiario.mana))
        _emitir_resolvido()


class DestructionSystem:
    """Ponto UNICO pra 'uma carta morreu': tira do slot de tabuleiro em que
    ela estiver (Monstro ou Magia), move pra Pilha de Descarte e publica
    `CardDestroyed`. Isso garante que nenhum caminho (combate, efeito de
    carta, gatilho) deixe uma entidade destruida "presa" num slot — foi
    exatamente esse bug (combatente morto continuava sendo o `.monstro`
    ativo e seguia atacando) que motivou centralizar tudo aqui em vez de
    cada chamador zerar o slot por conta propria.

    Tambem e o UM lugar certo pra qualquer gatilho 'ao ser destruido'
    (Cu Chulainn, Trono de Camelot, Valhalla, Jardins Suspensos, Caixa de
    Pandora — GAME_DESIGN.md) escutar, via `CardDestroyed`.
    """

    def __init__(self, bus: EventBus, board=None, dono_da_carta=None, ctrl=None):
        self.bus = bus
        self.board = board
        self.dono_da_carta = dono_da_carta
        self.ctrl = ctrl  # ver triggers.py — remover_passivos_de/remover_triggers_de/CardAboutToBeDestroyed

    def destruir(self, world: World, card: int, motivo: str = "") -> None:
        owner = self.dono_da_carta(card) if self.dono_da_carta is not None else None
        zona_nova = Zona.PILHA_DESCARTE

        if self.board is not None and owner is not None:
            lado = self.board.lado(owner)
            if lado.monstro == card:
                lado.remover_monstro()
            elif card in lado.magia:
                lado.remover_magia(card)

            # evento PRE-destruicao: da pra um gatilho (ex.: Valhalla)
            # sobrescrever contexto["destino"] ANTES de decidir pra onde a
            # carta vai. Ainda NAO limpamos os gatilhos desta carta aqui de
            # proposito -- uma carta pode ter um gatilho que reage à PRÓPRIA
            # destruição (ex.: Cu Chulainn), que só dispara mais abaixo, no
            # evento CardDestroyed.
            if self.ctrl is not None:
                contexto = {"destino": "descarte"}
                self.bus.publish(CardAboutToBeDestroyed(card=card, motivo=motivo, player_id=owner, contexto=contexto))
                if contexto["destino"] == "panteao":
                    zona_nova = Zona.PANTEAO
                    self.ctrl.panteoes[owner].devolver(card)

        loc = world.get_component(card, Location)
        zona_anterior = loc.zona if loc else None
        if loc:
            loc.zona = zona_nova
        self.bus.publish(CardMoved(card=card, zona_anterior=zona_anterior, zona_nova=zona_nova))
        self.bus.publish(CardDestroyed(card=card, motivo=motivo))

        # só agora, depois que a própria carta teve a chance de reagir à sua
        # destruição (ex.: Cu Chulainn), limpa qualquer passivo/gatilho cuja
        # FONTE é ela -- o buff "enquanto ativo" de um Domínio some quando
        # ele morre.
        if self.ctrl is not None:
            from .triggers import remover_passivos_de, remover_triggers_de
            remover_passivos_de(self.ctrl, card)
            remover_triggers_de(self.ctrl, card)
