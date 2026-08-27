# -*- coding: utf-8 -*-
"""Efeitos de carta: implementa `Efeito / Habilidade` das 60 cartas do CSV
como composicoes de um punhado de PRIMITIVAS (comprar, descartar, buff,
dano, destruir, mana, retornar ao Panteão...). Isso e deliberado — a secao
'Vocabulario de Mecanicas' de GAME_DESIGN.md ja mostrou que quase todo texto
de habilidade e uma dessas operacoes basicas + um alvo + uma duracao.

Efeitos com uma parte PASSIVA ("enquanto ativo...") ou de GATILHO
("Quando"/"Sempre que"/"No início do turno") usam `EFFECTS.registrar_passivo`
ou `triggers.registrar_trigger` em vez de mutar o estado direto — ver
`triggers.py` e a seção correspondente em `GAME_ENGINE.md`. Ex.: Trono de
Camelot reaplica o bônus a cada Fase Principal e some quando o Domínio é
destruído; Jörmungandr registra um gatilho de dano recorrente no alvo;
Caixa de Pandora dispara em `CardDestroyed` filtrado pelo dono, não na
própria destruição (bug real corrigido por essa arquitetura).

SIMPLIFICACOES QUE RESTAM (documentadas aqui uma vez, em vez de nota por
carta):
  - Efeitos "todos os X" afetam os combatentes ATIVOS no momento (1 por
    lado, dado que o tabuleiro so tem 1 slot de Monstro).
  - Rebote Arcano exige rastrear "o proximo feitico inimigo" — stub
    comentado, nao modelado.
  - Praga da Ferrugem, Gilgamesh ("Compre 1 carta de Equipamento") e
    Desintegração de Realidade ("...ou um Equipamento ligado a um
    combatente inimigo") dependem de um subtipo "Equipamento" que nao
    existe nos dados do CSV atual — Gilgamesh compra do Baralho Arcano
    normal; Desintegração de Realidade só destrói o Domínio.
  - Apoio Incondicional precisaria de um mecanismo de "par de alvos
    vinculados" a parte — placeholder deliberado, cai no fallback de
    `executar` (nenhum efeito registrado, no-op).

Cada funcao tem a assinatura `(ctrl, player_id, card)`, onde `player_id` e
quem ATIVOU/JOGOU a carta e `card` e a propria entidade.
"""
from __future__ import annotations

from typing import Callable

from .components import (
    AbilityCost, AttackedThisTurn, AttackNegated, CardInfo, CombatStats,
    DamageReflected, DanoDobradoContraMonstro, Duracao, Elemento,
    ElementoOverride, Fase, FaceDown, IgnoraFraquezaElemental,
    ImuneAHabilidadesInimigas, Location,
    ManaCost, StatusEffect, StatusEffects, Tipo, Zona,
)
from .deck import DeckEmptyError
from .events import (
    AbilityActivated, AttackDeclared, AttackResolved, CardAboutToBeDestroyed,
    CardDestroyed, CardDiscarded, CardDrawn, CombatantSummoned, DamageDealt,
    Event, LifeChanged, ManaChanged, PhaseChanged, TurnStarted,
)
from .phases import _recalcular_stats
from .systems import elemento_efetivo


class TopoRevelado(Event):
    def __init__(self, player_id: int, cartas: list[int]):
        self.player_id = player_id
        self.cartas = cartas


# ---------------------------------------------------------------------------
# Primitivas
# ---------------------------------------------------------------------------

def _oponente(ctrl, player_id: int) -> int:
    return next(p for p in ctrl.jogadores if p != player_id)


def buff(ctrl, card: int, atributo: str, magnitude: int,
         duracao: Duracao = Duracao.PERMANENTE, origem: str = "") -> None:
    statuses = ctrl.world.get_component(card, StatusEffects)
    if statuses is None:
        statuses = ctrl.world.add_component(card, StatusEffects())
    statuses.itens.append(StatusEffect(atributo=atributo, magnitude=magnitude, duracao=duracao, origem=origem))
    _recalcular_stats(ctrl.world, card)


def curar(ctrl, card: int, quantidade: int) -> None:
    stats = ctrl.world.get_component(card, CombatStats)
    if stats is None:
        return
    # Cura nao passa da Resistencia base (nao "sobre-cura" acima do impresso),
    # mas tambem nunca REDUZ o valor atual — se um buff ja tiver deixado a
    # Resistencia acima da base, curar nao pode derrubar isso de volta.
    alvo_res = max(stats.atual_res, min(stats.atual_res + quantidade, stats.base_res))
    # traduz em reduzir dano_acumulado (nao mutar atual_res direto) — é o que
    # sobrevive a um recálculo futuro por outro motivo (ver CombatStats).
    stats.dano_acumulado = max(stats.dano_acumulado - (alvo_res - stats.atual_res), 0)
    _recalcular_stats(ctrl.world, card)


def dano_combatente(ctrl, card: int | None, quantidade: int, origem: str = "") -> None:
    if card is None:
        return
    stats = ctrl.world.get_component(card, CombatStats)
    if stats is None:
        return
    # Jardins Suspensos: "todo dano recebido por combatentes de Terra é
    # reduzido em 3" (passivo, ver ctrl.reducao_dano_terra abaixo).
    reducao_terra = getattr(ctrl, "reducao_dano_terra", None)
    if reducao_terra and elemento_efetivo(ctrl.world, card) is Elemento.TERRA:
        quantidade = max(quantidade - reducao_terra, 0)
    # dano_acumulado (não mutar atual_res direto): sobrevive a qualquer
    # recálculo futuro por outro motivo — bug real que isso corrige: um buff
    # não relacionado nessa mesma carta, depois, silenciosamente "curava"
    # esse dano (ver CombatStats, components.py).
    stats.dano_acumulado += quantidade
    _recalcular_stats(ctrl.world, card)
    ctrl.bus.publish(DamageDealt(alvo=card, alvo_player=None, quantidade=quantidade, origem=origem))
    if stats.atual_res <= 0:
        ctrl.destruction_system.destruir(ctrl.world, card, motivo=origem or "destruido por efeito")


def dano_jogador(ctrl, player_id: int, quantidade: int, origem: str = "") -> None:
    ps = ctrl.players[player_id]
    ps.vida = max(ps.vida - quantidade, 0)
    # DamageDealt antes de LifeChanged — mesma ordem de systems.py/webgame,
    # ver comentário lá (a UI web depende dessa ordem pra deduplicar FX).
    ctrl.bus.publish(DamageDealt(alvo=None, alvo_player=player_id, quantidade=quantidade, origem=origem))
    ctrl.bus.publish(LifeChanged(player_id=player_id, delta=-quantidade, total=ps.vida))


def destruir(ctrl, card: int | None, motivo: str = "") -> None:
    if card is None:
        return
    ctrl.destruction_system.destruir(ctrl.world, card, motivo=motivo)


def comprar(ctrl, player_id: int, n: int) -> list[int]:
    ps = ctrl.players[player_id]
    baralho = ctrl.baralhos[player_id]
    compradas = []
    for _ in range(n):
        try:
            carta = baralho.draw_random(ctrl.rng)
        except DeckEmptyError:
            break
        loc = ctrl.world.get_component(carta, Location)
        if loc:
            loc.zona = Zona.MAO
        else:
            ctrl.world.add_component(carta, Location(zona=Zona.MAO))
        if len(ps.mao) >= ps.limite_mao:
            loc.zona = Zona.PILHA_DESCARTE
            ctrl.bus.publish(CardDiscarded(player_id=player_id, card=carta))
            continue
        ps.mao.append(carta)
        compradas.append(carta)
        ctrl.bus.publish(CardDrawn(player_id=player_id, card=carta))
    return compradas


def descartar_aleatorias(ctrl, player_id: int, n: int) -> list[int]:
    ps = ctrl.players[player_id]
    alvo = ctrl.rng.sample(ps.mao, k=min(n, len(ps.mao)))
    for card in alvo:
        ps.mao.remove(card)
        loc = ctrl.world.get_component(card, Location)
        if loc:
            loc.zona = Zona.PILHA_DESCARTE
        ctrl.bus.publish(CardDiscarded(player_id=player_id, card=card))
    return alvo


def ganhar_mana(ctrl, player_id: int, n: int) -> None:
    ps = ctrl.players[player_id]
    ps.mana += n
    ctrl.bus.publish(ManaChanged(player_id=player_id, delta=n, total=ps.mana))


