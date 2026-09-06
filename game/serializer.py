# -*- coding: utf-8 -*-
"""Serialização de estado por destinatário — a peça que faltava pra usar
`GameController` atrás de uma rede (ver GameController.estado(), que é só
pra depuração local: reduz cartas a nome puro, sem id, e não esconde nada
de ninguém).

Espelha webgame/engine.js's TCG.estadoCompletoPara/cartaOuOculta: manda o
id da entidade + só os campos MUTÁVEIS de cada carta (POW/RES atual,
status effects, faceDown, etc.) — nunca os campos estáticos do template
(custo de mana, texto de efeito, arte...), porque o cliente já resolve
isso batendo `nome` contra webgame/data.js. E redige (troca por um
placeholder `{"oculto": true, "instanceId": ...}`) qualquer informação que
`destinatario_id` não deveria poder ver: a mão do OUTRO jogador, e
Maldições viradas pra baixo que não são dele.
"""
from __future__ import annotations

from .components import (
    AbilityCost, AttackedThisTurn, AttackNegated, CardInfo, CombatStats,
    DamageReflected, DanoDobradoContraMonstro, ElementoOverride, FaceDown,
    IgnoraFraquezaElemental, ImuneAHabilidadesInimigas, Location, StatusEffects, Zona,
)
from .controller import GameController


def _esta_face_down(ctrl: GameController, card: int) -> bool:
    fd = ctrl.world.get_component(card, FaceDown)
    return bool(fd and fd.virada_para_baixo)


def _carta_publica(ctrl: GameController, card: int) -> dict:
    """Todo campo MUTÁVEL de uma carta — nunca os estáticos do template
    (esses o cliente já tem, indexados por `nome`, em webgame/data.js)."""
    info = ctrl.world.get_component(card, CardInfo)
    stats = ctrl.world.get_component(card, CombatStats)
    ability = ctrl.world.get_component(card, AbilityCost)
    status = ctrl.world.get_component(card, StatusEffects)
    override = ctrl.world.get_component(card, ElementoOverride)
    return {
        "instanceId": card,
        "nome": info.nome if info else None,
        "atualPow": stats.atual_pow if stats else None,
        "atualRes": stats.atual_res if stats else None,
        "danoAcumulado": stats.dano_acumulado if stats else None,
        "statusEffects": [
            {"atributo": s.atributo, "magnitude": s.magnitude, "duracao": s.duracao.name, "origem": s.origem}
            for s in status.itens
        ] if status else [],
        "habilidadeUsadaNesteTurno": ability.usada_neste_turno if ability else False,
        "atacouNesteTurno": ctrl.world.has_component(card, AttackedThisTurn),
        "faceDown": _esta_face_down(ctrl, card),
        "elementoOverride": override.elemento.name if override else None,
        "attackNegated": ctrl.world.has_component(card, AttackNegated),
        "damageReflected": ctrl.world.has_component(card, DamageReflected),
        "ignoraFraquezaElemental": ctrl.world.has_component(card, IgnoraFraquezaElemental),
        "danoDobradoContraMonstro": ctrl.world.has_component(card, DanoDobradoContraMonstro),
        "imuneAHabilidadesInimigas": ctrl.world.has_component(card, ImuneAHabilidadesInimigas),
    }


def _carta_ou_oculta(ctrl: GameController, card: int | None, pode_ver: bool) -> dict | None:
    if card is None:
        return None
    if pode_ver:
        return _carta_publica(ctrl, card)
    return {"oculto": True, "instanceId": card}


def _mao_filtrada(ctrl: GameController, player_id: int, destinatario_id: int) -> list[dict]:
    ps = ctrl.players[player_id]
    pode_ver = player_id == destinatario_id
    return [_carta_ou_oculta(ctrl, c, pode_ver) for c in ps.mao]


def _magia_filtrada(ctrl: GameController, player_id: int, destinatario_id: int) -> list[dict | None]:
    lado = ctrl.board.lado(player_id)
    resultado = []
    for c in lado.magia:
        if c is None:
            resultado.append(None)
            continue
        pode_ver = not _esta_face_down(ctrl, c) or player_id == destinatario_id
        resultado.append(_carta_ou_oculta(ctrl, c, pode_ver))
    return resultado


def _descarte_de(ctrl: GameController, player_id: int) -> list[dict]:
    """Não existe uma lista `descarte[pid]` pronta no Controller (ao
    contrário do JS) — a pilha de descarte é só um valor de `Location.zona`
    por entidade; reconstrói a lista consultando o World. Público/sem
    filtro pra qualquer destinatário, igual engine.js:675-676."""
    cartas = []
    for card, loc in ctrl.world.query(Location):
        if loc.zona is Zona.PILHA_DESCARTE and ctrl.dono_da_carta(card) == player_id:
            cartas.append(_carta_publica(ctrl, card))
    return cartas


def _localiza_lado(ctrl: GameController, card: int) -> tuple[int, str] | None:
    """Onde uma carta está agora (mão de quem, ou slot de magia de quem) —
    espelha rede.js's localizaLado. Usado só pra decidir visibilidade num
    payload de EVENTO avulso (estado_completo_para já sabe isso via
    _mao_filtrada/_magia_filtrada, que iteram a partir da posição, não da
    carta)."""
    for pid in ctrl.jogadores:
        if card in ctrl.players[pid].mao:
            return pid, "mao"
        if card in ctrl.board.lado(pid).magia:
            return pid, "magia"
    return None


