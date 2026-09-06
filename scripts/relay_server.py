# -*- coding: utf-8 -*-
"""Relay com código de sala, feito pra rodar publicamente na internet (ex.:
Fly.io) — ao contrário de scripts/relay_lan.py (uma sala só por processo,
pareada por ordem de conexão), este processo mantém várias salas
simultâneas num dicionário em memória, cada uma identificada por um código
curto que o jogador anfitrião compartilha com o oponente.

Não serve arquivo estático nenhum (o front-end mora num host separado,
ex.: GitHub Pages) — só entende WebSocket, e só entende o suficiente pra
criar/entrar/retomar salas; o resto de cada mensagem é repassado sem
interpretar, exatamente como scripts/relay_lan.py.

Uso local:
    python3 scripts/relay_server.py [--ws-port 8765]

Em produção (Fly.io), a porta vem da variável de ambiente PORT.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import string
import time

import websockets
from websockets.asyncio.server import ServerConnection, serve

from relay_core import Sala, bombear, enviar_guest_conectou, enviar_papel

# Sem 0/O/1/I/L pra evitar ambiguidade quando o jogador digita o código à mão.
ALFABETO_CODIGO = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
TAMANHO_CODIGO = 5

TEMPO_EXPIRACAO_SALA_VAZIA_SEGUNDOS = 600  # sala criada mas ninguém entrou
# Sala completa perdeu um lado: 5 minutos de margem pra reconectar (ver
# TCG.iniciarPartidaMultiplayer em webgame/match.js, que tenta de novo
# nessa mesma janela do lado do navegador) — tempo suficiente pra cobrir
# uma queda de wifi, o navegador suspender a aba em segundo plano, etc.,
# sem manter uma sala morta pra sempre se ninguém voltar.
TEMPO_GRACA_RECONEXAO_SEGUNDOS = 300
INTERVALO_LIMPEZA_SEGUNDOS = 30


class SalaComCodigo(Sala):
    """Uma Sala (host/guest) mais os metadados de quando cada lado ficou
    incompleto, usados só pra decidir quando a sala expira.

    `foi_completada` importa porque a navegação menu.html -> index.html
    fecha as DUAS conexões originais (cada lado fecha a própria assim que
    recebe a confirmação de pareamento e troca de página) ANTES de abrirem
    as conexões novas que mandam "retomarSala" — por um instante os dois
    slots ficam vazios de novo, mesmo com jogadores reais a caminho. Sem
    esse flag, esse instante seria indistinguível de "sala nunca teve
    ninguém" e a sala seria apagada na hora, invalidando o código."""

    def __init__(self) -> None:
        super().__init__()
        self.criada_em = time.monotonic()
        self.incompleta_desde: float | None = self.criada_em
        self.foi_completada = False


class RegistroDeSalas:
    def __init__(self) -> None:
        self.salas: dict[str, SalaComCodigo] = {}

    def gerar_codigo(self) -> str:
        while True:
            codigo = "".join(random.choice(ALFABETO_CODIGO) for _ in range(TAMANHO_CODIGO))
            if codigo not in self.salas:
                return codigo

    def criar(self) -> tuple[str, SalaComCodigo]:
        codigo = self.gerar_codigo()
        sala = SalaComCodigo()
        self.salas[codigo] = sala
        return codigo, sala

    def marcar_completude(self, codigo: str) -> None:
        sala = self.salas.get(codigo)
        if sala is None:
            return
        if sala.esta_completa():
            sala.incompleta_desde = None
            sala.foi_completada = True
        else:
            sala.incompleta_desde = time.monotonic()

    async def limpar_periodicamente(self) -> None:
        while True:
            await asyncio.sleep(INTERVALO_LIMPEZA_SEGUNDOS)
            agora = time.monotonic()
            expiradas = []
            for codigo, sala in self.salas.items():
                if sala.incompleta_desde is None:
                    continue
                # Uma sala que já foi completada uma vez usa sempre o prazo
                # curto de reconexão, mesmo que os dois slots estejam vazios
                # agora (ver docstring de SalaComCodigo) — só uma sala que
                # NUNCA teve os dois lados usa o prazo longo de "esperando
                # alguém entrar pela primeira vez".
                limite = (
                    TEMPO_GRACA_RECONEXAO_SEGUNDOS
                    if sala.foi_completada
                    else TEMPO_EXPIRACAO_SALA_VAZIA_SEGUNDOS
                )
                if agora - sala.incompleta_desde > limite:
                    expiradas.append(codigo)
            for codigo in expiradas:
                sala = self.salas.pop(codigo)
                sobrevivente = sala.host or sala.guest
                if sobrevivente is not None:
                    await _tentar_enviar(sobrevivente, {"type": "salaEncerrada"})
                print(f"[relay] sala {codigo} expirou e foi encerrada")