def perder_mana(ctrl, player_id: int, n: int) -> int:
    ps = ctrl.players[player_id]
    roubado = min(n, ps.mana)
    ps.mana -= roubado
    ctrl.bus.publish(ManaChanged(player_id=player_id, delta=-roubado, total=ps.mana))
    return roubado


def retornar_ao_panteao(ctrl, player_id: int, card: int | None) -> None:
    if card is None:
        return
    lado = ctrl.board.lado(player_id)
    if lado.monstro == card:
        lado.remover_monstro()
    # Volta como copia "intocada": sem dano/buffs acumulados nem gatilhos
    # pendurados na entidade — igual a qualquer outro Combatente esperando
    # no Panteão pra ser invocado (convenção padrão de TCG: sair de campo
    # "reseta" o objeto). Sem isso, ex.: o gatilho de Veneno de Jörmungandr
    # continuava mordendo um alvo que nem estava mais em jogo, e uma carta
    # podia voltar pro Panteão carregando dano/buff da vida anterior.
    from .triggers import remover_passivos_de, remover_triggers_de
    remover_passivos_de(ctrl, card)
    remover_triggers_de(ctrl, card)
    statuses = ctrl.world.get_component(card, StatusEffects)
    if statuses is not None:
        statuses.itens = []
    stats = ctrl.world.get_component(card, CombatStats)
    if stats is not None:
        stats.dano_acumulado = 0
        _recalcular_stats(ctrl.world, card)
    for comp_type in (AttackNegated, DamageReflected, IgnoraFraquezaElemental,
                       DanoDobradoContraMonstro, AttackedThisTurn, ImuneAHabilidadesInimigas):
        if ctrl.world.has_component(card, comp_type):
            ctrl.world.remove_component(card, comp_type)
    ability = ctrl.world.get_component(card, AbilityCost)
    if ability is not None:
        ability.usada_neste_turno = False
    ctrl.panteoes[player_id].devolver(card)
    loc = ctrl.world.get_component(card, Location)
    if loc:
        loc.zona = Zona.PANTEAO


def protegido_contra_maldicao(ctrl, player_id: int) -> bool:
    if getattr(ctrl, "_protecao_maldicao", None) and player_id in ctrl._protecao_maldicao:
        ctrl._protecao_maldicao.discard(player_id)
        return True
    return False


def negar_proximo_ataque(ctrl, card: int) -> None:
    ctrl.world.add_component(card, AttackNegated())


def refletir_dano(ctrl, card: int) -> None:
    ctrl.world.add_component(card, DamageReflected())


def combatente_ativo(ctrl, player_id: int) -> int | None:
    return ctrl.board.lado(player_id).monstro


def dominio_ativo(ctrl, player_id: int) -> int | None:
    return ctrl.board.lado(player_id).dominio_ativo(ctrl.world, ctrl.dominio_cards)


def dominio_ativo_global(ctrl) -> int | None:
    """Só pode haver 1 Domínio ativo NO JOGO INTEIRO (compartilhado — ver
    comentário de TCG.dominioParaFundo em webgame/engine.js), não uma por
    lado; usado por efeitos como Fenrir ("Destrói a carta de Domínio ativa
    no campo") que miram o Domínio em si, não o de um jogador específico."""
    for pid in ctrl.jogadores:
        d = dominio_ativo(ctrl, pid)
        if d is not None:
            return d
    return None


# ---------------------------------------------------------------------------
# Registro
# ---------------------------------------------------------------------------

class EffectRegistry:
    def __init__(self) -> None:
        self._fns: dict[str, Callable] = {}
        self._on_destroy: dict[str, Callable] = {}
        self._gatilhos_maldicao: dict[str, tuple[type, Callable]] = {}

    def registrar(self, nome: str):
        def deco(fn):
            self._fns[nome] = fn
            return fn
        return deco

    def registrar_passivo(self, nome: str, limpar: Callable | None = None):
        """Efeito PASSIVO ("enquanto ativo..."): `fn` roda já na ativação e
        de novo a cada Fase Principal (limpa-e-reaplica, ver
        triggers.aplicar_passivos), até a carta-fonte sair de campo. `limpar`
        (opcional) desfaz o que `fn` fez — o padrão remove os StatusEffects
        com origem = nome da carta; passe um `limpar` próprio quando o
        passivo mexe em outra coisa (um atributo em `ctrl`, por exemplo)."""
        def deco(fn):
            def wrapper(ctrl, player_id, card, evento=None):
                from .triggers import registrar_passivo
                registrar_passivo(ctrl, player_id, card, fn, limpar)
                fn(ctrl, player_id, card)
            self._fns[nome] = wrapper
            return fn
        return deco

    def registrar_gatilho_maldicao(self, nome: str, evento_tipo: type, condicao: Callable | None = None) -> None:
        """Tabela declarativa: qual TIPO de evento torna uma Maldição virada
        pra baixo ELEGÍVEL pro modal de "ativar agora?" (ver curses.py).
        `condicao(evento, ctrl, dono_id) -> bool`, padrão sempre True. Sem
        entrada aqui = a Maldição nunca aparece nesse modal (ex.: Praga da
        Ferrugem, que depende de um subtipo "Equipamento" inexistente)."""
        self._gatilhos_maldicao[nome] = (evento_tipo, condicao or (lambda evento, ctrl, dono_id: True))

    def gatilho_maldicao(self, nome: str):
        return self._gatilhos_maldicao.get(nome)

    def ao_destruir(self, nome: str):
        def deco(fn):
            self._on_destroy[nome] = fn
            return fn
        return deco

    def executar(self, ctrl, nome: str, player_id: int, card: int, evento=None) -> None:
        fn = self._fns.get(nome)
        if fn is None:
            print(f"[effects] aviso: nenhum efeito implementado para '{nome}', ignorando.")
            return
        fn(ctrl, player_id, card, evento)

    def ligar_gatilhos(self, ctrl) -> None:
        def _on_destroyed(event: CardDestroyed):
            info = ctrl.world.get_component(event.card, CardInfo)
            if info is None:
                return
            fn = self._on_destroy.get(info.nome)
            if fn:
                fn(ctrl, ctrl.dono_da_carta(event.card), event.card)
        ctrl.bus.subscribe(CardDestroyed, _on_destroyed)


EFFECTS = EffectRegistry()


# ---- Heróis -----------------------------------------------------------

@EFFECTS.registrar("Rei Arthur")
def _(ctrl, player_id, card, evento=None):
    buff(ctrl, card, "pow", 4, Duracao.NESTE_TURNO, "Excalibur")


@EFFECTS.registrar("Beowulf")
def _(ctrl, player_id, card, evento=None):
    curar(ctrl, card, 4)


@EFFECTS.registrar("Odisseu")
def _(ctrl, player_id, card, evento=None):
    ctrl._protecao_maldicao = getattr(ctrl, "_protecao_maldicao", set())
    ctrl._protecao_maldicao.add(player_id)


@EFFECTS.registrar("Sigurd")
def _(ctrl, player_id, card, evento=None):
    # "Matador de Feras: Dano em dobro contra Monstros" — a Habilidade só
    # PREPARA o buff (NESTE_TURNO); o dano dobrado só sai de verdade se
    # Sigurd de fato ATACAR um Monstro antes do fim do turno
    # (CombatSystem.resolver dobra o dano de combate nessa condição). Sem
    # isso, "Dano em dobro" virava um nuke avulso que não exigia ataque
    # nenhum — não bate com o texto nem com o resto do vocabulário do jogo
    # (GAME_DESIGN.md separa Habilidade de Ataque).
    ctrl.world.add_component(card, DanoDobradoContraMonstro())


@EFFECTS.registrar("Joana d'Arc")
def _(ctrl, player_id, card, evento=None):
    alvo = combatente_ativo(ctrl, player_id)
    if alvo is not None:
        # "Cura totalmente" = curar() com uma quantidade grande o bastante
        # pra sempre bater no teto (base_res) — reaproveita a mesma proteção
        # de curar() (nunca reduz um atual_res já acima da base por causa de
        # buff permanente) em vez de duplicar a lógica.
        stats = ctrl.world.get_component(alvo, CombatStats)
        curar(ctrl, alvo, stats.base_res)


@EFFECTS.registrar("Gilgamesh")
def _(ctrl, player_id, card, evento=None):
    comprar(ctrl, player_id, 1)  # simplificado: nao ha subtipo "Equipamento" nos dados atuais


