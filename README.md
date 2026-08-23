# O Duelo dos Feiticeiros — Pipeline de Cartas

Como gerar arte e renderizar as cartas finais a partir do CSV. Para as regras do jogo, veja `GAME_DESIGN.md`; para a gramática do texto de habilidade, `GRAMMAR.md`; para a API da Stability, `STABILITY_API.md`; para o motor de jogo (Python/ECS) e a versão jogável no navegador, veja `GAME_ENGINE.md` e `webgame/`.

## Visão geral do fluxo

```
CSV (dados da carta)
   │
   ├─► scripts/gerar_artes.py ──► arts/<Nome>.png        (Stability AI, 1 por carta)
   │
   └─► scripts/renderizar_cartas.py ──► cards/<Nome>.png (moldura + arte + texto)
```

O CSV é a fonte de verdade. Cada linha vira uma imagem de arte em `arts/` e depois uma carta final em `cards/`, com a moldura de `templates/card.css` (cor por elemento/tipo, badge de custo de invocação, losango de custo de habilidade).

## Estrutura do projeto

| Caminho | O que é |
|---|---|
| `Cartas do Jogo de Duelo de Feiticeiros - ....csv` | dados das 60 cartas (uma linha por carta) |
| `templates/card.css` | a moldura da carta (reusável, dirigida por `--card-width` e `--c1..--c4`) |
| `templates/card-template.html` | página de demonstração da moldura (abrir num navegador) |
| `scripts/gerar_artes.py` | chama a Stability AI e salva a arte de cada carta |
| `scripts/renderizar_cartas.py` | monta a carta final (moldura + arte + texto) via Chromium headless |
| `scripts/validar_habilidades.py` | checa o texto de `Efeito / Habilidade` contra a gramática de `GRAMMAR.md` |
| `arts/` | arte gerada pela IA, uma por carta, `1024x1024` |
| `cards/` | cartas finais prontas, uma por carta |
| `.env` | `STABILITY_API_KEY=...` (não commitar; já está fora do que os scripts imprimem) |

## Pré-requisitos

```bash
pip install pandas requests playwright pillow
python3 -m playwright install chromium
```

Crie um `.env` na raiz do projeto com sua chave da Stability:

```
STABILITY_API_KEY=sk-...
```

`gerar_artes.py` lê esse arquivo sozinho (não precisa dar `export` na mão). Rotacione a chave em platform.stability.ai/account/credits se ela já tiver vazado em algum lugar (chat, log, histórico de shell).

## Gerando as cartas do zero (ou depois de mexer no CSV)

```bash
cd /home/nery/Projects/tcg
python3 scripts/gerar_artes.py        # gera a arte que ainda falta em arts/
python3 scripts/renderizar_cartas.py  # monta cards/<Nome>.png para as 60 linhas do CSV
```

Os dois scripts são **idempotentes**: rodar de novo não gera arte duplicada (pula qualquer `arts/<Nome>.png` que já existe) nem quebra nada — só preenche o que falta. `renderizar_cartas.py` sempre re-renderiza todas as 60, porque é rápido (headless, sem chamada de API) e garante que qualquer mudança na `card.css` ou no CSV apareça em todas as cartas.

### Adicionando uma carta nova

1. Adicione uma linha no CSV com `Nome`, `Tipo` (`Herói`/`Monstro`/`Domínio`/`Encantamento`/`Maldição`), `Elemento` (`Fogo`/`Água`/`Terra`/`Vento`/`-`), `Custo de Mana`, `Resistência`/`Combate` (só Herói/Monstro; `-` nos demais) e `Efeito / Habilidade`.
2. Preencha **`Prompt de Arte`** à mão: uma descrição de cena em inglês (1–2 frases, sem texto/letras na imagem) seguida sempre do mesmo sufixo fixo:

   ```
   Epic high fantasy concept art, official Magic The Gathering card art style,
   intricate details, 8k resolution, trending on ArtStation,
   painted by Greg Rutkowski and Tyler Jacobson.
   ```

