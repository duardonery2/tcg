# -*- coding: utf-8 -*-
"""Relay burro pra multiplayer em rede local (LAN) — combina duas coisas
num só processo:

1. Um servidor HTTP estático servindo a RAIZ do repositório (não só
   webgame/), pra que os caminhos relativos que já existem em
   webgame/data.js (../cards/...) e webgame/ui.js (../sound/...)
   continuem resolvendo exatamente igual a hoje (quando o jogo é aberto
   direto como file://) — só que agora por http://.
2. Um relay WebSocket que NÃO entende nada de regra de jogo: aceita
   exatamente 2 conexões (a primeira é o "host", a segunda o "guest") e
   repassa cada mensagem de texto de uma pra outra, sem tocar no
   conteúdo. Toda a lógica de sincronização/filtragem de informação
   oculta mora em webgame/rede.js, nos dois navegadores — este processo
   só entrega o cano entre eles.

Uso:
    python3 scripts/relay_lan.py [--http-port 8000] [--ws-port 8765]

Depois, em cada máquina da mesma rede local, abrir no navegador:
    http://<ip impresso>:8000/webgame/index.html
"""
from __future__ import annotations

import argparse
import asyncio
import http.server
import json
import socket
import threading

import websockets
from websockets.asyncio.server import ServerConnection, serve

RAIZ_DO_REPO = __import__("pathlib").Path(__file__).resolve().parent.parent


def descobrir_ip_lan() -> str:
    """Não manda nada de verdade — só usa um socket UDP "conectado" a um IP
    qualquer fora da máquina pra perguntar ao SO qual interface de rede
    LAN seria usada, e lê o IP local dessa interface."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def iniciar_servidor_estatico(porta: int) -> None:
    """Serve a raiz do repo (não webgame/) numa thread separada — só assim
    ../cards/... e ../sound/... (relativos a webgame/index.html) resolvem
    do jeito certo. ThreadingHTTPServer porque http.server é síncrono e
    não pode compartilhar o event loop asyncio do relay WebSocket."""
    handler = lambda *args, **kwargs: http.server.SimpleHTTPRequestHandler(
        *args, directory=str(RAIZ_DO_REPO), **kwargs
    )
    servidor = http.server.ThreadingHTTPServer(("0.0.0.0", porta), handler)
    thread = threading.Thread(target=servidor.serve_forever, daemon=True)
    thread.start()


class Sala:
    """MVP: uma sala só por processo. A primeira conexão que chega vira o
    host, a segunda o guest; uma terceira é rejeitada. Nenhuma das duas
    pontas precisa saber a ordem de antemão — quem conecta primeiro que
    define (o jogador que vai hostear só precisa apertar "Hospedar" antes
    do outro apertar "Entrar")."""

    def __init__(self) -> None:
        self.host: ServerConnection | None = None
        self.guest: ServerConnection | None = None

    def papel_para(self, ws: ServerConnection) -> str | None:
        if self.host is None:
            self.host = ws
            return "host"
        if self.guest is None:
            self.guest = ws
            return "guest"
        return None

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


async def tratar_conexao(ws: ServerConnection, sala: Sala) -> None:
    papel = sala.papel_para(ws)
    if papel is None:
        await ws.close(1013, "sala cheia (já há host e guest conectados)")
        return
    print(f"[relay] {papel} conectado ({ws.remote_address})")
    # o relay não entende nada de jogo, mas cada navegador precisa saber se
    # é o host (dono da simulação de verdade) ou o guest (espelho) — isso
    # não dá pra decidir sozinho no JS, só o relay sabe quem chegou primeiro.
    await ws.send(json.dumps({"type": "papel", "papel": papel}))
    if papel == "guest" and sala.host is not None:
        await sala.host.send(json.dumps({"type": "guestConectou"}))
    try:
        async for mensagem in ws:
            destino = sala.outra_ponta(ws)
            if destino is not None:
                try:
                    await destino.send(mensagem)
                except websockets.exceptions.ConnectionClosed:
                    pass  # a outra ponta já caiu; a própria iteração acima vai perceber e sair
    finally:
        sala.desconectar(ws)
        print(f"[relay] {papel} desconectado")


async def rodar_relay(porta: int) -> None:
    sala = Sala()

    async def handler(ws: ServerConnection) -> None:
        await tratar_conexao(ws, sala)

    async with serve(handler, "0.0.0.0", porta):
        await asyncio.Future()  # roda pra sempre


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--http-port", type=int, default=8000)
    parser.add_argument("--ws-port", type=int, default=8765)
    args = parser.parse_args()

    ip = descobrir_ip_lan()
    iniciar_servidor_estatico(args.http_port)

    print("=== O Duelo dos Feiticeiros — relay de multiplayer LAN ===")
    print(f"Servidor de arquivos: http://{ip}:{args.http_port}/webgame/index.html")
    print(f"Relay WebSocket:      ws://{ip}:{args.ws_port}")
    print()
    print("Em CADA máquina da mesma rede local, abra a URL acima no navegador.")
    print("Quem clicar em \"Hospedar\" primeiro vira o host; o outro clica em \"Entrar\".")
    print("Ctrl+C encerra o relay (e a partida).")
    print()

    try:
        asyncio.run(rodar_relay(args.ws_port))
    except KeyboardInterrupt:
        print("\n[relay] encerrado.")


if __name__ == "__main__":
    main()