@EFFECTS.registrar("Aquiles")
def _(ctrl, player_id, card, evento=None):
    # "Ataca duas vezes, mas o dano é reduzido à metade" — dispara DOIS
    # ataques DE VERDADE (passam pela fórmula normal de combate em
    # CombatSystem.resolver_ataque: diferença de Combate, bônus elemental,
    # Sigurd, Jardins Suspensos, reflexão), cada um com o dano final
    # dividido por 2 — não um nuke avulso de "metade do Combate atual"
    # direto no alvo, fora da fórmula (mesmo raciocínio da correção de
    # Sigurd). Conta como o ataque do turno: depois de ativar, não dá pra
    # declarar um ataque normal de novo. Não passa por
    # curses.ofertar_maldicoes_reativas (Maldições reativas a "ataque
    # declarado", tipo Escudo de Gelo Absoluto, não são oferecidas aqui) —
    # escopo deliberadamente menor que um ataque declarado de verdade.
    oponente = _oponente(ctrl, player_id)
    for _ in range(2):
        defensor = combatente_ativo(ctrl, oponente)
        ctrl.combat_system.resolver_ataque(ctrl.world, player_id, card, oponente, defensor, multiplicador=0.5)
    ctrl.world.add_component(card, AttackedThisTurn())


@EFFECTS.registrar("Atalanta")
def _(ctrl, player_id, card, evento=None):
    dano_jogador(ctrl, _oponente(ctrl, player_id), 5, "Flecha Veloz")


@EFFECTS.registrar("Cu Chulainn")
def _(ctrl, player_id, card, evento=None):
    # "Se for derrotado NO ATAQUE, o alvo também é" — não é um efeito pra
    # disparar na hora que a Habilidade é ativada, e sim um gatilho de
    # morte: registra um trigger em CardDestroyed que só faz algo se a carta
    # destruída for o PRÓPRIO Cu Chulainn E se a vez ainda for do dono dele
    # (Fase de Batalha só acontece no turno de quem ataca, então se ainda é
    # a vez dele, foi ELE quem atacou e morreu por dano refletido).
    from .triggers import registrar_trigger, remover_triggers_de

    def _condicao(evento, ctrl):
        return (evento.card == card and evento.motivo == "derrotado em combate"
                and ctrl.fase_atual().jogador_da_vez == player_id)

    def _efeito(evento, ctrl):
        oponente = _oponente(ctrl, player_id)
        destruir(ctrl, combatente_ativo(ctrl, oponente), "Fúria Final")

    # A vingança só protege ATÉ O FIM DO TURNO em que a Habilidade foi
    # ativada — mesmo padrão de duração das outras Habilidades de combatente
    # (Rei Arthur, Sigurd, Quimera: todas NESTE_TURNO). Sem isso, o gatilho
    # ficava armado PRA SEMPRE (só sumia se Cu Chulainn morresse) — pagar o
    # custo de Habilidade de novo em turnos seguintes nunca fazia diferença
    # nenhuma, já que a vingança já estava permanentemente armada.
    def _condicao_expira(evento, ctrl):
        return evento.fase_nova is Fase.FINAL and evento.player_id == player_id

    def _expira(evento, ctrl):
        remover_triggers_de(ctrl, card)

    remover_triggers_de(ctrl, card)  # evita empilhar de novo se a Habilidade for ativada mais de 1 vez
    registrar_trigger(ctrl, CardDestroyed, _efeito, origem_card=card, owner_player_id=player_id, condicao=_condicao)
    registrar_trigger(ctrl, PhaseChanged, _expira, origem_card=card, owner_player_id=player_id,
                       condicao=_condicao_expira, persistente=False)


@EFFECTS.registrar("Merlin")
def _(ctrl, player_id, card, evento=None):
    topo = ctrl.baralhos[player_id].topo(3)
    ctrl.bus.publish(TopoRevelado(player_id=player_id, cartas=topo))


# ---- Monstros -----------------------------------------------------------

@EFFECTS.registrar("Cthulhu")
def _(ctrl, player_id, card, evento=None):
    descartar_aleatorias(ctrl, _oponente(ctrl, player_id), 2)


@EFFECTS.registrar("Fenrir")
def _(ctrl, player_id, card, evento=None):
    # "Destrói a carta de Domínio ativa no campo" — sem qualificar dono. Como
    # só existe 1 Domínio ativo NO JOGO INTEIRO (compartilhado, fica no slot
    # de magia de quem o jogou por último), mira esse Domínio único, mesmo
    # que tenha sido o próprio controlador de Fenrir quem o ativou — checar
    # só o lado do oponente deixava a Habilidade sem alvo válido nesse caso,
    # apesar de haver um Domínio bem "ativo no campo".
    destruir(ctrl, dominio_ativo_global(ctrl), "Devorar")


@EFFECTS.registrar("Jörmungandr")
def _(ctrl, player_id, card, evento=None):
    # "Causa 3 de dano POR TURNO ao alvo atingido" — não é um dano único;
    # morde logo na ativação e registra um gatilho no PRÓPRIO alvo (não em
    # Jörmungandr) que continua mordendo a cada início de turno do
    # controlador do alvo, até o alvo morrer (o destruir dele mesmo limpa o
    # gatilho — a sobrevida de Jörmungandr não importa pro veneno continuar).
    from .triggers import registrar_trigger

    alvo = combatente_ativo(ctrl, _oponente(ctrl, player_id))
    if alvo is None:
        return
    dano_combatente(ctrl, alvo, 3, "Veneno")
    stats = ctrl.world.get_component(alvo, CombatStats)
    if stats is None or stats.atual_res <= 0:
        return  # ja morreu com a mordida inicial, sem gatilho pra registrar
    dono_do_alvo = ctrl.dono_da_carta(alvo)

    def _condicao(evento, ctrl):
        return evento.player_id == dono_do_alvo

    def _efeito(evento, ctrl):
        dano_combatente(ctrl, alvo, 3, "Veneno")

    registrar_trigger(ctrl, TurnStarted, _efeito, origem_card=alvo, owner_player_id=player_id, condicao=_condicao)


@EFFECTS.registrar("Tífon")
def _(ctrl, player_id, card, evento=None):
    retornar_ao_panteao(ctrl, _oponente(ctrl, player_id), combatente_ativo(ctrl, _oponente(ctrl, player_id)))


@EFFECTS.registrar("Shoggoth")
def _(ctrl, player_id, card, evento=None):
    ctrl.world.add_component(card, IgnoraFraquezaElemental())


@EFFECTS.registrar("Surtur")
def _(ctrl, player_id, card, evento=None):
    for pid in ctrl.jogadores:
        dano_combatente(ctrl, combatente_ativo(ctrl, pid), 10, "Ragnarok")


@EFFECTS.registrar("Wendigo")
def _(ctrl, player_id, card, evento=None):
    oponente = _oponente(ctrl, player_id)
    roubado = perder_mana(ctrl, oponente, 2)
    ganhar_mana(ctrl, player_id, roubado)


@EFFECTS.registrar("Nyarlathotep")
def _(ctrl, player_id, card, evento=None):
    # "Olhe... e desarme uma" — quem ativa ve as Maldições reveladas e
    # ESCOLHE qual desarmar, isso e uma decisao de verdade do jogador.
    oponente = _oponente(ctrl, player_id)
    lado = ctrl.board.lado(oponente)
    setadas = [c for c in lado.magia if c is not None and ctrl.world.has_component(c, FaceDown)]
    if not setadas:
        return
    ctrl.bus.publish(TopoRevelado(player_id=player_id, cartas=setadas))
    ctrl.solicitar_selecao(
        player_id=player_id,
        prompt="Caos: escolha 1 Maldição virada para baixo do oponente para desarmar",
        opcoes=setadas,
        on_resolved=lambda escolha: destruir(ctrl, escolha[0], "Caos"),
    )


@EFFECTS.registrar("Minotauro")
def _(ctrl, player_id, card, evento=None):
    alvo = combatente_ativo(ctrl, _oponente(ctrl, player_id))
    if alvo is not None and ctrl.world.has_component(alvo, ImuneAHabilidadesInimigas):
        return  # Manto da Natureza
    ability = ctrl.world.get_component(alvo, AbilityCost) if alvo else None
    if ability:
        ability.usada_neste_turno = True  # simplificado: bloqueia so o turno corrente


@EFFECTS.registrar("Quimera")
def _(ctrl, player_id, card, evento=None):
    alvo = combatente_ativo(ctrl, _oponente(ctrl, player_id))
    if alvo is not None and elemento_efetivo(ctrl.world, alvo) is Elemento.TERRA:
        buff(ctrl, card, "pow", 2, Duracao.NESTE_TURNO, "Três Cabeças")


