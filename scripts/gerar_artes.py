# -*- coding: utf-8 -*-
"""Gera a arte (Stable Image Ultra) de todas as cartas do CSV, exceto Rei Arthur,
que ja tem arte gerada. Salva em arts/<Nome>.png e loga o progresso."""
import os
import time
import requests
import pandas as pd

BASE = "/home/nery/Projects/tcg"
CSV_PATH = f"{BASE}/Cartas do Jogo de Duelo de Feiticeiros - Cartas do Jogo de Duelo de Feiticeiros.csv"
ARTS_DIR = f"{BASE}/arts"
LOG_PATH = f"{BASE}/scripts/gerar_artes.log"
SKIP = {"Rei Arthur"}


def carregar_dotenv(caminho=f"{BASE}/.env"):
    """Le pares CHAVE=valor de um .env simples, sem sobrescrever vars ja exportadas."""
    if not os.path.exists(caminho):
        return
    with open(caminho, encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            chave, valor = linha.split("=", 1)
            os.environ.setdefault(chave.strip(), valor.strip())


carregar_dotenv()
API_KEY = os.environ["STABILITY_API_KEY"]
ENDPOINT = "https://api.stability.ai/v2beta/stable-image/generate/ultra"


def log(msg):
    line = f"{time.strftime('%H:%M:%S')} | {msg}"
    print(line, flush=True)
    with open(LOG_PATH, "a") as f:
        f.write(line + "\n")


def gerar(prompt, out_path, max_retries=3):
    for attempt in range(1, max_retries + 1):
        resp = requests.post(
            ENDPOINT,
            headers={"Authorization": f"Bearer {API_KEY}", "Accept": "image/*"},
            files={"none": ""},
            data={"prompt": prompt, "aspect_ratio": "1:1", "output_format": "png"},
            timeout=120,
        )
        if resp.status_code == 200:
            with open(out_path, "wb") as f:
                f.write(resp.content)
            return True, resp.headers.get("finish-reason", "?")
        if resp.status_code == 429:
            wait = 5 * attempt
            log(f"  429 rate limited, aguardando {wait}s (tentativa {attempt}/{max_retries})")
            time.sleep(wait)
            continue
        # 400/403/413/422/500 etc — nao adianta retry
        return False, f"HTTP {resp.status_code}: {resp.text[:300]}"
    return False, "esgotou tentativas apos 429 repetido"


def main():
    os.makedirs(ARTS_DIR, exist_ok=True)
    open(LOG_PATH, "w").close()

    df = pd.read_csv(CSV_PATH)
    pendentes = df[~df["Nome"].isin(SKIP)]
    total = len(pendentes)
    ok, falha = 0, 0

    for i, (_, row) in enumerate(pendentes.iterrows(), 1):
        nome = row["Nome"]
        out_path = os.path.join(ARTS_DIR, f"{nome.replace(' ', '_')}.png")
        if os.path.exists(out_path):
            log(f"[{i}/{total}] {nome}: ja existe, pulando")
            ok += 1
            continue

        log(f"[{i}/{total}] {nome}: gerando...")
        sucesso, info = gerar(row["Prompt de Arte"], out_path)
        if sucesso:
            ok += 1
            log(f"[{i}/{total}] {nome}: OK ({info})")
        else:
            falha += 1
            log(f"[{i}/{total}] {nome}: FALHOU -> {info}")

        time.sleep(1.5)  # respiro entre chamadas

    log(f"CONCLUIDO. sucesso={ok} falha={falha} total={total}")


if __name__ == "__main__":
    main()
