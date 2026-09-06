# -*- coding: utf-8 -*-
"""estado_completo_para(ctrl, destinatario_id) — a matriz de redação de
informação oculta, espelhando webgame/engine.js's TCG.estadoCompletoPara.
GameController.estado() (vestigial, sem id de entidade e sem filtro
nenhum) NÃO é o que testamos aqui."""
from __future__ import annotations

from game.actions import ActivateSetCurseAction, SetCurseAction, SummonAction
from game.components import Tipo
from game.controller import GameController
from game.serializer import estado_completo_para


def _achar_na_mao(ctrl, player_id, tipo: Tipo):
    from game.components import CardInfo
    for c in ctrl.players[player_id].mao:
        info = ctrl.world.get_component(c, CardInfo)
        if info.tipo is tipo:
            return c
    return None


def test_oponente_nao_ve_a_mao_do_outro_mas_o_dono_ve_a_propria():
    ctrl = GameController(seed=42)
    ctrl.iniciar_jogo()

    estado_para_1 = estado_completo_para(ctrl, 1)
    estado_para_2 = estado_completo_para(ctrl, 2)

    # J1 vê a própria mão de verdade...
    mao_j1_vista_por_1 = estado_para_1["players"][1]["mao"]
    assert all(not c.get("oculto") for c in mao_j1_vista_por_1)
    assert all(c["nome"] is not None for c in mao_j1_vista_por_1)

    # ...mas a mão de J1 vista por J2 é só placeholders ocultos, com o
    # instanceId preservado (o cliente precisa dele pra contar/animar o
    # verso da carta) e nenhum dado de identidade real.
    mao_j1_vista_por_2 = estado_para_2["players"][1]["mao"]
    assert len(mao_j1_vista_por_2) == len(mao_j1_vista_por_1)
    for c in mao_j1_vista_por_2:
        assert c["oculto"] is True
        assert "nome" not in c
        assert "instanceId" in c

    # é simétrico: mesma coisa pra mão de J2 do ponto de vista de J1.
    mao_j2_vista_por_1 = estado_para_1["players"][2]["mao"]
    assert all(c.get("oculto") for c in mao_j2_vista_por_1)
    mao_j2_vista_por_2 = estado_para_2["players"][2]["mao"]
    assert all(not c.get("oculto") for c in mao_j2_vista_por_2)


def _preparar_maldicao_setada(ctrl: GameController) -> int:
    """Avança até a Fase Principal de J2 e seta uma Maldição, devolvendo o
    id da carta."""
    ctrl.avancar_fase()  # SAQUE -> INVOCACAO (J1)
    escolhido = ctrl.panteoes[1].restantes()[0]
    ctrl.players[1].mana = 20
    ctrl.submeter_acao(SummonAction(player_id=1, card=escolhido))
    while ctrl.fase_atual().jogador_da_vez != 2 or ctrl.fase_atual().fase.name != "PRINCIPAL":
        ctrl.avancar_fase()
    maldicao = _achar_na_mao(ctrl, 2, Tipo.MALDICAO)
    assert maldicao is not None, "seed precisa garantir uma Maldição na mão de J2 — ver comentário no teste"
    ctrl.players[2].mana = 10
    ctrl.submeter_acao(SetCurseAction(player_id=2, card=maldicao))
    return maldicao


def test_maldicao_face_down_oculta_do_nao_dono_visivel_do_dono():
    ctrl = GameController(seed=7)  # mesma seed de demo_mecanismos.py, sabidamente dá Maldição na mão de J2
    ctrl.iniciar_jogo()
    maldicao = _preparar_maldicao_setada(ctrl)

    estado_para_1 = estado_completo_para(ctrl, 1)  # J1 é o NÃO-dono
    estado_para_2 = estado_completo_para(ctrl, 2)  # J2 é o dono

    magia_j2_vista_por_1 = estado_para_1["board"][2]["magia"]
    carta_oculta = next(c for c in magia_j2_vista_por_1 if c is not None)
    assert carta_oculta["oculto"] is True
    assert carta_oculta["instanceId"] == maldicao

    magia_j2_vista_por_2 = estado_para_2["board"][2]["magia"]
    carta_visivel = next(c for c in magia_j2_vista_por_2 if c is not None)
    assert not carta_visivel.get("oculto")
    assert carta_visivel["instanceId"] == maldicao
    assert carta_visivel["nome"] is not None
    assert carta_visivel["faceDown"] is True  # visível pro dono, mas ele SABE que está virada pra baixo


def test_monstro_nunca_e_ocultado():
    ctrl = GameController(seed=42)
    ctrl.iniciar_jogo()
    ctrl.avancar_fase()
    escolhido = ctrl.panteoes[1].restantes()[0]
    ctrl.players[1].mana = 20
    ctrl.submeter_acao(SummonAction(player_id=1, card=escolhido))

    # do ponto de vista do OPONENTE (2), que normalmente teria motivo pra
    # não ver informação de J1 — o Monstro em campo é sempre público.
    estado_para_2 = estado_completo_para(ctrl, 2)
    monstro = estado_para_2["board"][1]["monstro"]
    assert monstro is not None
    assert not monstro.get("oculto")
    assert monstro["instanceId"] == escolhido
    assert monstro["nome"] is not None


def test_baralho_e_so_contagem_mesmo_para_o_proprio_dono():
    ctrl = GameController(seed=42)
    ctrl.iniciar_jogo()
    estado_para_1 = estado_completo_para(ctrl, 1)
    assert isinstance(estado_para_1["baralhos"][1], int)
    assert estado_para_1["baralhos"][1] == len(ctrl.baralhos[1].restantes())
    assert isinstance(estado_para_1["baralhos"][2], int)


def test_panteao_completo_so_pro_proprio_dono_contagem_pro_oponente():
    ctrl = GameController(seed=42)
    ctrl.iniciar_jogo()
    estado_para_1 = estado_completo_para(ctrl, 1)

    panteao_proprio = estado_para_1["panteoes"][1]
    assert isinstance(panteao_proprio, list)
    assert len(panteao_proprio) == len(ctrl.panteoes[1].restantes())
    assert all(not c.get("oculto") and c["nome"] is not None for c in panteao_proprio)

    panteao_oponente = estado_para_1["panteoes"][2]
    assert isinstance(panteao_oponente, int)
    assert panteao_oponente == len(ctrl.panteoes[2].restantes())


def test_descarte_e_publico_para_qualquer_destinatario():
    ctrl = GameController(seed=7)
    ctrl.iniciar_jogo()
    mao_j1 = list(ctrl.players[1].mao)
    from game.components import Location, Zona
    carta = mao_j1[0]
    ctrl.players[1].mao.remove(carta)
    ctrl.world.get_component(carta, Location).zona = Zona.PILHA_DESCARTE

    estado_para_1 = estado_completo_para(ctrl, 1)
    estado_para_2 = estado_completo_para(ctrl, 2)

    descarte_visto_por_1 = estado_para_1["descarte"][1]
    descarte_visto_por_2 = estado_para_2["descarte"][1]
    assert any(c["instanceId"] == carta for c in descarte_visto_por_1)
    assert any(c["instanceId"] == carta for c in descarte_visto_por_2)
    assert not any(c.get("oculto") for c in descarte_visto_por_1)
    assert not any(c.get("oculto") for c in descarte_visto_por_2)
