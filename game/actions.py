# -*- coding: utf-8 -*-
"""Acoes do Jogador (GAME_DESIGN.md, 'Vocabulario de Mecanicas'). Cada Acao e
um objeto com `.validar(ctrl)` e `.executar(ctrl)`, chamado sempre via
`GameController.submeter_acao(acao)` — nunca direto — pra todo mundo passar
pela mesma validacao de fase/custo/mana."""
from __future__ import annotations

from dataclasses import dataclass, field

from .components import (
    AbilityCost, AttackedThisTurn, CardInfo, Fase, FaceDown, Location,
    ManaCost, TipoEncantamento, Zona,
)
from .deck import Deck
from .events import (
    AbilityActivated, AttackDeclared, CombatantSummoned, CursePlaced,
    DeckShuffled, DomainActivated, EnchantmentPlayed, ManaChanged,
)


class AcaoInvalida(RuntimeError):
    pass


def _pagar_mana(ctrl, player_id: int, custo: int) -> None:
    ps = ctrl.players[player_id]
    if ps.mana < custo:
        raise AcaoInvalida(f"Mana insuficiente: precisa de {custo}, tem {ps.mana}.")
    ps.mana -= custo
    ctrl.bus.publish(ManaChanged(player_id=player_id, delta=-custo, total=ps.mana))


def _exigir_fase(ctrl, player_id: int, *fases: Fase) -> None:
    ts = ctrl.fase_system.estado_atual(ctrl.world)
    if ts.jogador_da_vez != player_id:
        raise AcaoInvalida("Nao e a vez desse jogador.")
    if ts.fase not in fases:
        nomes = "/".join(f.name for f in fases)
        raise AcaoInvalida(f"Acao exige a Fase {nomes}, mas o jogo esta na Fase {ts.fase.name}.")


@dataclass
class SummonAction:
    """Fase de Invocacao: traz um Combatente do Panteao pro unico slot de
    Monstro do tabuleiro. Custo: Custo de Mana da carta."""
    player_id: int
    card: int

    def executar(self, ctrl) -> None:
        _exigir_fase(ctrl, self.player_id, Fase.INVOCACAO)
        lado = ctrl.board.lado(self.player_id)
        if lado.monstro is not None:
            raise AcaoInvalida("Ja ha um combatente ativo neste lado do tabuleiro.")

        panteao = ctrl.panteoes[self.player_id]
        custo = ctrl.world.get_component(self.card, ManaCost).valor
        _pagar_mana(ctrl, self.player_id, custo)

        panteao.tirar_especifica(self.card)
        # zera "Habilidade usada neste turno" ao ENTRAR em campo — sem isso,
        # um combatente que usou a Habilidade, voltou ao Panteão no mesmo
        # turno (ex.: Cânion dos Ventos) e foi invocado de novo depois
        # ficaria com a flag travada em True pra sempre (o upkeep só reseta
        # quem já está em campo, game/phases.py UpkeepSystem).
        ability = ctrl.world.get_component(self.card, AbilityCost)
        if ability is not None:
            ability.usada_neste_turno = False
        # mesma lógica pro "já atacou neste turno" (Cânion dos Ventos): sem
        # isso, um combatente que atacou, voltou ao Panteão e foi invocado
        # de novo no MESMO turno ficaria impedido de atacar de novo. Já é
        # redundante com o reset feito em retornar_ao_panteao, mas mantido
        # aqui também por defesa (mesmo padrão do reset de AbilityCost acima).
        if ctrl.world.has_component(self.card, AttackedThisTurn):
            ctrl.world.remove_component(self.card, AttackedThisTurn)
        lado.colocar_monstro(self.card)
        loc = ctrl.world.get_component(self.card, Location)
        if loc:
            loc.zona = Zona.CAMPO_MONSTRO
        else:
            ctrl.world.add_component(self.card, Location(zona=Zona.CAMPO_MONSTRO))

        evento = CombatantSummoned(player_id=self.player_id, card=self.card)
        ctrl.bus.publish(evento)

        from .curses import ofertar_maldicoes_reativas
        ofertar_maldicoes_reativas(ctrl, evento)