3. Se for Herói/Monstro, preencha **`Custo de Habilidade`** (1–3, calibrado pela força do efeito — veja a tabela de exemplos em `GAME_DESIGN.md`, seção "Habilidades dos Combatentes"). Deixe em branco para os outros tipos.
4. Deixe `Carta Criada` em branco ou `Não` — os scripts preenchem sozinhos.
5. Rode os dois scripts do fluxo acima.

Não precisa mexer em nomes de arquivo: os scripts derivam `arts/<Nome>.png` e `cards/<Nome>.png` de `Nome.replace(' ', '_')` automaticamente (inclusive nomes com apóstrofo, tipo *Joana d'Arc*).

## Referência dos scripts

### `scripts/gerar_artes.py`
Lê a coluna `Prompt de Arte`, chama `POST /v2beta/stable-image/generate/ultra` (aspect 1:1, PNG) e salva em `arts/<Nome>.png`. Loga cada chamada em `scripts/gerar_artes.log`. Trata `429` com retry/backoff; erros de crédito (`402`) ou moderação (`403`) ficam registrados no log e a carta fica pendente pra próxima rodada. **Cada carta custa 8 créditos Stability.**

### `scripts/renderizar_cartas.py`
Monta cada carta com Playwright + Chromium headless: escreve um HTML temporário (moldura de `card.css` + dados da linha), navega até ele com `file://` (necessário pro Chromium carregar a arte local — `set_content()` bloqueia isso) e tira um screenshot só do elemento `.card`. Aplica a paleta de cor por `Tipo`/`Elemento` (Fogo/Água/Terra/Vento, verde pra Encantamento, roxo pra Maldição; Domínio fica no pergaminho neutro). Ao final, atualiza a coluna `Carta Criada` no CSV e salva um backup (`....csv.bak`).

### `scripts/validar_habilidades.py`
Roda a gramática de `GRAMMAR.md` (seção 2) contra `Efeito / Habilidade` de cada carta e imprime quais passam/falham e por quê. Útil como checagem leve de redação ao escrever uma habilidade nova (tem verbo reconhecível? tem rótulo? termina em ponto?) — não é (nem pretende ser) um parser completo de português; veja a seção "Validação do corpus" em `GRAMMAR.md` pra entender os limites.

```bash
python3 scripts/validar_habilidades.py
```

## Gerando uma carta ou re-render pontual

Pra testar uma carta específica sem rodar tudo, use o próprio `renderizar_cartas.py` como módulo:

```bash
python3 -c "
import sys; sys.path.insert(0, 'scripts')
from renderizar_cartas import build_html, CSS_PATH, ARTS_DIR, OUT_DIR
import pandas as pd, os
from playwright.sync_api import sync_playwright

df = pd.read_csv('Cartas do Jogo de Duelo de Feiticeiros - Cartas do Jogo de Duelo de Feiticeiros.csv')
row = df[df['Nome'] == 'Rei Arthur'].iloc[0]
css = open(CSS_PATH, encoding='utf-8').read()
art = os.path.join(ARTS_DIR, 'Rei_Arthur.png')
html = build_html(row, css, art)
with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page(viewport={'width': 900, 'height': 1300}, device_scale_factor=2)
    page.set_content(html)  # ok aqui so se a carta nao tiver arte; com arte, escreva um arquivo e use page.goto('file://...')
    page.query_selector('.card').screenshot(path=os.path.join(OUT_DIR, 'Rei_Arthur.png'))
    b.close()
"
```

## Notas

* `main.py` é o protótipo original (DALL·E 3) e não faz parte deste pipeline — mantido só como referência histórica.
* Os arquivos `....csv.bak`, `.bak2`, `.bak3` são backups automáticos feitos antes de cada mudança de esquema no CSV; seguro apagar os mais antigos se o histórico não importar.
* `ref/` guarda imagens de referência soltas (não faz parte do pipeline automático).