# ---- Domínios -----------------------------------------------------------
#
# Todos os 10 Domínios têm efeito PASSIVO ("enquanto ativo...") e/ou um
# GATILHO ("Quando"/"Sempre que"/"No início do turno") — ver triggers.py.
# Passivos são reaplicados do zero a cada Fase Principal (registrar_passivo) e
# somem quando o Domínio é destruído; gatilhos ficam registrados esperando o
# evento certo, e também são removidos automaticamente na destruição
# (DestructionSystem.destruir chama remover_passivos_de/remover_triggers_de).

@EFFECTS.registrar_passivo("Trono de Camelot")
def _(ctrl, player_id, card, evento=None):
    # "todos os Espíritos Heróicos" — sem qualificar dono, vale pros DOIS
    # lados (mesmo padrão de Vulcão Primordial), não só o combatente do
    # controlador do Domínio.
    for pid in ctrl.jogadores:
        alvo = combatente_ativo(ctrl, pid)
        info = ctrl.world.get_component(alvo, CardInfo) if alvo else None
        if info and info.tipo is Tipo.HEROI:
            buff(ctrl, alvo, "pow", 3, Duracao.PERMANENTE, "Trono de Camelot")


@EFFECTS.ao_destruir("Trono de Camelot")
def _(ctrl, player_id, card, evento=None):
    comprar(ctrl, player_id, 1)


@EFFECTS.registrar("Fenda de R'lyeh")
def _(ctrl, player_id, card, evento=None):
    from .triggers import registrar_passivo, registrar_trigger

    # "Monstros Primordiais ganham +4 de Resistência" — sem qualificar dono,
    # vale pros DOIS lados (mesmo padrão de Vulcão Primordial), não só o
    # combatente do controlador do Domínio.
    def _aplicar(ctrl, player_id, card):
        for pid in ctrl.jogadores:
            alvo = combatente_ativo(ctrl, pid)
            info = ctrl.world.get_component(alvo, CardInfo) if alvo else None
            if info and info.tipo is Tipo.MONSTRO:
                buff(ctrl, alvo, "res", 4, Duracao.PERMANENTE, "Fenda de R'lyeh")

    registrar_passivo(ctrl, player_id, card, _aplicar)
    _aplicar(ctrl, player_id, card)

    # "No início do turno, ambos descartam 1 carta" — os dois jogadores, todo turno.
    def _efeito(evento, ctrl):
        for pid in ctrl.jogadores:
            descartar_aleatorias(ctrl, pid, 1)

    registrar_trigger(ctrl, TurnStarted, _efeito, origem_card=card, owner_player_id=player_id)


@EFFECTS.registrar_passivo("Vulcão Primordial")
def _(ctrl, player_id, card, evento=None):
    for pid in ctrl.jogadores:
        alvo = combatente_ativo(ctrl, pid)
        if alvo is None:
            continue
        elem = elemento_efetivo(ctrl.world, alvo)
        if elem is Elemento.FOGO:
            buff(ctrl, alvo, "pow", 3, Duracao.PERMANENTE, "Vulcão Primordial")
        elif elem is Elemento.VENTO:
            buff(ctrl, alvo, "res", -2, Duracao.PERMANENTE, "Vulcão Primordial")


# "Sempre que um combatente de Água usar uma Habilidade de Mana, o
# feiticeiro recupera 1 de Mana" — gatilho puro, sem parte passiva.
@EFFECTS.registrar("Templo de Atlântida")
def _(ctrl, player_id, card, evento=None):
    from .triggers import registrar_trigger

    def _condicao(evento, ctrl):
        return elemento_efetivo(ctrl.world, evento.card) is Elemento.AGUA

    def _efeito(evento, ctrl):
        ganhar_mana(ctrl, evento.player_id, 1)

    registrar_trigger(ctrl, AbilityActivated, _efeito, origem_card=card, owner_player_id=player_id, condicao=_condicao)


# "Combatentes de Vento podem retornar ao Panteão logo após atacar, evitando
# contra-ataques" — sem contra-ataque modelado, vira determinístico: todo
# combatente de Vento que sobrevive ao próprio ataque volta sozinho.
@EFFECTS.registrar("Cânion dos Ventos")
def _(ctrl, player_id, card, evento=None):
    from .triggers import registrar_trigger

    def _condicao(evento, ctrl):
        atacante = evento.atacante_card
        return (elemento_efetivo(ctrl.world, atacante) is Elemento.VENTO
                and ctrl.board.lado(evento.atacante_player).monstro == atacante)

    def _efeito(evento, ctrl):
        retornar_ao_panteao(ctrl, evento.atacante_player, evento.atacante_card)

    registrar_trigger(ctrl, AttackResolved, _efeito, origem_card=card, owner_player_id=player_id, condicao=_condicao)


# "Todo dano recebido por combatentes de Terra é reduzido em 3" (passivo,
# checado em dano_combatente/CombatSystem via ctrl.reducao_dano_terra) +
# "Se um for derrotado, o feiticeiro [dono do Domínio] ganha 4 de Mana" (gatilho).
@EFFECTS.registrar("Jardins Suspensos")
def _(ctrl, player_id, card, evento=None):
    from .triggers import registrar_passivo, registrar_trigger

    def _aplicar(ctrl, player_id, card):
        ctrl.reducao_dano_terra = 3

    def _limpar(ctrl, card):
        ctrl.reducao_dano_terra = None

    registrar_passivo(ctrl, player_id, card, _aplicar, _limpar)
    _aplicar(ctrl, player_id, card)

    def _condicao(evento, ctrl):
        stats = ctrl.world.get_component(evento.card, CombatStats)
        return stats is not None and elemento_efetivo(ctrl.world, evento.card) is Elemento.TERRA

    def _efeito(evento, ctrl):
        ganhar_mana(ctrl, player_id, 4)

    registrar_trigger(ctrl, CardDestroyed, _efeito, origem_card=card, owner_player_id=player_id, condicao=_condicao)


# "Quando um Espírito Heróico for derrotado, em vez de ir para a Pilha de
# Descarte, ele retorna para o Panteão" — intercepta o destino no evento
# PRÉ-destruição (ver DestructionSystem.destruir), sem caso especial lá.
@EFFECTS.registrar("Valhalla")
def _(ctrl, player_id, card, evento=None):
    from .triggers import registrar_trigger

    def _condicao(evento, ctrl):
        info = ctrl.world.get_component(evento.card, CardInfo)
        return info is not None and info.tipo is Tipo.HEROI

    def _efeito(evento, ctrl):
        evento.contexto["destino"] = "panteao"

    registrar_trigger(ctrl, CardAboutToBeDestroyed, _efeito, origem_card=card, owner_player_id=player_id, condicao=_condicao)


@EFFECTS.ao_destruir("Valhalla")
def _(ctrl, player_id, card, evento=None):
    pass  # redirecionamento tratado acima via CardAboutToBeDestroyed


# "Todo Monstro em campo ganha +3 de Combate" (passivo) + "Nenhuma carta pode
# ser retirada ou revivida da Pilha de Descarte" (flag global, checada em
# Ressurreição Arcana e Chamado do Além — os únicos 2 efeitos que tiram
# carta do descarte).
@EFFECTS.registrar("Fosso de Tártaro")
def _(ctrl, player_id, card, evento=None):
    from .triggers import registrar_passivo

    # "Todo Monstro em campo ganha +3 de Combate" — sem qualificar dono, vale
    # pros DOIS lados (mesmo padrão de Vulcão Primordial), não só o
    # combatente do controlador do Domínio.
    def _aplicar(ctrl, player_id, card):
        for pid in ctrl.jogadores:
            alvo = combatente_ativo(ctrl, pid)
            info = ctrl.world.get_component(alvo, CardInfo) if alvo else None
            if info and info.tipo is Tipo.MONSTRO:
                buff(ctrl, alvo, "pow", 3, Duracao.PERMANENTE, "Fosso de Tártaro")
        ctrl.bloqueia_ressureicao = True

    def _limpar(ctrl, card):
        from .triggers import limpar_status_por_origem
        limpar_status_por_origem(ctrl, ctrl.nome_da_carta(card))
        ctrl.bloqueia_ressureicao = False

    registrar_passivo(ctrl, player_id, card, _aplicar, _limpar)
    _aplicar(ctrl, player_id, card)


