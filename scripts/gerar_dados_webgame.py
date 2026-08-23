# -*- coding: utf-8 -*-
"""Gera webgame/data.js a partir do CSV do projeto (mesma leitura de game/loader.py).
Roda uma vez; roda de novo se o CSV mudar. Nao usa fetch/JSON em runtime de proposito
(o jogo e aberto via file://, onde fetch() e bloqueado) — os dados viram um literal JS
carregado por <script src="data.js"> classico, igual ao padrao ja usado em gallery.html.
"""
import json
import pandas as pd

CSV_PATH = "/home/nery/Projects/tcg/Cartas do Jogo de Duelo de Feiticeiros - Cartas do Jogo de Duelo de Feiticeiros.csv"
OUT_PATH = "/home/nery/Projects/tcg/webgame/data.js"

df = pd.read_csv(CSV_PATH)

cartas = []
for _, r in df.iterrows():
    tipo = r["Tipo"]
    combatente = tipo in ("Herói", "Monstro")
    cartas.append({
        "nome": r["Nome"],
        "arquivo": f"../cards/{r['Nome'].replace(' ', '_')}.png",
        "tipo": tipo,
        "elemento": None if r["Elemento"] == "-" else r["Elemento"],
        "custoMana": int(r["Custo de Mana"]),
        "resistencia": int(r["Resistência"]) if combatente else None,
        "combate": int(r["Combate"]) if combatente else None,
        "efeito": r["Efeito / Habilidade"],
        "custoHabilidade": int(r["Custo de Habilidade"]) if (combatente and pd.notna(r["Custo de Habilidade"])) else None,
    })

js = "// GERADO por scripts/gerar_dados_webgame.py — nao editar a mao.\n"
js += "const CARTAS = " + json.dumps(cartas, ensure_ascii=False, indent=2) + ";\n"

with open(OUT_PATH, "w", encoding="utf-8") as f:
    f.write(js)

print(f"Gerado {OUT_PATH} com {len(cartas)} cartas.")
tipos = {}
for c in cartas:
    tipos[c["tipo"]] = tipos.get(c["tipo"], 0) + 1
print(tipos)