@dataclass
class SwapCombatantAction:
    """Fase Principal: abre o Panteão e invoca um Combatente de lá, pagando
    o Custo de Mana normal — MESMO com um combatente já ativo em campo,
    caso em que ele é DESTRUÍDO antes (não devolvido ao Panteão: vai pra
    Pilha de Descarte e dispara qualquer gatilho "ao ser destruído", igual
    a qualquer outra destruição). Complementa a Invocação normal (Fase de
    Invocação, só serve com o slot vazio), dando ao jogador a opção de
    trocar de combatente no meio do turno pagando o preço de destruir o
    que já tinha — não há limite de vezes por turno além da Mana
    disponível."""
    player_id: int
    card: int

    def executar(self, ctrl) -> None:
        _exigir_fase(ctrl, self.player_id, Fase.PRINCIPAL)
        panteao = ctrl.panteoes[self.player_id]
        if self.card not in panteao.restantes():
            raise AcaoInvalida("Essa carta nao esta no Panteao desse jogador.")

        custo = ctrl.world.get_component(self.card, ManaCost).valor
        _pagar_mana(ctrl, self.player_id, custo)

        lado = ctrl.board.lado(self.player_id)
        anterior = lado.monstro
        if anterior is not None:
            ctrl.destruction_system.destruir(
                ctrl.world, anterior, motivo="substituído por invocação na Fase Principal")

        # destruir o combatente anterior pode disparar gatilhos de terceiros
        # (ex.: Caixa de Pandora força um descarte aleatório) que, em tese,
        # poderiam tirar justo ESTA carta do Panteão antes dela ser invocada
        # — confere de novo em vez de deixar tirar_especifica estourar.
        if self.card not in panteao.restantes():
            raise AcaoInvalida("Essa carta saiu do Panteão por um efeito antes de poder ser invocada.")
        panteao.tirar_especifica(self.card)
        # mesmo reset de flags de turno da Invocação normal (ver SummonAction
        # acima) — sem isso, um combatente que já usou a Habilidade ou já
        # atacou noutra passagem pelo campo neste turno (Cânion dos Ventos)
        # ficaria travado ao voltar.
        ability = ctrl.world.get_component(self.card, AbilityCost)
        if ability is not None:
            ability.usada_neste_turno = False
        if ctrl.world.has_component(self.card, AttackedThisTurn):
            ctrl.world.remove_component(self.card, AttackedThisTurn)
        lado.colocar_monstro(self.card)
        loc = ctrl.world.get_component(self.card, Location)
        if loc:
            loc.zona = Zona.CAMPO_MONSTRO
        else:
            ctrl.world.add_component(self.card, Location(zona=Zona.CAMPO_MONSTRO))

        evento = CombatantSummoned(player_id=self.player_id, card=self.card)
        ctrl.bus.publish(evento)

        from .curses import ofertar_maldicoes_reativas
        ofertar_maldicoes_reativas(ctrl, evento)


@dataclass
class ActivateAbilityAction:
    """Fase Tatica ou de Combate, 1x por turno: paga o Custo de Habilidade
    (losango) e dispara o efeito da carta (game/effects.py)."""
    player_id: int
    card: int

    def executar(self, ctrl) -> None:
        _exigir_fase(ctrl, self.player_id, Fase.PRINCIPAL, Fase.BATALHA)
        lado = ctrl.board.lado(self.player_id)
        if lado.monstro != self.card:
            raise AcaoInvalida("Essa carta nao e o combatente ativo desse jogador.")

        ability = ctrl.world.get_component(self.card, AbilityCost)
        if ability is None:
            raise AcaoInvalida("Essa carta nao tem Habilidade ativavel.")
        if ability.usada_neste_turno:
            raise AcaoInvalida("Habilidade ja usada neste turno.")

        _pagar_mana(ctrl, self.player_id, ability.valor)
        ability.usada_neste_turno = True
        evento = AbilityActivated(player_id=self.player_id, card=self.card)
        ctrl.bus.publish(evento)

        # a decisão de Maldição reativa (ex.: Roubo de Essência) acontece
        # ANTES do efeito da própria Habilidade resolver.
        def _continuar() -> None:
            info = ctrl.world.get_component(self.card, CardInfo)
            ctrl.effects.executar(ctrl, info.nome, self.player_id, self.card)

        from .curses import ofertar_maldicoes_reativas
        ofertar_maldicoes_reativas(ctrl, evento, _continuar)