# "No início do turno, revela a carta do topo do Baralho. Se for de Água ou
# Encantamento, compra de graça." — gatilho recorrente, sem parte passiva.
@EFFECTS.registrar("Oceano Primordial")
def _(ctrl, player_id, card, evento=None):
    from .triggers import registrar_trigger

    def _efeito(evento, ctrl):
        pid = evento.player_id
        baralho = ctrl.baralhos[pid]
        topo = baralho.topo(1)
        if not topo:
            return
        topo_card = topo[0]
        ctrl.bus.publish(TopoRevelado(player_id=pid, cartas=topo))
        info = ctrl.world.get_component(topo_card, CardInfo)
        ps = ctrl.players[pid]
        if (info.elemento is Elemento.AGUA or info.tipo is Tipo.ENCANTAMENTO) and len(ps.mao) < ps.limite_mao:
            baralho.tirar_especifica(topo_card)
            loc = ctrl.world.get_component(topo_card, Location)
            if loc:
                loc.zona = Zona.MAO
            ps.mao.append(topo_card)
            ctrl.bus.publish(CardDrawn(player_id=pid, card=topo_card, origem="efeito"))

    registrar_trigger(ctrl, TurnStarted, _efeito, origem_card=card, owner_player_id=player_id)


# "Heróis de Fogo/Vento ignoram desvantagem elemental" (passivo, reaproveita
# o componente IgnoraFraquezaElemental que Shoggoth já usa) + "Sempre que
# atacam, oponente descarta o topo do baralho" (gatilho — mill, não compra).
@EFFECTS.registrar("Céus de Valíria")
def _(ctrl, player_id, card, evento=None):
    from .triggers import registrar_passivo, registrar_trigger

    def _elegivel(ctrl, c):
        if c is None:
            return False
        info = ctrl.world.get_component(c, CardInfo)
        return info is not None and info.tipo is Tipo.HEROI and elemento_efetivo(ctrl.world, c) in (Elemento.FOGO, Elemento.VENTO)

    def _aplicar(ctrl, player_id, card):
        for pid in ctrl.jogadores:
            alvo = combatente_ativo(ctrl, pid)
            if _elegivel(ctrl, alvo) and not ctrl.world.has_component(alvo, IgnoraFraquezaElemental):
                ctrl.world.add_component(alvo, IgnoraFraquezaElemental())

    def _limpar(ctrl, card):
        for pid in ctrl.jogadores:
            alvo = combatente_ativo(ctrl, pid)
            if alvo is not None and ctrl.world.has_component(alvo, IgnoraFraquezaElemental):
                ctrl.world.remove_component(alvo, IgnoraFraquezaElemental)

    registrar_passivo(ctrl, player_id, card, _aplicar, _limpar)
    _aplicar(ctrl, player_id, card)

    def _condicao(evento, ctrl):
        return _elegivel(ctrl, evento.atacante_card)

    def _efeito(evento, ctrl):
        oponente = _oponente(ctrl, evento.atacante_player)
        baralho = ctrl.baralhos[oponente]
        topo = baralho.topo(1)
        if not topo:
            return
        topo_card = topo[0]
        baralho.tirar_especifica(topo_card)
        loc = ctrl.world.get_component(topo_card, Location)
        if loc:
            loc.zona = Zona.PILHA_DESCARTE
        ctrl.bus.publish(CardDiscarded(player_id=oponente, card=topo_card))

    registrar_trigger(ctrl, AttackDeclared, _efeito, origem_card=card, owner_player_id=player_id, condicao=_condicao)


# ---- Encantamentos -----------------------------------------------------------

@EFFECTS.registrar("Tomo do Oráculo")
def _(ctrl, player_id, card, evento=None):
    comprar(ctrl, player_id, 2)


@EFFECTS.registrar("Pacto de Sangue")
def _(ctrl, player_id, card, evento=None):
    alvo = combatente_ativo(ctrl, player_id)
    if alvo is None:
        return
    stats = ctrl.world.get_component(alvo, CombatStats)
    # dano_acumulado (não mutar atual_res direto): sobrevive a qualquer
    # recálculo futuro por outro motivo (ver CombatStats, components.py).
    stats.dano_acumulado += 5
    _recalcular_stats(ctrl.world, alvo)
    # Resistência chegando a 0 destrói o combatente, igual a QUALQUER outra
    # fonte de dano (CombatSystem, dano_combatente) — o sacrifício não é
    # isento dessa regra só por vir de um custo pago pelo próprio dono.
    if stats.atual_res <= 0:
        destruir(ctrl, alvo, "sacrificado por Pacto de Sangue")
        return
    buff(ctrl, alvo, "pow", 6, Duracao.ATE_FIM_DE_TURNO, "Pacto de Sangue")


@EFFECTS.registrar("Visão do Olho Que Tudo Vê")
def _(ctrl, player_id, card, evento=None):
    # "O oponente deve revelar sua mão. Escolha uma carta..." — quem ativa
    # e que escolhe, depois de ver a mao revelada.
    oponente = _oponente(ctrl, player_id)
    ps = ctrl.players[oponente]
    candidatas = [c for c in ps.mao if ctrl.world.get_component(c, CardInfo).tipo in (Tipo.MALDICAO, Tipo.ENCANTAMENTO)]
    if not candidatas:
        return

    def _ao_escolher(escolha: list[int]) -> None:
        escolhida = escolha[0]
        ps.mao.remove(escolhida)
        ctrl.world.get_component(escolhida, Location).zona = Zona.PILHA_DESCARTE
        ctrl.bus.publish(CardDiscarded(player_id=oponente, card=escolhida))

    ctrl.solicitar_selecao(
        player_id=player_id,
        prompt="Visão do Olho Que Tudo Vê: escolha 1 carta da mão revelada do oponente para descartar",
        opcoes=candidatas,
        on_resolved=_ao_escolher,
    )


@EFFECTS.registrar("Ressurreição Arcana")
def _(ctrl, player_id, card, evento=None):
    if getattr(ctrl, "bloqueia_ressureicao", False):
        return  # Fosso de Tártaro: nada sai do descarte enquanto ativo
    # "Escolha qualquer carta..." e uma escolha de verdade do jogador -> usa
    # o mecanismo de selecao (a GUI destaca as opcoes; resolver_selecao()
    # e chamado quando o jogador clica numa delas).
    descarte = [c for c, _ in _cartas_na_zona(ctrl, Zona.PILHA_DESCARTE) if ctrl.dono_da_carta(c) == player_id]
    if not descarte:
        return

    def _ao_escolher(escolha: list[int]) -> None:
        escolhida = escolha[0]
        ctrl.world.get_component(escolhida, Location).zona = Zona.MAO
        ctrl.players[player_id].mao.append(escolhida)

    ctrl.solicitar_selecao(
        player_id=player_id,
        prompt="Ressurreição Arcana: escolha 1 carta da Pilha de Descarte para sua mão",
        opcoes=descarte,
        on_resolved=_ao_escolher,
    )


@EFFECTS.registrar("Transmutação Elemental")
def _(ctrl, player_id, card, evento=None):
    # "Mude... para QUALQUER OUTRA" — decisão real do jogador (mirar a
    # vantagem elemental certa), não sorteio; exclui o elemento atual (não
    # seria "outra"). `opcoes` aqui são valores Elemento, não entidades — o
    # SelectionManager é genérico o bastante pra aceitar qualquer coisa
    # comparável (só a GUI Pygame, que assume carta em toda seleção, não
    # sabe desenhar essa — não é usada por nenhum script/teste desta versão).
    alvo = combatente_ativo(ctrl, player_id)
    if alvo is None:
        return
    atual = elemento_efetivo(ctrl.world, alvo)
    opcoes = [e for e in Elemento if e is not Elemento.NENHUM and e is not atual]

    def _ao_escolher(escolha: list) -> None:
        ctrl.world.add_component(alvo, ElementoOverride(elemento=escolha[0], duracao=Duracao.ATE_PROXIMO_TURNO_PROPRIO))

    ctrl.solicitar_selecao(
        player_id=player_id,
        prompt="Transmutação Elemental: escolha o novo elemento do seu combatente ativo",
        opcoes=opcoes,
        on_resolved=_ao_escolher,
    )