async def _tentar_enviar(ws: ServerConnection, mensagem: dict) -> None:
    try:
        await ws.send(json.dumps(mensagem))
    except websockets.exceptions.ConnectionClosed:
        pass


async def _enviar_erro(ws: ServerConnection, codigo_erro: str, mensagem: str) -> None:
    await _tentar_enviar(ws, {"type": "erro", "codigo": codigo_erro, "mensagem": mensagem})


async def _parear(registro: RegistroDeSalas, ws: ServerConnection, codigo: str, sala: SalaComCodigo, papel: str) -> None:
    """Depois que `ws` acabou de ocupar o slot `papel` na `sala`: avisa o
    papel pro próprio ws e, se a sala acabou de ficar completa (os dois
    slots preenchidos), avisa o host. Essa regra única cobre o primeiro
    "entrar", a retomada após a navegação menu->index.html (WS não
    sobrevive a location.href) e a reconexão depois de queda de rede."""
    registro.marcar_completude(codigo)
    await enviar_papel(ws, papel, {"codigo": codigo})
    if sala.esta_completa() and sala.host is not None:
        await enviar_guest_conectou(sala.host)


async def _tratar_conexao(registro: RegistroDeSalas, ws: ServerConnection) -> None:
    codigo: str | None = None
    papel: str | None = None
    try:
        primeira = await ws.recv()
    except websockets.exceptions.ConnectionClosed:
        return

    try:
        msg = json.loads(primeira)
    except (json.JSONDecodeError, TypeError):
        await _enviar_erro(ws, "REQUISICAO_INVALIDA", "primeira mensagem não é JSON válido")
        return

    tipo = msg.get("type")

    if tipo == "criarSala":
        codigo, sala = registro.criar()
        sala.host = ws
        papel = "host"
        registro.marcar_completude(codigo)
        await enviar_papel(ws, papel, {"codigo": codigo})
        print(f"[relay] sala {codigo} criada (host conectado)")

    elif tipo == "entrarSala":
        codigo = msg.get("codigo")
        sala = registro.salas.get(codigo) if codigo else None
        if sala is None:
            await _enviar_erro(ws, "SALA_NAO_ENCONTRADA", f"nenhuma sala com o código {codigo!r}")
            return
        if sala.guest is not None:
            await _enviar_erro(ws, "SALA_CHEIA", "essa sala já tem dois jogadores")
            return
        sala.guest = ws
        papel = "guest"
        await _parear(registro, ws, codigo, sala, papel)
        print(f"[relay] sala {codigo}: guest entrou")

    elif tipo == "retomarSala":
        codigo = msg.get("codigo")
        papel = msg.get("papel")
        sala = registro.salas.get(codigo) if codigo else None
        if sala is None or papel not in ("host", "guest"):
            await _enviar_erro(ws, "SALA_NAO_ENCONTRADA", f"nenhuma sala com o código {codigo!r}")
            return
        setattr(sala, papel, ws)
        await _parear(registro, ws, codigo, sala, papel)
        print(f"[relay] sala {codigo}: {papel} retomou")

    else:
        await _enviar_erro(ws, "REQUISICAO_INVALIDA", f"tipo de mensagem inesperado: {tipo!r}")
        return

    try:
        await bombear(ws, sala)
    finally:
        sala.desconectar(ws)
        vazia = sala.host is None and sala.guest is None
        if vazia and not sala.foi_completada:
            # Nunca teve os dois lados pareados — não há ninguém que possa
            # estar a caminho de volta com esse código, então não faz
            # sentido guardar a sala pro prazo de reconexão.
            registro.salas.pop(codigo, None)
            print(f"[relay] sala {codigo}: vazia, removida")
        else:
            registro.marcar_completude(codigo)
            outra_ponta = sala.host or sala.guest
            if outra_ponta is not None:
                await _tentar_enviar(outra_ponta, {"type": "oponenteDesconectou"})
            print(f"[relay] sala {codigo}: {papel} desconectado")


async def rodar_relay(porta: int) -> None:
    registro = RegistroDeSalas()
    limpeza = asyncio.create_task(registro.limpar_periodicamente())

    async def handler(ws: ServerConnection) -> None:
        await _tratar_conexao(registro, ws)

    async with serve(handler, "0.0.0.0", porta):
        try:
            await asyncio.Future()  # roda pra sempre
        finally:
            limpeza.cancel()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ws-port", type=int, default=int(os.environ.get("PORT", 8765)))
    args = parser.parse_args()

    print("=== O Duelo dos Feiticeiros — relay com código de sala ===")
    print(f"Escutando em ws://0.0.0.0:{args.ws_port}")
    print()

    try:
        asyncio.run(rodar_relay(args.ws_port))
    except KeyboardInterrupt:
        print("\n[relay] encerrado.")


if __name__ == "__main__":
    main()