@dataclass
class ActivateDomainAction:
    """Fase Tatica: ativa um Dominio da mao. So pode haver 1 ativo NO JOGO
    INTEIRO — "só pode haver um ativo na mesa" (GAME_DESIGN.md) e a mesa
    compartilhada dos dois jogadores, nao uma por lado. Ativar um novo
    destroi QUALQUER Dominio ja ativo, seja de quem for."""
    player_id: int
    card: int
    slot: int | None = None

    def executar(self, ctrl) -> None:
        _exigir_fase(ctrl, self.player_id, Fase.PRINCIPAL)
        ps = ctrl.players[self.player_id]
        if self.card not in ps.mao:
            raise AcaoInvalida("Essa carta nao esta na mao desse jogador.")

        custo = ctrl.world.get_component(self.card, ManaCost).valor
        _pagar_mana(ctrl, self.player_id, custo)

        lado = ctrl.board.lado(self.player_id)
        anterior = lado.dominio_ativo(ctrl.world, ctrl.dominio_cards)
        if anterior is not None:
            ctrl.destruction_system.destruir(ctrl.world, anterior, motivo="substituido por novo Domínio")
        lado_oponente = ctrl.board.lado(ctrl.oponente_de(self.player_id))
        anterior_oponente = lado_oponente.dominio_ativo(ctrl.world, ctrl.dominio_cards)
        if anterior_oponente is not None:
            ctrl.destruction_system.destruir(ctrl.world, anterior_oponente, motivo="substituido por novo Domínio")

        # checa ANTES de tirar da mao — senao, se nao houver slot livre, a
        # carta seria removida da mao sem ir pra lugar nenhum (perdida).
        if self.slot is None and not lado.slots_livres():
            raise AcaoInvalida("Nao ha slot de magia livre (limite de 5) pra ativar o Domínio.")

        # destruir o Domínio anterior pode disparar gatilhos de terceiros
        # (ex.: Caixa de Pandora força um descarte aleatorio) que, em tese,
        # poderiam pegar justo ESTA carta ainda na mao antes dela ser
        # colocada em campo — confere de novo em vez de deixar um
        # ValueError estourar.
        if self.card not in ps.mao:
            raise AcaoInvalida("Essa carta foi descartada por um efeito antes de poder ser ativada.")
        ps.mao.remove(self.card)
        slot = lado.colocar_magia(self.card, self.slot)
        ctrl.world.add_component(self.card, Location(zona=Zona.CAMPO_MAGIA, slot=slot))
        ctrl.bus.publish(DomainActivated(player_id=self.player_id, card=self.card, dominio_substituido=anterior))

        info = ctrl.world.get_component(self.card, CardInfo)
        ctrl.effects.executar(ctrl, info.nome, self.player_id, self.card)