def _deve_ocultar_para(ctrl: GameController, valor: dict, destinatario_id: int) -> bool:
    """Espelha rede.js's deveOcultarPara: recebe um valor de payload já
    resolvido (um dict de carta, produzido por _carta_publica) e decide se
    esse destinatário específico pode ver a identidade real dele."""
    if not isinstance(valor, dict) or "instanceId" not in valor:
        return False
    onde = _localiza_lado(ctrl, valor["instanceId"])
    if onde is None:
        return False
    pid, zona = onde
    if zona == "mao":
        return pid != destinatario_id
    if zona == "magia":
        return valor.get("faceDown", False) and pid != destinatario_id
    return False


def filtrar_payload_para(ctrl: GameController, payload: dict, destinatario_id: int) -> dict:
    """Espelha rede.js's filtrarPayload: troca qualquer valor de carta no
    payload de um EVENTO (não do snapshot completo, que já tem seu próprio
    filtro por posição) por um placeholder oculto, se esse destinatário não
    deveria ver a identidade real dela. Detecção por FORMATO do valor (é um
    dict de carta?), não por nome de campo — o mesmo truque do JS, que
    permite um único filtro genérico cobrir qualquer evento novo sem listar
    campo por campo."""
    resultado = {}
    for chave, valor in payload.items():
        if isinstance(valor, dict) and _deve_ocultar_para(ctrl, valor, destinatario_id):
            resultado[chave] = {"oculto": True, "instanceId": valor["instanceId"]}
        elif isinstance(valor, list):
            resultado[chave] = [
                ({"oculto": True, "instanceId": v["instanceId"]} if _deve_ocultar_para(ctrl, v, destinatario_id) else v)
                if isinstance(v, dict) else v
                for v in valor
            ]
        else:
            resultado[chave] = valor
    return resultado


def estado_completo_para(ctrl: GameController, destinatario_id: int) -> dict:
    ts = ctrl.fase_atual()
    go = ctrl.fim_de_jogo()

    return {
        "turno": ts.numero_turno,
        "jogadorDaVez": ts.jogador_da_vez,
        "fase": ts.fase.name,
        "ultimoDominioAtivadoPor": ctrl.ultimo_dominio_ativado_por,
        # `perdedor` (não `perdedorPlayer`): nome de campo herdado do
        # cliente JS existente — webgame/engine.js's checarFimDeJogo monta
        # `game.fimDeJogo = { perdedor: pid, motivo }`, e ui.js/match.js já
        # leem `game.fimDeJogo.perdedor` — manter o mesmo nome aqui evita
        # qualquer tradução extra do lado do cliente quando ele passar a
        # receber isto de um servidor em vez do host local.
        "fimDeJogo": {"perdedor": go.perdedor_player, "motivo": go.motivo} if go else None,
        "players": {
            pid: {
                "nome": ps.nome, "mana": ps.mana, "vida": ps.vida,
                "mao": _mao_filtrada(ctrl, pid, destinatario_id),
            }
            for pid, ps in ctrl.players.items()
        },
        "board": {
            # NÃO itera ctrl.board.lados.items() direto: esse dict é
            # preenchido PREGUIÇOSAMENTE (Board.lado(pid) só cria o
            # BoardSide na primeira vez que alguém pede aquele lado) — um
            # jogo recém-criado, antes de qualquer invocação/magia, tem
            # `lados` VAZIO, e o snapshot mandaria um tabuleiro inteiro
            # ausente pros dois lados. ctrl.board.lado(pid) força a
            # criação (idempotente) e sempre devolve algo, mesmo vazio.
            pid: {
                "playerId": pid,
                # o Monstro nunca é escondido: só Maldições setadas (via
                # SetCurseAction, num slot de MAGIA) recebem FaceDown —
                # invocar/trocar combatente nunca marca o slot de Monstro
                # como virado pra baixo.
                "monstro": _carta_publica(ctrl, lado.monstro) if lado.monstro is not None else None,
                "magia": _magia_filtrada(ctrl, pid, destinatario_id),
            }
            for pid in ctrl.jogadores
            for lado in [ctrl.board.lado(pid)]
        },
        # Baralho: nunca manda o conteúdo, nem pro dono — só a contagem,
        # igual engine.js:661-664 (a compra é aleatória/oculta até sair).
        "baralhos": {pid: len(ctrl.baralhos[pid].restantes()) for pid in ctrl.jogadores},
        # Panteão: lista completa só pro PRÓPRIO dono (precisa pra escolher
        # quem invocar); só a contagem pro oponente.
        "panteoes": {
            pid: (
                [_carta_publica(ctrl, c) for c in ctrl.panteoes[pid].restantes()]
                if pid == destinatario_id
                else len(ctrl.panteoes[pid].restantes())
            )
            for pid in ctrl.jogadores
        },
        "descarte": {pid: _descarte_de(ctrl, pid) for pid in ctrl.jogadores},
    }