@EFFECTS.registrar("Desintegração de Realidade")
def _(ctrl, player_id, card, evento=None):
    # "a carta de Domínio ativa NA MESA" — sem qualificar dono. Mesmo caso de
    # Fenrir: só existe 1 Domínio ativo NO JOGO INTEIRO (compartilhado), então
    # mira esse Domínio único, mesmo que esteja do lado do próprio ativador
    # (checar só o lado do oponente deixava a carta sem alvo válido nesse
    # caso). "...ou um Equipamento ligado a um combatente inimigo" não é
    # modelado (sem subtipo Equipamento nos dados, ver topo do arquivo).
    destruir(ctrl, dominio_ativo_global(ctrl), "Desintegração de Realidade")


@EFFECTS.registrar("Vórtice Dimensional")
def _(ctrl, player_id, card, evento=None):
    oponente = _oponente(ctrl, player_id)
    retornar_ao_panteao(ctrl, oponente, combatente_ativo(ctrl, oponente))


@EFFECTS.registrar("Clarividência Divina")
def _(ctrl, player_id, card, evento=None):
    # "Descarte 1 e devolva as outras 2" — quem olha e que escolhe qual das
    # 3 descarta.
    oponente = _oponente(ctrl, player_id)
    topo = ctrl.baralhos[oponente].topo(3)
    if not topo:
        return
    ctrl.bus.publish(TopoRevelado(player_id=player_id, cartas=topo))

    def _ao_escolher(escolha: list[int]) -> None:
        escolhida = escolha[0]
        ctrl.baralhos[oponente].tirar_especifica(escolhida)
        ctrl.world.get_component(escolhida, Location).zona = Zona.PILHA_DESCARTE
        ctrl.bus.publish(CardDiscarded(player_id=oponente, card=escolhida))

    ctrl.solicitar_selecao(
        player_id=player_id,
        prompt="Clarividência Divina: escolha 1 das 3 cartas do topo do baralho inimigo para descartar",
        opcoes=topo,
        on_resolved=_ao_escolher,
    )


@EFFECTS.registrar("Bênção de Yggdrasil")
def _(ctrl, player_id, card, evento=None):
    comprar(ctrl, player_id, 2)
    if len(ctrl.players[player_id].mao) <= 1:
        comprar(ctrl, player_id, 1)


@EFFECTS.registrar("Fúria Titânica")
def _(ctrl, player_id, card, evento=None):
    alvo = combatente_ativo(ctrl, player_id)
    if alvo is None:
        return
    buff(ctrl, alvo, "pow", 8, Duracao.NESTE_TURNO, "Fúria Titânica")
    # "Fim do turno sofre debuff permanente de -4 de Resistência" — o texto
    # separa os dois momentos ("neste turno" vs. "fim do turno"): o debuff só
    # bate na Fase Final DAQUELE turno, não na hora de jogar a carta (o
    # combatente aproveita o ataque forte sem pagar o preço imediatamente).
    # Gatilho amarrado ao próprio alvo: se ele morrer/sair de campo antes da
    # Fase Final, o gatilho é removido junto (remover_triggers_de), sem
    # debuff pendurado num combatente que já não existe mais.
    from .triggers import registrar_trigger

    def _condicao_aplica(evento, ctrl):
        return evento.fase_nova is Fase.FINAL and evento.player_id == player_id

    def _aplicar_debuff(evento, ctrl):
        buff(ctrl, alvo, "res", -4, Duracao.PERMANENTE, "Fúria Titânica")

    registrar_trigger(ctrl, PhaseChanged, _aplicar_debuff, origem_card=alvo, owner_player_id=player_id,
                       condicao=_condicao_aplica, persistente=False)


@EFFECTS.registrar("Troca Equivalente")
def _(ctrl, player_id, card, evento=None):
    # "Embaralhe ATÉ 3 cartas da mão" — escolha real do jogador (mulligan
    # seletivo, pra se livrar de cartas específicas), não sorteio; até 3
    # escolhas de 1 em 1 (mesmo padrão de Purificação Arcana), com opção de
    # parar antes via "Pular" (minimo=0).
    from .actions import ShuffleAction
    ps = ctrl.players[player_id]
    escolhidas: list[int] = []

    def _finalizar() -> None:
        if not escolhidas:
            return
        ShuffleAction(deck=ctrl.baralhos[player_id], devolver=list(escolhidas)).executar(ctrl)
        comprar(ctrl, player_id, len(escolhidas))

    def _pedir_uma(restantes: int) -> None:
        if restantes <= 0 or not ps.mao:
            _finalizar()
            return

        def _ao_escolher(escolha: list[int]) -> None:
            if not escolha:
                _finalizar()
                return
            escolhida = escolha[0]
            ps.mao.remove(escolhida)
            escolhidas.append(escolhida)
            _pedir_uma(restantes - 1)

        ctrl.solicitar_selecao(
            player_id=player_id,
            prompt=f"Troca Equivalente: escolha uma carta da mão pra embaralhar de volta (restam até {restantes}, ou pule)",
            opcoes=list(ps.mao),
            on_resolved=_ao_escolher,
            minimo=0, maximo=1,
        )

    _pedir_uma(3)


@EFFECTS.registrar("Exílio Dimensional")
def _(ctrl, player_id, card, evento=None):
    oponente = _oponente(ctrl, player_id)
    destruir(ctrl, combatente_ativo(ctrl, oponente), "Exílio Dimensional")
    # "invoca outro de graça" exige escolha do oponente -> deixado para a
    # camada de selecao (GUI/bot) chamar SummonAction sem custo em seguida.


@EFFECTS.registrar("Chamado do Além")
def _(ctrl, player_id, card, evento=None):
    if getattr(ctrl, "bloqueia_ressureicao", False):
        return  # Fosso de Tártaro: nada sai do descarte enquanto ativo
    # "Escolha uma carta de Maldição/Equipamento da Pilha de Descarte" —
    # escolha de verdade. Simplificado (como ja era): volta pra mao em vez
    # de campo direto, mas setar uma Maldição ja e gratis, entao o efeito
    # pratico e quase o mesmo.
    ps = ctrl.players[player_id]
    descarte = [c for c, _ in _cartas_na_zona(ctrl, Zona.PILHA_DESCARTE)
                if ctrl.dono_da_carta(c) == player_id
                and ctrl.world.get_component(c, CardInfo).tipo is Tipo.MALDICAO]
    if not descarte:
        return

    def _ao_escolher(escolha: list[int]) -> None:
        escolhida = escolha[0]
        ctrl.world.get_component(escolhida, Location).zona = Zona.MAO
        ps.mao.append(escolhida)

    ctrl.solicitar_selecao(
        player_id=player_id,
        prompt="Chamado do Além: escolha 1 Maldição da Pilha de Descarte para sua mão",
        opcoes=descarte,
        on_resolved=_ao_escolher,
    )


@EFFECTS.registrar("Purificação Arcana")
def _(ctrl, player_id, card, evento=None):
    # "Destrua duas delas" — duas escolhas de verdade, uma de cada vez
    # (reaproveita o mesmo mecanismo de selecao unica em sequencia).
    oponente = _oponente(ctrl, player_id)

    def _pedir_uma(restantes: int) -> None:
        if restantes <= 0:
            return
        lado = ctrl.board.lado(oponente)
        maldicoes = [c for c in lado.magia if c is not None and ctrl.world.has_component(c, FaceDown)]
        if not maldicoes:
            return

        def _ao_escolher(escolha: list[int]) -> None:
            destruir(ctrl, escolha[0], "Purificação Arcana")
            _pedir_uma(restantes - 1)

        ctrl.solicitar_selecao(
            player_id=player_id,
            prompt=f"Purificação Arcana: escolha uma Maldição do oponente para destruir (restam {restantes})",
            opcoes=maldicoes,
            on_resolved=_ao_escolher,
        )

    _pedir_uma(2)


@EFFECTS.registrar("Manto da Natureza")
def _(ctrl, player_id, card, evento=None):
    alvo = combatente_ativo(ctrl, player_id)
    if alvo is not None:
        buff(ctrl, alvo, "res", 5, Duracao.PERMANENTE, "Manto da Natureza")
        # "imunidade a Habilidades de Mana inimigas" — checado por Minotauro
        # (Labirinto), Amnésia Mágica e Roubo de Essência antes de agir.
        ctrl.world.add_component(alvo, ImuneAHabilidadesInimigas())


