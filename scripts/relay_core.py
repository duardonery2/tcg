# -*- coding: utf-8 -*-
"""Primitivas de pareamento/repasse compartilhadas pelos dois relays deste
projeto: o relay LAN de desenvolvimento (scripts/relay_lan.py, uma sala só
por processo) e o relay com código de sala hospedado na internet
(scripts/relay_server.py, várias salas simultâneas). Nenhum dos dois
entende regra de jogo — só entregam o cano entre "host" e "guest"; toda a
lógica de sincronização/filtragem de informação oculta mora em
webgame/rede.js, nos dois navegadores.
"""
from __future__ import annotations

import json

import websockets
from websockets.asyncio.server import ServerConnection


class Sala:
    """Duas pontas nomeadas: a primeira que chega vira o "host" (dono da
    simulação de verdade), a segunda o "guest" (espelho). `papel_para`
    atribui o papel só quando o slot correspondente está livre — quem
    chama decide como/quando os slots são preenchidos (ordem de conexão
    no relay LAN; mensagens explícitas de criar/entrar/retomar no relay
    com código de sala)."""

    def __init__(self) -> None:
        self.host: ServerConnection | None = None
        self.guest: ServerConnection | None = None

    def esta_completa(self) -> bool:
        return self.host is not None and self.guest is not None

    def outra_ponta(self, ws: ServerConnection) -> ServerConnection | None:
        if ws is self.host:
            return self.guest
        if ws is self.guest:
            return self.host
        return None

    def desconectar(self, ws: ServerConnection) -> None:
        if ws is self.host:
            self.host = None
        elif ws is self.guest:
            self.guest = None


async def bombear(ws: ServerConnection, sala: Sala) -> None:
    """Repassa cada mensagem de texto recebida em `ws` pra outra ponta da
    `sala`, sem tocar no conteúdo. Roda até a conexão cair; quem chama é
    responsável por chamar `sala.desconectar(ws)` depois (num `finally`),
    já que o que fazer com uma sala esvaziada varia entre os dois relays."""
    async for mensagem in ws:
        destino = sala.outra_ponta(ws)
        if destino is not None:
            try:
                await destino.send(mensagem)
            except websockets.exceptions.ConnectionClosed:
                pass  # a outra ponta já caiu; a própria iteração acima vai perceber e sair


async def enviar_papel(ws: ServerConnection, papel: str, extra: dict | None = None) -> None:
    await ws.send(json.dumps({"type": "papel", "papel": papel, **(extra or {})}))


async def enviar_guest_conectou(host: ServerConnection) -> None:
    await host.send(json.dumps({"type": "guestConectou"}))
