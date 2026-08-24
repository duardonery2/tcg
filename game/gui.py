# -*- coding: utf-8 -*-
"""GUI do jogo em Pygame. Le as cartas ja renderizadas em cards/*.png (o
mesmo pipeline de scripts/renderizar_cartas.py) e desenha o tabuleiro: 1
slot de Monstro + 5 slots de Magia por jogador, a mao do jogador da vez, e
um log de notificacoes — a GUI nunca lê o estado "por fora": ela so aparece
porque assinou os eventos do EventBus (game/events.py).

Rodar:  python3 -m game.gui
Requer um display (X11/Wayland). Em ambiente headless, defina
SDL_VIDEODRIVER=dummy so pra fins de teste de fumaca (nao ha janela real).
"""
from __future__ import annotations

import os
import sys

import pygame

from .actions import (
    AcaoInvalida, ActivateAbilityAction, ActivateDomainAction,
    DeclareAttackAction, PlayEnchantmentAction, SetCurseAction, SummonAction,
)
from .components import AbilityCost, CardInfo, Fase, Tipo
from .controller import GameController
from .events import (
    AttackDeclared, CardDestroyed, CardDrawn, CombatantSummoned, DamageDealt,
    GameOver, LifeChanged, ManaChanged, PhaseChanged, SelectionRequested,
)

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CARDS_DIR = os.path.join(BASE, "cards")

LARGURA, ALTURA = 1280, 860
COR_FUNDO = (24, 26, 22)
COR_SLOT_VAZIO = (55, 58, 50)
COR_SELECIONAVEL = (240, 200, 90)
COR_TEXTO = (235, 232, 220)
COR_PAINEL = (36, 38, 32)

CARTA_W, CARTA_H = 90, 126
MAO_CARTA_W, MAO_CARTA_H = 110, 154


class ImageCache:
    def __init__(self):
        self._cache: dict[str, pygame.Surface] = {}

    def get(self, nome: str, size: tuple[int, int]) -> pygame.Surface:
        key = f"{nome}@{size}"
        if key in self._cache:
            return self._cache[key]
        path = os.path.join(CARDS_DIR, f"{nome.replace(' ', '_')}.png")
        try:
            img = pygame.image.load(path).convert_alpha()
        except Exception:
            img = pygame.Surface(size, pygame.SRCALPHA)
            img.fill((80, 40, 40, 255))
        img = pygame.transform.smoothscale(img, size)
        self._cache[key] = img
        return img