# ---- Encantamentos Contínuos (GAME_DESIGN.md) ----------------------------
#
# Custo de Mana 0 de propósito — o "custo" real é o sacrifício pago no
# próprio efeito (descarte, Pontos de Vida, POW/RES). Diferente de um
# Encantamento Simples/Equipamento, ficam em campo (PlayEnchantmentAction
# checa CardInfo.tipo_encantamento is TipoEncantamento.CONTINUO — coluna
# "Tipo de Encantamento" do CSV) enquanto o bônus de +Mana por turno
# estiver ativo — mesmo padrão de
# registrar_passivo/limpa-e-reaplica já usado pelos Domínios (Vulcão
# Primordial, Jardins Suspensos...), só que somando num contador por
# JOGADOR (ctrl.bonus_mana_por_turno) em vez de um StatusEffect por carta,
# já que o que essas cartas afetam é a economia de Mana do turno, não POW/RES
# de um combatente.

@EFFECTS.registrar("Oásis do Saara")
def _(ctrl, player_id, card, evento=None):
    from .triggers import registrar_passivo

    descartar_aleatorias(ctrl, player_id, 1)  # sacrifício: descarte 1 carta da mão (se houver)

    def _aplicar(ctrl, player_id, card):
        ctrl.bonus_mana_por_turno[player_id] = ctrl.bonus_mana_por_turno.get(player_id, 0) + 1

    def _limpar(ctrl, card):
        ctrl.bonus_mana_por_turno[player_id] = ctrl.bonus_mana_por_turno.get(player_id, 0) - 1

    registrar_passivo(ctrl, player_id, card, _aplicar, _limpar)
    _aplicar(ctrl, player_id, card)


@EFFECTS.registrar("Geleiras do Ártico")
def _(ctrl, player_id, card, evento=None):
    from .triggers import registrar_passivo

    dano_jogador(ctrl, player_id, 3, "Geleiras do Ártico")  # sacrifício: 3 de vida do próprio dono

    def _aplicar(ctrl, player_id, card):
        ctrl.bonus_mana_por_turno[player_id] = ctrl.bonus_mana_por_turno.get(player_id, 0) + 1

    def _limpar(ctrl, card):
        ctrl.bonus_mana_por_turno[player_id] = ctrl.bonus_mana_por_turno.get(player_id, 0) - 1

    registrar_passivo(ctrl, player_id, card, _aplicar, _limpar)
    _aplicar(ctrl, player_id, card)


@EFFECTS.registrar("Selva Amazônica")
def _(ctrl, player_id, card, evento=None):
    from .triggers import registrar_passivo

    # sacrifício: o próprio combatente em campo perde 2/2 permanentemente
    # (se não houver combatente, o sacrifício simplesmente não se aplica —
    # mesma leniência de Pacto de Sangue).
    alvo = combatente_ativo(ctrl, player_id)
    if alvo is not None:
        buff(ctrl, alvo, "pow", -2, Duracao.PERMANENTE, "Selva Amazônica")
        buff(ctrl, alvo, "res", -2, Duracao.PERMANENTE, "Selva Amazônica")

    def _aplicar(ctrl, player_id, card):
        ctrl.bonus_mana_por_turno[player_id] = ctrl.bonus_mana_por_turno.get(player_id, 0) + 2

    def _limpar(ctrl, card):
        ctrl.bonus_mana_por_turno[player_id] = ctrl.bonus_mana_por_turno.get(player_id, 0) - 2

    registrar_passivo(ctrl, player_id, card, _aplicar, _limpar)
    _aplicar(ctrl, player_id, card)


# ---- Maldições -----------------------------------------------------------
#
# GAME_DESIGN.md: "Revelar/ativar uma Maldição já setada: a qualquer momento
# no turno do OPONENTE." O motor nunca revela uma Maldição sozinho: sempre
# que um evento bate com o gatilho declarado (EFFECTS.registrar_gatilho_maldicao)
# de alguma Maldição virada pra baixo de quem NÃO está na vez, uma seleção
# pergunta pro dono se quer ativá-la agora (curses.ofertar_maldicoes_reativas)
# — o motor PARA (mesmo `ctrl.solicitar_selecao` de sempre) até essa decisão.
# O efeito roda na hora da decisão, com o `evento` que motivou a oferta ainda
# disponível — por isso lê o alvo direto dele quando o texto pede algo
# específico (ex.: "o combatente INVOCADO"), com fallback pro combatente
# ativo/mão atual pra continuar funcionando se a carta for revelada
# manualmente (sem um evento associado).

@EFFECTS.registrar("Escudo de Gelo Absoluto")
def _(ctrl, player_id, card, evento=None):
    # "O ataque e negado" protege quem ATIVOU a Maldicao (e quem esta sendo
    # atacado quando isso dispara) — negar_proximo_ataque tem que ir no
    # PROPRIO combatente do ativador, nao no do oponente. "o combatente
    # inimigo perde seu elemento" e que mira o oponente.
    oponente = _oponente(ctrl, player_id)
    if protegido_contra_maldicao(ctrl, oponente):
        return
    proprio = (evento.defensor_card if evento else None) or combatente_ativo(ctrl, player_id)
    if proprio:
        negar_proximo_ataque(ctrl, proprio)
    inimigo = (evento.atacante_card if evento else None) or combatente_ativo(ctrl, oponente)
    if inimigo:
        ctrl.world.add_component(inimigo, ElementoOverride(elemento=Elemento.NENHUM, duracao=Duracao.ATE_FIM_DE_TURNO))


EFFECTS.registrar_gatilho_maldicao("Escudo de Gelo Absoluto", AttackDeclared,
                                    lambda evento, ctrl, dono_id: evento.defensor_player == dono_id)


@EFFECTS.registrar("Espelho das Ilusões")
def _(ctrl, player_id, card, evento=None):
    if protegido_contra_maldicao(ctrl, _oponente(ctrl, player_id)):
        return
    alvo = (evento.defensor_card if evento else None) or combatente_ativo(ctrl, player_id)
    if alvo:
        refletir_dano(ctrl, alvo)


EFFECTS.registrar_gatilho_maldicao("Espelho das Ilusões", AttackDeclared,
                                    lambda evento, ctrl, dono_id: evento.defensor_player == dono_id)


@EFFECTS.registrar("Areias Movediças")
def _(ctrl, player_id, card, evento=None):
    oponente = _oponente(ctrl, player_id)
    if protegido_contra_maldicao(ctrl, oponente):
        return
    alvo = (evento.card if evento else None) or combatente_ativo(ctrl, oponente)
    if alvo:
        buff(ctrl, alvo, "res", -5, Duracao.PERMANENTE, "Areias Movediças")


EFFECTS.registrar_gatilho_maldicao("Areias Movediças", CombatantSummoned,
                                    lambda evento, ctrl, dono_id: evento.player_id != dono_id)


@EFFECTS.registrar("Roubo de Essência")
def _(ctrl, player_id, card, evento=None):
    oponente = _oponente(ctrl, player_id)
    if protegido_contra_maldicao(ctrl, oponente):
        return
    if evento and evento.card and ctrl.world.has_component(evento.card, ImuneAHabilidadesInimigas):
        return  # Manto da Natureza
    # simplificado (como já era): não cancela de fato o efeito da Habilidade
    # ativada (não há uma noção separada de "Habilidade de Mana" nos dados),
    # só rouba a Mana que ela custou.
    if evento and evento.card:
        ability = ctrl.world.get_component(evento.card, AbilityCost)
        custo = ability.valor if ability else 0
    else:
        custo = 99
    roubado = perder_mana(ctrl, oponente, custo)
    ganhar_mana(ctrl, player_id, roubado)


EFFECTS.registrar_gatilho_maldicao("Roubo de Essência", AbilityActivated,
                                    lambda evento, ctrl, dono_id: evento.player_id != dono_id)


@EFFECTS.registrar("Praga da Ferrugem")
def _(ctrl, player_id, card, evento=None):
    oponente = _oponente(ctrl, player_id)
    if protegido_contra_maldicao(ctrl, oponente):
        return
    perder_mana(ctrl, oponente, 1)


# sem gatilho declarado: depende de "Equipamento", que não existe nos dados
# desta versão — não é oferecida no modal reativo, só pode ser descartada
# por outro efeito (ex.: Purificação Arcana) nesta versão.


@EFFECTS.registrar("Vínculo Sombrio")
def _(ctrl, player_id, card, evento=None):
    oponente = _oponente(ctrl, player_id)
    if protegido_contra_maldicao(ctrl, oponente):
        return
    alvo = (evento.atacante_card if evento else None) or combatente_ativo(ctrl, oponente)
    if alvo:
        stats = ctrl.world.get_component(alvo, CombatStats)
        buff(ctrl, alvo, "pow", 10 - stats.atual_pow, Duracao.ATE_FIM_DE_TURNO, "Vínculo Sombrio")


