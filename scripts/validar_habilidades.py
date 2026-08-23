# -*- coding: utf-8 -*-
"""Parser recursivo-descendente para a Gramatica do Texto de Habilidade (GRAMMAR.md, secao 2).
Valida cada 'Efeito / Habilidade' do CSV contra a gramatica e reporta PASS/FAIL com motivo.

v2: casamento sem diferenciar maiusculas/minusculas, verbos por radical (cobrindo
flexoes de numero/pessoa), "N pontos de X", e clausulas coordenadas com "e".
"""
import re
import pandas as pd

CSV_PATH = "/home/nery/Projects/tcg/Cartas do Jogo de Duelo de Feiticeiros - Cartas do Jogo de Duelo de Feiticeiros.csv"

# ---- terminais ------------------------------------------------------------
# cada verbo e um radical (regex) casado sem diferenciar maiusculas/minusculas,
# cobrindo as flexoes de numero/pessoa realmente usadas no corpus.
VERBO_RADICAIS = [
    r"ganha(m)?", r"recupera(m)?", r"causa(m)?", r"compr(e|a|am)", r"descart(a|am|e)",
    r"destr(ói|ua|oem|uído)", r"retorn(a|am|e)", r"anul(a|am|ado|e)", r"perd(e|em)",
    r"roub(a|e)", r"reduz(ido|e)?", r"ignora(m)?", r"cancele", r"envi(e|a)",
    r"escolh(a|e)", r"revel(e|a)", r"embaralhe", r"sacrifique", r"inverte",
    r"cura", r"ataca", r"olhe", r"impede", r"força", r"redireciona", r"reflete",
    r"nega(do)?", r"mud(e|a)", r"entra", r"sofre", r"invoca", r"vira", r"deve",
    r"é",
]
VERBO_RE = re.compile(r"^(" + "|".join(VERBO_RADICAIS) + r")\b", re.IGNORECASE)

SUJEITO = ["O seu combatente", "O combatente", "Oponente", "Inimigo", "Você"]
RECURSOS = [
    "de Combate", "de Resistência", "de Mana", "carta do Baralho Arcano",
    "cartas do Baralho Arcano", "cartas", "de dano", "carta de Domínio",
    "carta de Maldição", "Habilidade de Mana",
]
DURACOES = [
    "até o início do seu próximo turno", "até o fim do turno",
    "neste turno", "permanentemente", "permanente",
]
ALVOS_PREP = ["do oponente", "da mão", "em campo", "ao atacante"]
CONDICAO_LITERAL = "ignorando combate"
GATILHOS_SIMPLES = ["No início do turno"]
GATILHOS_COM_EVENTO = ["Quando", "Se", "Sempre que", "Ao ter"]


def match_prefix_ci(text, options):
    """Casa uma das `options` no inicio de `text`, sem diferenciar maiusc./minusc."""
    low = text.lower()
    for opt in sorted(options, key=len, reverse=True):
        if low.startswith(opt.lower()):
            return text[:len(opt)], text[len(opt):].lstrip()
    return None, text


def strip_rotulo(text):
    m = re.match(r'^([A-ZÀ-ÚÇ][^:.]*?):\s*', text)
    if m:
        return m.group(1), text[m.end():]
    return None, text


def strip_gatilho(text):
    for lit in GATILHOS_SIMPLES:
        if text.startswith(lit + ","):
            return lit, text[len(lit) + 1:].lstrip()
    for kw in GATILHOS_COM_EVENTO:
        if text.startswith(kw + " "):
            idx = text.find(",")
            if idx == -1:
                return None, text
            evento_text = text[len(kw) + 1: idx]
            resto = text[idx + 1:].lstrip()
            return (kw, evento_text), resto
    return None, text