@dataclass
class PlayEnchantmentAction:
    """Fase Tatica: joga um Encantamento da mao. Resolve na hora e vai pra
    Pilha de Descarte — exceto dois Tipo de Encantamento que ficam em campo,
    num slot de magia (GAME_DESIGN.md):
      - CONTINUO: enquanto o bônus de +Mana por turno estiver ativo.
      - EQUIPAMENTO: "vestido" no combatente ativo no momento de jogar —
        some (vai pro Descarte) quando ESSE combatente for destruído, ou
        quando o próprio Equipamento for destruído por outro efeito (essa
        segunda metade já vem de graça do próprio efeito da carta usar
        `registrar_passivo` — ver, ex., Manto da Natureza em effects.py)."""
    player_id: int
    card: int
    slot: int | None = None

    def executar(self, ctrl) -> None:
        _exigir_fase(ctrl, self.player_id, Fase.PRINCIPAL)
        ps = ctrl.players[self.player_id]
        if self.card not in ps.mao:
            raise AcaoInvalida("Essa carta nao esta na mao desse jogador.")

        info = ctrl.world.get_component(self.card, CardInfo)
        continuo = info.tipo_encantamento is TipoEncantamento.CONTINUO
        equipamento = info.tipo_encantamento is TipoEncantamento.EQUIPAMENTO
        fica_em_campo = continuo or equipamento
        lado = ctrl.board.lado(self.player_id)
        if equipamento and lado.monstro is None:
            raise AcaoInvalida("Não há combatente ativo pra equipar.")
        if fica_em_campo and self.slot is None and not lado.slots_livres():
            raise AcaoInvalida("Não há slot de magia livre (limite de 5) pra jogar este Encantamento.")

        custo = ctrl.world.get_component(self.card, ManaCost).valor
        _pagar_mana(ctrl, self.player_id, custo)
        ps.mao.remove(self.card)

        # o alvo do Equipamento e fixado AGORA (o combatente ativo no
        # instante de jogar) — antes do efeito da carta rodar e antes dela
        # ir pro slot de magia. Fica preso a essa entidade especifica
        # mesmo que ela volte ao Panteao sem ser destruida depois.
        alvo_equipado = lado.monstro if equipamento else None

        ctrl.bus.publish(EnchantmentPlayed(player_id=self.player_id, card=self.card))
        ctrl.effects.executar(ctrl, info.nome, self.player_id, self.card)

        loc = ctrl.world.get_component(self.card, Location)
        if fica_em_campo:
            slot = lado.colocar_magia(self.card, self.slot)
            loc.zona = Zona.CAMPO_MAGIA
            loc.slot = slot
            if equipamento and alvo_equipado is not None:
                from .events import CardDestroyed
                from .triggers import registrar_trigger
                registrar_trigger(
                    ctrl, CardDestroyed,
                    lambda evento, ctrl, card=self.card: ctrl.destruction_system.destruir(
                        ctrl.world, card, motivo="combatente equipado foi destruído"),
                    origem_card=self.card, owner_player_id=self.player_id,
                    condicao=lambda evento, ctrl, alvo=alvo_equipado: evento.card == alvo,
                )
        else:
            loc.zona = Zona.PILHA_DESCARTE


@dataclass
class SetCurseAction:
    """Fase Tatica: baixa uma Maldicao virada pra baixo num slot de magia.
    Setar e de graca — o Custo de Mana da carta so e cobrado na hora de
    revelar/ativar (ver ActivateSetCurseAction), nao aqui."""
    player_id: int
    card: int
    slot: int | None = None

    def executar(self, ctrl) -> None:
        _exigir_fase(ctrl, self.player_id, Fase.PRINCIPAL)
        ps = ctrl.players[self.player_id]
        if self.card not in ps.mao:
            raise AcaoInvalida("Essa carta nao esta na mao desse jogador.")

        lado = ctrl.board.lado(self.player_id)
        # checa ANTES de tirar da mao — senao, se nao houver slot livre, a
        # carta seria removida da mao sem ir pra lugar nenhum (perdida).
        if self.slot is None and not lado.slots_livres():
            raise AcaoInvalida("Nao ha slot de magia livre (limite de 5) pra setar a Maldição.")

        ps.mao.remove(self.card)
        slot = lado.colocar_magia(self.card, self.slot)
        ctrl.world.add_component(self.card, Location(zona=Zona.CAMPO_MAGIA, slot=slot))
        ctrl.world.add_component(self.card, FaceDown())
        ctrl.bus.publish(CursePlaced(player_id=self.player_id, card=self.card, slot=slot))


