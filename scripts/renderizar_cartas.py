# -*- coding: utf-8 -*-
"""Renderiza uma carta PNG por linha do CSV, usando templates/card.css.
Usa a arte em arts/<Nome>.png quando existe; senao deixa a janela de arte em branco.
Cor da carta segue o elemento (Herói/Monstro), ou o tipo (Encantamento = verde,
Maldição = roxo profundo); Domínios ficam no pergaminho neutro padrao.
"""
import os
import shutil
import tempfile
import pandas as pd
from playwright.sync_api import sync_playwright

BASE = "/home/nery/Projects/tcg"
CSV_PATH = f"{BASE}/Cartas do Jogo de Duelo de Feiticeiros - Cartas do Jogo de Duelo de Feiticeiros.csv"
CSS_PATH = f"{BASE}/templates/card.css"
ARTS_DIR = f"{BASE}/arts"
OUT_DIR = f"{BASE}/cards"

COM_STATS = {"Herói", "Monstro"}

# Cada paleta: c1 (mais claro) -> c2 (medio) -> c3 (escuro) -> c4 (acento/sombra)
PALETA_ELEMENTO = {
    "Fogo": ("#ffe2bd", "#f0a25a", "#b14a1c", "#5c1f09"),
    "Água": ("#d2eefc", "#69bfe8", "#23689e", "#0f3252"),
    "Terra": ("#eef0d3", "#b7a35f", "#7a6122", "#3a2d0f"),
    "Vento": ("#f2fbf7", "#b7ded0", "#5c9a88", "#244036"),
}
PALETA_TIPO = {
    "Encantamento": ("#d7f6e2", "#5fce8c", "#1f8c53", "#0c4128"),  # verde
    "Maldição": ("#e6d9f6", "#9a5ed1", "#5a1e93", "#290c49"),      # roxo profundo
}

PAGE_STYLE = """
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; }
  body { display: inline-block; background: transparent; font-family: Georgia, 'Times New Roman', serif; }

  .card__bar-label {
    margin: 0; height: 100%; display: flex; align-items: center;
    padding: 0 5%; font-weight: 700; color: #201a10; white-space: nowrap;
  }
  .card__bar--name .card__bar-label { padding-right: 15%; }
  .card__cost-badge { color: #f1efe6; font-weight: 700; font-size: 0.62em; }
  .card__text-content {
    box-sizing: border-box; height: 100%; padding: 6% 7%;
    display: flex; flex-direction: column;
    color: #2a241a; font-size: 0.85em; line-height: 1.4;
  }
  .card__effect { display: flex; align-items: baseline; }
  .card__ability-badge { flex-shrink: 0; }
  .card__stats { margin-top: auto; padding-top: 10px; font-weight: 700; color: #5a4620; }
"""


def tipo_linha(row):
    tipo = row["Tipo"]
    elemento = row["Elemento"]
    if elemento and elemento != "-":
        return f"{tipo} — {elemento}"
    return tipo


def paleta_da_carta(row):
    tipo = row["Tipo"]
    if tipo in COM_STATS:
        return PALETA_ELEMENTO.get(row["Elemento"])
    return PALETA_TIPO.get(tipo)  # None para Domínio -> pergaminho neutro padrao


def build_html(row, css, art_path):
    nome = row["Nome"]
    custo = row["Custo de Mana"]
    tipo = tipo_linha(row)
    efeito = row["Efeito / Habilidade"]

    art_style = ""
    if art_path and os.path.exists(art_path):
        # apostrofo no nome do arquivo (Joana d'Arc, Fenda de R'lyeh) quebra tanto aspas
        # simples quanto duplas, seja na string CSS ou no atributo HTML — codifica na URL.
        art_url = art_path.replace("'", "%27")
        art_style = f'style=\'background-image: url("file://{art_url}");\''

    paleta = paleta_da_carta(row)
    card_style = ""
    if paleta:
        c1, c2, c3, c4 = paleta
        card_style = f' style="--c1:{c1}; --c2:{c2}; --c3:{c3}; --c4:{c4};"'

    stats_html = ""
    ability_badge = ""
    if row["Tipo"] in COM_STATS:
        stats_html = (
            f'<div class="card__stats">POW {row["Combate"]} '
            f'&nbsp;|&nbsp; RES {row["Resistência"]}</div>'
        )
        custo_habilidade = int(row["Custo de Habilidade"])
        ability_badge = (
            '<span class="card__ability-badge">'
            f'<span class="card__ability-badge-num">{custo_habilidade}</span>'
            "</span>"
        )

    return f"""<!doctype html>
<html><head><meta charset="utf-8">
<style>{css}</style>
<style>{PAGE_STYLE}</style>
</head>
<body>
  <div class="card"{card_style}>
    <div class="card__body">
      <div class="card__bar card__bar--name">
        <p class="card__bar-label"><span>{nome}</span></p>
        <div class="card__cost-badge">{custo}</div>
      </div>
      <div class="card__art" {art_style}></div>
      <div class="card__bar">
        <p class="card__bar-label">{tipo}</p>
      </div>
      <div class="card__text">
        <div class="card__text-content">
          <div class="card__effect">{ability_badge}<span>{efeito}</span></div>
          {stats_html}
        </div>
      </div>
    </div>
  </div>
</body></html>"""


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(CSS_PATH, encoding="utf-8") as f:
        css = f.read()

    df = pd.read_csv(CSV_PATH)
    if "Carta Criada" not in df.columns:
        df["Carta Criada"] != "Sim"

    com_arte, sem_arte = 0, 0
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 900, "height": 1300}, device_scale_factor=2)

        for idx, row in df.iterrows():
            nome = row["Nome"]
            art_path = os.path.join(ARTS_DIR, f"{nome.replace(' ', '_')}.png")
            tem_arte = os.path.exists(art_path)
            com_arte += tem_arte
            sem_arte += not tem_arte

            html = build_html(row, css, art_path if tem_arte else None)
            # set_content() serve a pagina a partir de about:blank, e o Chromium bloqueia
            # `file://` para imagens de fundo nesse contexto. Navegar para um arquivo real
            # (origem file://) permite carregar a arte local.
            with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, dir=OUT_DIR) as tmp:
                tmp.write(html)
                tmp_path = tmp.name
            page.goto(f"file://{tmp_path}", wait_until="load")
            if tem_arte:
                page.wait_for_timeout(80)  # deixa o background-image local decodificar
            card = page.query_selector(".card")
            out_path = os.path.join(OUT_DIR, f"{nome.replace(' ', '_')}.png")
            card.screenshot(path=out_path)
            os.remove(tmp_path)
            df.at[idx, "Carta Criada"] = "Sim"
            print(f"{'[arte]' if tem_arte else '[sem arte]':11} {nome} -> {out_path}")

        browser.close()

    shutil.copy(CSV_PATH, CSV_PATH + ".bak")
    df.to_csv(CSV_PATH, index=False)

    print(f"\nTotal: {len(df)} | com arte: {com_arte} | sem arte (moldura em branco): {sem_arte}")
    print(f"CSV atualizado com a coluna 'Carta Criada' (backup em {CSV_PATH}.bak)")


if __name__ == "__main__":
    main()