class GameGUI:
    def __init__(self, ctrl: GameController, jogador_local: int = 1):
        pygame.init()
        pygame.display.set_caption("O Duelo dos Feiticeiros")
        self.screen = pygame.display.set_mode((LARGURA, ALTURA))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("georgia,dejavusans", 18)
        self.font_small = pygame.font.SysFont("georgia,dejavusans", 14)
        self.font_big = pygame.font.SysFont("georgia,dejavusans", 26, bold=True)

        self.ctrl = ctrl
        self.jogador_local = jogador_local
        self.images = ImageCache()
        self.log: list[str] = []
        self.selecao_pendente: SelectionRequested | None = None
        self.rodando = True

        self._ligar_notificacoes()

    # ---- notificacoes -----------------------------------------------------

    def _ligar_notificacoes(self) -> None:
        bus = self.ctrl.bus

        def linha(msg: str):
            self.log.append(msg)
            self.log[:] = self.log[-8:]

        bus.subscribe(PhaseChanged, lambda e: linha(f"Fase: J{e.player_id} -> {e.fase_nova.name}"))
        bus.subscribe(CardDrawn, lambda e: linha(f"J{e.player_id} comprou {self.ctrl.nome_da_carta(e.card)}"))
        bus.subscribe(CombatantSummoned, lambda e: linha(f"J{e.player_id} invocou {self.ctrl.nome_da_carta(e.card)}"))
        bus.subscribe(ManaChanged, lambda e: linha(f"J{e.player_id} mana {e.delta:+d} -> {e.total}"))
        bus.subscribe(LifeChanged, lambda e: linha(f"J{e.player_id} vida {e.delta:+d} -> {e.total}"))
        bus.subscribe(AttackDeclared, lambda e: linha(
            f"J{e.atacante_player} ataca com {self.ctrl.nome_da_carta(e.atacante_card)}"))
        bus.subscribe(DamageDealt, lambda e: linha(
            f"{e.quantidade} de dano em "
            f"{'J' + str(e.alvo_player) if e.alvo is None else self.ctrl.nome_da_carta(e.alvo)}"))
        bus.subscribe(CardDestroyed, lambda e: linha(f"{self.ctrl.nome_da_carta(e.card)} destruída ({e.motivo})"))
        bus.subscribe(GameOver, lambda e: linha(f"FIM DE JOGO: J{e.perdedor_player} perdeu ({e.motivo})"))

        def on_selecao(e: SelectionRequested):
            self.selecao_pendente = e
            linha(f"[seleção] J{e.player_id}: {e.prompt}")
        bus.subscribe(SelectionRequested, on_selecao)

    # ---- loop principal -----------------------------------------------------

    def run(self) -> None:
        while self.rodando:
            for event in pygame.event.get():
                self._handle_pygame_event(event)
            self._desenhar()
            self.clock.tick(30)
        pygame.quit()

    def _handle_pygame_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.QUIT:
            self.rodando = False
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self._on_click(event.pos)
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.rodando = False

    # ---- layout / hit-testing -----------------------------------------------

    def _rects_mao(self) -> list[tuple[pygame.Rect, int]]:
        ps = self.ctrl.players[self.jogador_local]
        rects = []
        n = len(ps.mao)
        if n == 0:
            return rects
        espaco = min(MAO_CARTA_W + 8, (LARGURA - 40) // n)
        x0 = (LARGURA - espaco * n) // 2
        y = ALTURA - MAO_CARTA_H - 16
        for i, card in enumerate(ps.mao):
            rect = pygame.Rect(x0 + i * espaco, y, MAO_CARTA_W, MAO_CARTA_H)
            rects.append((rect, card))
        return rects

    def _rects_tabuleiro(self, player_id: int, y_base: int) -> tuple[pygame.Rect, list[pygame.Rect]]:
        lado = self.ctrl.board.lado(player_id)
        cx = LARGURA // 2
        monstro_rect = pygame.Rect(cx - CARTA_W // 2, y_base, CARTA_W, CARTA_H)
        magia_rects = []
        largura_total = 5 * (CARTA_W + 10) - 10
        x0 = cx - largura_total // 2
        y_magia = y_base + (CARTA_H + 14 if player_id == self.jogador_local else -CARTA_H - 14)
        for i in range(5):
            magia_rects.append(pygame.Rect(x0 + i * (CARTA_W + 10), y_magia, CARTA_W, CARTA_H))
        return monstro_rect, magia_rects

    def _rects_panteao(self) -> list[tuple[pygame.Rect, int]]:
        restantes = self.ctrl.panteoes[self.jogador_local].restantes()
        rects = []
        y = ALTURA // 2 - CARTA_H // 2
        x0 = 20
        for i, card in enumerate(restantes):
            rects.append((pygame.Rect(x0, y + i * (CARTA_H // 3), CARTA_W, CARTA_H), card))
        return rects

    def _rects_selecao_overlay(self) -> list[tuple[pygame.Rect, int]]:
        """Layout generico pra qualquer SelectionRequested pendente — as
        opcoes podem vir de qualquer zona (mao, Pilha de Descarte, Maldições
        setadas...), entao a GUI mostra elas num carrossel central em vez
        de tentar achar cada uma no seu slot normal do tabuleiro."""
        req = self.selecao_pendente
        if req is None:
            return []
        n = len(req.opcoes)
        espaco = min(CARTA_W + 14, (LARGURA - 80) // max(n, 1))
        x0 = (LARGURA - espaco * n) // 2
        y = ALTURA // 2 - CARTA_H // 2
        return [(pygame.Rect(x0 + i * espaco, y, CARTA_W, CARTA_H), c) for i, c in enumerate(req.opcoes)]

    def _rect_botao_avancar(self) -> pygame.Rect:
        return pygame.Rect(LARGURA - 200, ALTURA // 2 - 20, 170, 44)

    def _rect_botao_atacar(self) -> pygame.Rect:
        return pygame.Rect(LARGURA - 200, ALTURA // 2 + 34, 170, 44)

    # ---- interacao -----------------------------------------------------

    def _on_click(self, pos: tuple[int, int]) -> None:
        ctrl = self.ctrl
        ts = ctrl.fase_atual()
        jogador = self.jogador_local

        if self.selecao_pendente is not None:
            self._tentar_resolver_selecao(pos)
            return

        if self._rect_botao_avancar().collidepoint(pos):
            ctrl.avancar_fase()
            return
        if self._rect_botao_atacar().collidepoint(pos) and ts.fase is Fase.BATALHA and ts.jogador_da_vez == jogador:
            self._tentar(DeclareAttackAction(player_id=jogador, oponente_id=ctrl.oponente_de(jogador)))
            return

        if ts.jogador_da_vez != jogador:
            return  # nao e a vez do jogador local (sem IA/2o humano nesta versao)

        if ts.fase is Fase.INVOCACAO:
            for rect, card in self._rects_panteao():
                if rect.collidepoint(pos):
                    self._tentar(SummonAction(player_id=jogador, card=card))
                    return

        if ts.fase in (Fase.PRINCIPAL, Fase.BATALHA):
            monstro_rect, _ = self._rects_tabuleiro(jogador, self._y_base_local())
            if monstro_rect.collidepoint(pos) and ctrl.board.lado(jogador).monstro is not None:
                self._tentar(ActivateAbilityAction(player_id=jogador, card=ctrl.board.lado(jogador).monstro))
                return

        if ts.fase is Fase.PRINCIPAL:
            for rect, card in self._rects_mao():
                if rect.collidepoint(pos):
                    self._jogar_da_mao(jogador, card)
                    return

    def _jogar_da_mao(self, jogador: int, card: int) -> None:
        info = self.ctrl.world.get_component(card, CardInfo)
        if info.tipo is Tipo.DOMINIO:
            self._tentar(ActivateDomainAction(player_id=jogador, card=card))
        elif info.tipo is Tipo.ENCANTAMENTO:
            self._tentar(PlayEnchantmentAction(player_id=jogador, card=card))
        elif info.tipo is Tipo.MALDICAO:
            self._tentar(SetCurseAction(player_id=jogador, card=card))

    def _tentar(self, acao) -> None:
        try:
            self.ctrl.submeter_acao(acao)
        except AcaoInvalida as e:
            self.log.append(f"[ação inválida] {e}")

    def _tentar_resolver_selecao(self, pos: tuple[int, int]) -> None:
        req = self.selecao_pendente
        for rect, card in self._rects_selecao_overlay():
            if rect.collidepoint(pos):
                self.ctrl.resolver_selecao(req.request_id, [card])
                self.selecao_pendente = None
                return

    def _y_base_local(self) -> int:
        return ALTURA - MAO_CARTA_H - CARTA_H - 60

    # ---- desenho -----------------------------------------------------

    def _blit_carta(self, nome: str, rect: pygame.Rect, destacar: bool = False) -> None:
        img = self.images.get(nome, (rect.width, rect.height))
        self.screen.blit(img, rect.topleft)
        cor_borda = COR_SELECIONAVEL if destacar else (10, 10, 10)
        pygame.draw.rect(self.screen, cor_borda, rect, width=3 if destacar else 1, border_radius=6)

    def _blit_slot_vazio(self, rect: pygame.Rect) -> None:
        pygame.draw.rect(self.screen, COR_SLOT_VAZIO, rect, border_radius=6)
        pygame.draw.rect(self.screen, (20, 20, 20), rect, width=1, border_radius=6)

    def _texto(self, txt: str, pos, cor=COR_TEXTO, fonte=None) -> None:
        fonte = fonte or self.font
        self.screen.blit(fonte.render(txt, True, cor), pos)

    def _desenhar(self) -> None:
        ctrl = self.ctrl
        ts = ctrl.fase_atual()
        self.screen.fill(COR_FUNDO)

        # HUD topo
        p1, p2 = ctrl.players[1], ctrl.players[2]
        self._texto(f"Turno {ts.numero_turno} — vez de J{ts.jogador_da_vez} — Fase {ts.fase.name}",
                    (20, 12), fonte=self.font_big)
        self._texto(f"{p1.nome}: {p1.mana} mana | {p1.vida} vida", (20, 46))
        self._texto(f"{p2.nome}: {p2.mana} mana | {p2.vida} vida", (20, 68))
        if ctrl.fim_de_jogo():
            self._texto(f"FIM DE JOGO — {ctrl.fim_de_jogo().motivo}", (20, 92), cor=(255, 90, 90), fonte=self.font_big)

        # tabuleiro do oponente (topo) e do jogador local (base)
        oponente = ctrl.oponente_de(self.jogador_local)
        self._desenhar_lado(oponente, y_base=150, mao_visivel=False)
        self._desenhar_lado(self.jogador_local, y_base=self._y_base_local(), mao_visivel=True)

        # Panteão do jogador local (INVOCACAO)
        if ts.fase is Fase.INVOCACAO and ts.jogador_da_vez == self.jogador_local:
            for rect, card in self._rects_panteao():
                self._blit_carta(ctrl.nome_da_carta(card), rect, destacar=True)
            self._texto("Panteão — clique para invocar", (20, ALTURA // 2 - CARTA_H // 2 - 22))

        # botoes
        self._botao(self._rect_botao_avancar(), "Próxima Fase")
        if ts.fase is Fase.BATALHA and ts.jogador_da_vez == self.jogador_local:
            self._botao(self._rect_botao_atacar(), "Atacar")

        # overlay de selecao pendente (por cima de tudo, bloqueia o resto do clique)
        if self.selecao_pendente:
            véu = pygame.Surface((LARGURA, ALTURA), pygame.SRCALPHA)
            véu.fill((0, 0, 0, 170))
            self.screen.blit(véu, (0, 0))
            self._texto(f"Selecione: {self.selecao_pendente.prompt}",
                        (LARGURA // 2 - 260, ALTURA // 2 - CARTA_H // 2 - 30), cor=COR_SELECIONAVEL, fonte=self.font_big)
            for rect, card in self._rects_selecao_overlay():
                self._blit_carta(ctrl.nome_da_carta(card), rect, destacar=True)

        # log de notificacoes
        painel = pygame.Rect(LARGURA - 380, ALTURA - 220, 360, 200)
        pygame.draw.rect(self.screen, COR_PAINEL, painel, border_radius=8)
        for i, linha in enumerate(self.log[-8:]):
            self._texto(linha, (painel.x + 10, painel.y + 8 + i * 20), fonte=self.font_small)

        pygame.display.flip()

    def _desenhar_lado(self, player_id: int, y_base: int, mao_visivel: bool) -> None:
        ctrl = self.ctrl
        lado = ctrl.board.lado(player_id)
        monstro_rect, magia_rects = self._rects_tabuleiro(player_id, y_base)

        selecionavel_ability = (
            lado.monstro is not None
            and ctrl.world.has_component(lado.monstro, AbilityCost)
            and not ctrl.world.get_component(lado.monstro, AbilityCost).usada_neste_turno
            and ctrl.fase_atual().jogador_da_vez == player_id
        )
        if lado.monstro is not None:
            self._blit_carta(ctrl.nome_da_carta(lado.monstro), monstro_rect, destacar=selecionavel_ability)
        else:
            self._blit_slot_vazio(monstro_rect)

        for i, rect in enumerate(magia_rects):
            card = lado.magia[i]
            if card is None:
                self._blit_slot_vazio(rect)
            elif ctrl.world.has_component(card, __import__("game.components", fromlist=["FaceDown"]).FaceDown) \
                    and player_id != self.jogador_local:
                self._blit_slot_vazio(rect)  # Maldição virada pra baixo do oponente: nao revela
            else:
                self._blit_carta(ctrl.nome_da_carta(card), rect)

        if mao_visivel:
            for rect, card in self._rects_mao():
                destacar = bool(self.selecao_pendente and card in self.selecao_pendente.opcoes)
                self._blit_carta(ctrl.nome_da_carta(card), rect, destacar=destacar)
        else:
            ps = ctrl.players[player_id]
            self._texto(f"Mão do oponente: {len(ps.mao)} carta(s)", (20, y_base - 24))

    def _botao(self, rect: pygame.Rect, texto: str) -> None:
        pygame.draw.rect(self.screen, (70, 60, 30), rect, border_radius=8)
        pygame.draw.rect(self.screen, (150, 120, 50), rect, width=2, border_radius=8)
        txt_surf = self.font.render(texto, True, COR_TEXTO)
        self.screen.blit(txt_surf, txt_surf.get_rect(center=rect.center))


def main() -> None:
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else None
    ctrl = GameController(seed=seed)
    ctrl.iniciar_jogo()
    gui = GameGUI(ctrl, jogador_local=1)
    gui.run()


if __name__ == "__main__":
    main()