EFFECTS.registrar_gatilho_maldicao("Vínculo Sombrio", AttackDeclared,
                                    lambda evento, ctrl, dono_id: evento.defensor_player == dono_id)


@EFFECTS.registrar("Nevoeiro do Pânico")
def _(ctrl, player_id, card, evento=None):
    oponente = _oponente(ctrl, player_id)
    if protegido_contra_maldicao(ctrl, oponente):
        return
    ps = ctrl.players[oponente]
    carta_comprada = evento.card if evento else None
    if carta_comprada and carta_comprada in ps.mao:
        ps.mao.remove(carta_comprada)
        loc = ctrl.world.get_component(carta_comprada, Location)
        if loc:
            loc.zona = Zona.PILHA_DESCARTE
        ctrl.bus.publish(CardDiscarded(player_id=oponente, card=carta_comprada))
    else:
        descartar_aleatorias(ctrl, oponente, 1)  # fallback p/ revelação manual sem evento associado
    baralho = ctrl.baralhos[oponente]
    restantes = baralho.restantes()
    if not restantes:
        return
    do_fundo = restantes[-1]
    baralho.tirar_especifica(do_fundo)
    loc = ctrl.world.get_component(do_fundo, Location)
    if loc:
        loc.zona = Zona.MAO
    ps.mao.append(do_fundo)
    ctrl.bus.publish(CardDrawn(player_id=oponente, card=do_fundo, origem="efeito"))


# "a carta recém comprada NO TURNO" = a compra automática da Fase de Saque
# (origem "turno" — ver ResourceSystem), não uma compra de efeito.
EFFECTS.registrar_gatilho_maldicao("Nevoeiro do Pânico", CardDrawn,
                                    lambda evento, ctrl, dono_id: evento.player_id != dono_id and evento.origem == "turno")


@EFFECTS.registrar("Barreira de Vento Cortante")
def _(ctrl, player_id, card, evento=None):
    # "O ataque e negado" protege o PROPRIO combatente de quem ativou a
    # Maldicao; "o atacante retorna ao Panteao" manda o combatente do
    # OPONENTE de volta.
    oponente = _oponente(ctrl, player_id)
    if protegido_contra_maldicao(ctrl, oponente):
        return
    proprio = (evento.defensor_card if evento else None) or combatente_ativo(ctrl, player_id)
    if proprio:
        negar_proximo_ataque(ctrl, proprio)
    inimigo = (evento.atacante_card if evento else None) or combatente_ativo(ctrl, oponente)
    retornar_ao_panteao(ctrl, oponente, inimigo)


EFFECTS.registrar_gatilho_maldicao("Barreira de Vento Cortante", AttackDeclared,
                                    lambda evento, ctrl, dono_id: evento.defensor_player == dono_id)


@EFFECTS.registrar("Retribuição Kármica")
def _(ctrl, player_id, card, evento=None):
    if protegido_contra_maldicao(ctrl, _oponente(ctrl, player_id)):
        return
    alvo = (evento.defensor_card if evento else None) or combatente_ativo(ctrl, player_id)
    if alvo:
        refletir_dano(ctrl, alvo)


EFFECTS.registrar_gatilho_maldicao("Retribuição Kármica", AttackDeclared,
                                    lambda evento, ctrl, dono_id: evento.defensor_player == dono_id)


@EFFECTS.registrar("Aperto da Múmia")
def _(ctrl, player_id, card, evento=None):
    oponente = _oponente(ctrl, player_id)
    if protegido_contra_maldicao(ctrl, oponente):
        return
    alvo = (evento.card if evento else None) or combatente_ativo(ctrl, oponente)
    if alvo:
        buff(ctrl, alvo, "res", -5, Duracao.PERMANENTE, "Aperto da Múmia")
        buff(ctrl, alvo, "pow", -3, Duracao.PERMANENTE, "Aperto da Múmia")


EFFECTS.registrar_gatilho_maldicao("Aperto da Múmia", CombatantSummoned,
                                    lambda evento, ctrl, dono_id: evento.player_id != dono_id)


@EFFECTS.registrar("Mente Fraturada")
def _(ctrl, player_id, card, evento=None):
    oponente = _oponente(ctrl, player_id)
    if protegido_contra_maldicao(ctrl, oponente):
        return
    ps = ctrl.players[oponente]
    if not ps.mao:
        return
    pior = max(ps.mao, key=lambda c: ctrl.world.get_component(c, ManaCost).valor)
    ps.mao.remove(pior)
    loc = ctrl.world.get_component(pior, Location)
    if loc:
        loc.zona = Zona.PILHA_DESCARTE
    ctrl.bus.publish(CardDiscarded(player_id=oponente, card=pior))


# "ao tentar comprar cartas EXTRAS" = origem "efeito" (Tomo do Oráculo,
# Bênção de Yggdrasil...), não a compra normal de início de turno.
EFFECTS.registrar_gatilho_maldicao("Mente Fraturada", CardDrawn,
                                    lambda evento, ctrl, dono_id: evento.player_id != dono_id and evento.origem == "efeito")


@EFFECTS.registrar("Amnésia Mágica")
def _(ctrl, player_id, card, evento=None):
    oponente = _oponente(ctrl, player_id)
    if protegido_contra_maldicao(ctrl, oponente):
        return
    # "a Habilidade de Mana falha e o combatente perde o direito de usar
    # habilidades" — simplificado (como já era) pra "essa ativação já era" +
    # bloqueia o resto do turno.
    alvo = (evento.card if evento else None) or combatente_ativo(ctrl, oponente)
    if alvo is not None and ctrl.world.has_component(alvo, ImuneAHabilidadesInimigas):
        return  # Manto da Natureza
    ability = ctrl.world.get_component(alvo, AbilityCost) if alvo else None
    if ability:
        ability.usada_neste_turno = True


EFFECTS.registrar_gatilho_maldicao("Amnésia Mágica", AbilityActivated,
                                    lambda evento, ctrl, dono_id: evento.player_id != dono_id)


@EFFECTS.registrar("Fio do Destino Cortado")
def _(ctrl, player_id, card, evento=None):
    oponente = _oponente(ctrl, player_id)
    if protegido_contra_maldicao(ctrl, oponente):
        return
    alvo = (evento.card if evento else None) or combatente_ativo(ctrl, oponente)
    statuses = ctrl.world.get_component(alvo, StatusEffects) if alvo else None
    if statuses:
        for st in statuses.itens:
            st.magnitude = -st.magnitude
        _recalcular_stats(ctrl.world, alvo)


# aproximação de "buff ativado": a maioria dos buffs vem de Habilidade.
EFFECTS.registrar_gatilho_maldicao("Fio do Destino Cortado", AbilityActivated,
                                    lambda evento, ctrl, dono_id: evento.player_id != dono_id)


@EFFECTS.registrar("Rebote Arcano")
def _(ctrl, player_id, card, evento=None):
    pass  # exige rastrear "o proximo feitico inimigo" -- nao modelado nesta versao


@EFFECTS.registrar("Caixa de Pandora")
def _(ctrl, player_id, card, evento=None):
    # diferente das outras Maldições reativas, não faz sentido nenhum
    # "efeito de fallback" pra Caixa de Pandora sem o evento de destruição
    # que a motivou — sem ele, revelar a carta (fora do modal reativo) não
    # faz nada.
    if evento is None:
        return
    descartar_aleatorias(ctrl, _oponente(ctrl, player_id), 3)


def _gatilho_caixa_de_pandora(evento, ctrl, dono_id):
    if ctrl.dono_da_carta(evento.card) != dono_id:
        return False
    info = ctrl.world.get_component(evento.card, CardInfo)
    stats = ctrl.world.get_component(evento.card, CombatStats)
    return (info is not None and info.tipo is Tipo.DOMINIO) or stats is not None


# "Ao ter Domínio/Combatente destruído" = quando uma carta DO DONO da Caixa
# de Pandora (não ela mesma) morre — fix de um gatilho errado que existia
# antes desta refatoração (disparava quando a PRÓPRIA Caixa de Pandora era
# destruída, condição diferente da do texto).
EFFECTS.registrar_gatilho_maldicao("Caixa de Pandora", CardDestroyed, _gatilho_caixa_de_pandora)


def _cartas_na_zona(ctrl, zona):
    for eid, loc in ctrl.world.query(Location):
        if loc.zona is zona:
            yield eid, loc