def parse_clausula(text):
    """Sujeito? Verbo Quantidade? ("pontos")? Recurso? Modificador* ("e" Clausula)?"""
    partes = []
    restante = text

    subj, r2 = match_prefix_ci(restante, SUJEITO)
    if subj:
        partes.append(("Sujeito", subj))
        restante = r2

    m = VERBO_RE.match(restante)
    if not m:
        trecho = restante[:40] + ("..." if len(restante) > 40 else "")
        return partes, restante, f"esperava um Verbo (nenhum radical conhecido casa), encontrei: ‘{trecho}’"
    partes.append(("Verbo", m.group(0)))
    restante = restante[m.end():].lstrip()

    m = re.match(r'^([+\-]?\d+|todos)\s*', restante)
    if m:
        partes.append(("Quantidade", m.group(1)))
        restante = restante[m.end():]
        m2 = re.match(r'^pontos?\s+', restante, re.IGNORECASE)
        if m2:
            restante = restante[m2.end():]

    rec, r2 = match_prefix_ci(restante, RECURSOS)
    if rec:
        partes.append(("Recurso", rec))
        restante = r2

    progrediu = True
    while progrediu and restante:
        progrediu = False
        dur, r2 = match_prefix_ci(restante, DURACOES)
        if dur:
            partes.append(("Duracao", dur)); restante = r2; progrediu = True; continue
        alvo, r2 = match_prefix_ci(restante, ALVOS_PREP)
        if alvo:
            partes.append(("Alvo", alvo)); restante = r2; progrediu = True; continue
        if restante.lower().startswith(CONDICAO_LITERAL):
            partes.append(("Condicao", CONDICAO_LITERAL))
            restante = restante[len(CONDICAO_LITERAL):].lstrip()
            progrediu = True
            continue

    # coordenacao: "... e <outra clausula>"
    m = re.match(r'^e\s+', restante, re.IGNORECASE)
    if m:
        sub_partes, sub_restante, sub_erro = parse_clausula(restante[m.end():])
        partes.append(("Coordenada", sub_partes))
        restante = sub_restante
        if sub_erro:
            return partes, restante, sub_erro

    return partes, restante, None


def parse_habilidade(efeito):
    texto = efeito.strip()
    rotulo, texto = strip_rotulo(texto)
    gatilho, texto = strip_gatilho(texto)

    if texto.endswith("."):
        texto = texto[:-1]
    clausulas_texto = [c.strip() for c in re.split(r'\.\s+', texto) if c.strip()]

    if not clausulas_texto:
        return {"ok": False, "motivo": "nenhuma clausula encontrada apos rotulo/gatilho"}

    detalhes = []
    ok_geral = True
    for ct in clausulas_texto:
        partes, restante, erro = parse_clausula(ct)
        if erro:
            ok_geral = False
            detalhes.append({"clausula": ct, "ok": False, "motivo": erro})
        elif restante.strip():
            ok_geral = False
            detalhes.append({
                "clausula": ct, "ok": False,
                "motivo": f"sobrou texto nao reconhecido: ‘{restante.strip()}’",
            })
        else:
            detalhes.append({"clausula": ct, "ok": True, "partes": partes})

    return {"ok": ok_geral, "rotulo": rotulo, "gatilho": gatilho, "clausulas": detalhes}


def main():
    df = pd.read_csv(CSV_PATH)
    passou, falhou = [], []

    for _, row in df.iterrows():
        nome = row["Nome"]
        efeito = row["Efeito / Habilidade"]
        resultado = parse_habilidade(efeito)
        (passou if resultado["ok"] else falhou).append((nome, efeito, resultado))

    print(f"PASS: {len(passou)}/60   FAIL: {len(falhou)}/60\n")

    print("=" * 70)
    print("FALHAS")
    print("=" * 70)
    for nome, efeito, resultado in falhou:
        print(f"\n[{nome}] {efeito}")
        for c in resultado["clausulas"]:
            if not c["ok"]:
                print(f"    clausula: ‘{c['clausula']}’")
                print(f"    motivo:   {c['motivo']}")

    print("\n" + "=" * 70)
    print(f"PASSARAM ({len(passou)})")
    print("=" * 70)
    for nome, efeito, _ in passou:
        print(f"  [{nome}] {efeito}")


if __name__ == "__main__":
    main()
