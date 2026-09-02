# Imagem mínima pro relay com código de sala (scripts/relay_server.py).
# Não inclui o front-end (webgame/) nem os assets (cards/, arts/, sound/) —
# isso mora num host estático separado (ver GAME_ENGINE.md / plano de
# multiplayer); aqui só o que o relay precisa pra rodar.
FROM python:3.13-slim

WORKDIR /app

COPY scripts/requirements.txt scripts/requirements.txt
RUN pip install --no-cache-dir -r scripts/requirements.txt

COPY scripts/relay_core.py scripts/relay_server.py scripts/

CMD ["python3", "scripts/relay_server.py"]