@dataclass
class ActivateSetCurseAction:
    """Revela e resolve uma Maldicao ja setada — SÓ chamada pela decisão do
    dono dentro de curses.ofertar_maldicoes_reativas, nunca por um clique
    livre da UI: o "a qualquer momento no turno do oponente"
    (GAME_DESIGN.md) descreve QUANDO a janela reativa pode aparecer, não
    uma permissão pra virar a carta sem o gatilho dela (`EFFECTS.
    registrar_gatilho_maldicao`) ter disparado — sem isso, dava pra
    ativar "negar o próximo ataque" fora de qualquer ataque, sem contexto
    nenhum (bug real, corrigido junto com a remoção do clique livre em
    webgame/ui.js). E aqui, na ativação, que o Custo de Mana da carta e
    cobrado (setar foi de graça). `evento` (opcional): o evento que
    motivou a oferta, repassado pro efeito da carta (ver comentário no
    topo da seção Maldições de effects.py); só fica `None` numa chamada
    direta de teste/demo fora do fluxo reativo (ex.: demo_mecanismos.py)."""
    player_id: int
    card: int
    evento: object | None = None

    def executar(self, ctrl) -> None:
        lado = ctrl.board.lado(self.player_id)
        if self.card not in lado.magia:
            raise AcaoInvalida("Essa Maldicao nao esta setada nesse lado do tabuleiro.")
        custo = ctrl.world.get_component(self.card, ManaCost).valor
        _pagar_mana(ctrl, self.player_id, custo)
        ctrl.world.remove_component(self.card, FaceDown)

        info = ctrl.world.get_component(self.card, CardInfo)
        from .events import CurseTriggered
        ctrl.bus.publish(CurseTriggered(player_id=self.player_id, card=self.card))
        ctrl.effects.executar(ctrl, info.nome, self.player_id, self.card, self.evento)

        ctrl.destruction_system.destruir(ctrl.world, self.card, motivo="Maldição ativada")


@dataclass
class DeclareAttackAction:
    """Fase de Batalha: confronta o combatente ativo contra o do oponente
    (ou os Pontos de Vida dele, se o campo estiver vazio)."""
    player_id: int
    oponente_id: int

    def executar(self, ctrl) -> None:
        _exigir_fase(ctrl, self.player_id, Fase.BATALHA)
        # GAME_DESIGN.md, 'Declarar um ataque': "Fase de Batalha, 1x/turno
        # por combatente, nunca no 1º turno da partida" — nenhuma das duas
        # restrições era verificada aqui antes desta correção (bug real: o
        # motor Python deixava atacar quantas vezes quisesse, e no turno 1).
        if ctrl.fase_system.estado_atual(ctrl.world).numero_turno == 1:
            raise AcaoInvalida("Nao e possivel atacar no primeiro turno.")
        atacante = ctrl.board.lado(self.player_id).monstro
        if atacante is None:
            raise AcaoInvalida("Nao ha combatente ativo pra atacar.")
        if ctrl.world.has_component(atacante, AttackedThisTurn):
            raise AcaoInvalida("Esse combatente ja atacou neste turno.")
        ctrl.world.add_component(atacante, AttackedThisTurn())
        defensor = ctrl.board.lado(self.oponente_id).monstro

        # Maldições reativas elegíveis pro ataque (Escudo de Gelo Absoluto,
        # Espelho das Ilusões, Barreira de Vento Cortante, Retribuição
        # Kármica, Vínculo Sombrio) precisam decidir ANTES do dano ser
        # calculado. O evento aqui é só um objeto de dados pra checar
        # elegibilidade — resolver_ataque publica o de verdade.
        evento = AttackDeclared(
            atacante_player=self.player_id, atacante_card=atacante,
            defensor_player=self.oponente_id, defensor_card=defensor,
        )

        def _continuar() -> None:
            defensor_atual = ctrl.board.lado(self.oponente_id).monstro
            ctrl.combat_system.resolver_ataque(ctrl.world, self.player_id, atacante, self.oponente_id, defensor_atual)

        from .curses import ofertar_maldicoes_reativas
        ofertar_maldicoes_reativas(ctrl, evento, _continuar)


@dataclass
class ShuffleAction:
    """Acao de embaralhar um deck (ex.: Troca Equivalente devolve cartas da
    mao pro Baralho Arcano e embaralha antes de comprar de novo)."""
    deck: Deck
    devolver: list[int] = field(default_factory=list)

    def executar(self, ctrl) -> None:
        for card in self.devolver:
            self.deck.adicionar(card)
            loc = ctrl.world.get_component(card, Location)
            if loc:
                loc.zona = Zona.BARALHO_ARCANO
        self.deck.embaralhar()
        ctrl.bus.publish(DeckShuffled(deck_nome=self.deck.nome))
