# Motor do Jogo — Arquitetura ECS

Implementação jogável do `GAME_DESIGN.md` em Python, com arquitetura **ECS (Entity-Component-System)**, usando o CSV do projeto como fonte de dados e as cartas já renderizadas em `cards/*.png` na GUI. Fica em `game/`.

## Por que ECS

Uma carta não é uma classe com métodos (`Carta.atacar()`, `Carta.ativarHabilidade()`) — ela é uma **Entidade** (um id) com um conjunto de **Componentes** (dado puro: `CardInfo`, `CombatStats`, `ManaCost`, `AbilityCost`, `Location`...). Toda a lógica de regra mora em **Systems**, que leem/escrevem esses componentes. Isso casa direto com a seção "Vocabulário de Mecânicas" de `GAME_DESIGN.md`: **Ações do Jogador** viram `game/actions.py`, **Gatilhos de Evento** viram assinaturas no `EventBus` (`game/events.py`).

## Módulos

| Módulo | Responsabilidade |
|---|---|
| `ecs.py` | `World`, `Entity`, `Component`, `System` — o framework genérico. |
| `components.py` | Todo componente do jogo (`CombatStats`, `ManaCost`, `AbilityCost`, `Location`, `StatusEffects`, `TurnState`...). |
| `events.py` | `EventBus` (o sistema de notificação) + todo evento (`PhaseChanged`, `SelectionRequested`, `CardDestroyed`...). |
| `deck.py` | `Deck` — sorteia aleatoriamente 1 carta ainda não comprada da sua lista (`draw_random`). O **Panteão é um `Deck` também** (mesma classe), só que a escolha de qual Combatente invocar passa pelo mecanismo de seleção, não por sorteio — ver nota de design no topo do arquivo. |
| `board.py` | `Board`/`BoardSide` — 1 slot de Monstro + 5 slots de Magia por jogador. |
| `selection.py` | Mecanismo de seleção: publica `SelectionRequested`, guarda um callback pendente, dispara ao receber `resolver()`. É o que deixa a GUI (ou um bot) esperar o jogador escolher sem travar o motor. |
| `phases.py` | `PhaseSystem` (troca de fase: SAQUE → INVOCAÇÃO → PRINCIPAL → BATALHA → FINAL → próximo jogador) + `UpkeepSystem` (zera habilidade usada na entrada da Fase de Saque, expira buffs "neste turno" na entrada da Fase Final). |
| `systems.py` | `ResourceSystem` (compra + mana), `CombatSystem` (vantagem elemental, POW vs RES, dano ao jogador quando não há bloqueador), `DestructionSystem` (ponto único onde uma carta morre — limpa o slot do tabuleiro, dispara `CardAboutToBeDestroyed`/`CardDestroyed` e limpa passivos/gatilhos da carta). |
| `triggers.py` | Pilha de gatilhos + efeitos passivos (`registrar_trigger`, `registrar_passivo`, `aplicar_passivos`) — ver seção própria abaixo. |
| `actions.py` | As Ações do Jogador: `SummonAction`, `ActivateAbilityAction`, `ActivateDomainAction`, `PlayEnchantmentAction`, `SetCurseAction`, `ActivateSetCurseAction`, `DeclareAttackAction`, `ShuffleAction`. |
| `effects.py` | O efeito de cada uma das 60 cartas, como composição de ~15 primitivas (`buff`, `curar`, `dano_combatente`, `comprar`, `descartar_aleatorias`, `destruir`, `retornar_ao_panteao`...), usando `EFFECTS.registrar`/`registrar_passivo` + `triggers.registrar_trigger` conforme o caso. |
| `loader.py` | Lê o CSV do projeto e cria as entidades. |
| `controller.py` | `GameController` — a API pública única. |
| `gui.py` | Interface gráfica em Pygame. |
| `demo_sim.py`, `demo_mecanismos.py` | Simulações de texto que exercitam o motor sem GUI (úteis pra testar regra sem abrir janela). |

## Decisões de design que valem registrar

- **O CSV é um pool de 60 cartas únicas, não um deck pronto.** Cada jogador recebe cópias próprias das 40 cartas de suporte (Domínio/Encantamento/Maldição) e sorteia 5 dos 20 Heróis/Monstros pra montar seu próprio Panteão — os dois lados normalmente saem com Panteões diferentes.
- **Dano "direto"/sem combatente-alvo acerta os Pontos de Vida do jogador**, implementando a regra fechada em `GAME_DESIGN.md`.
- **`DestructionSystem` é o único lugar onde uma carta morre.** Um bug real apareceu durante o desenvolvimento — um combatente destruído em combate continuava marcado como `.monstro` ativo e seguia atacando — porque a limpeza do slot estava duplicada em vários lugares. Centralizar resolveu.

## Pilha de eventos, gatilhos e efeitos passivos (`triggers.py`)

Todo efeito de carta é ATIVO (o jogador ativa e resolve na hora — Habilidade, Encantamento, Maldição revelada) ou tem uma parte PASSIVA/de GATILHO (um Domínio "enquanto ativo", uma Maldição que "quando X acontecer, faça Y"). O `EventBus` já mantém um log de tudo que é publicado (`historico` — a "pilha de eventos"); `EventBus.publish` chama `triggers.disparar_triggers(ctrl, evento)` logo depois de empilhar, o que roda a lista de gatilhos registrados (`ctrl.triggers`) contra o TIPO do evento publicado. É o único lugar onde "Quando X"/"Sempre que X" são resolvidos.

- `EFFECTS.registrar_passivo(nome)` — o efeito é reaplicado do zero (limpa e reaplica) a cada Fase Principal de QUALQUER jogador (`triggers.aplicar_passivos`, chamado por `GameController.avancar_fase`), e some quando a carta-fonte é destruída (`DestructionSystem.destruir` chama `remover_passivos_de`). Ex.: Trono de Camelot (+3 Combate nos Heróis do dono enquanto ativo) agora cobre um Herói invocado DEPOIS da ativação e some corretamente quando o Domínio morre — antes disso era aplicado uma vez só, num bug latente onde o buff nunca saía.
- `triggers.registrar_trigger(ctrl, evento_tipo, efeito, condicao=...)` — registra um gatilho que fica esperando aquele TIPO de evento; ex.: Oceano Primordial ("no início do turno...") em `TurnStarted`, Valhalla ("quando um Herói for derrotado...") em `CardAboutToBeDestroyed` (evento pré-destruição com um `contexto["destino"]` mutável, que deixa redirecionar a carta pro Panteão em vez do descarte sem caso especial em `DestructionSystem`).
- Maldições cujo texto descreve uma condição futura (Areias Movediças, Roubo de Essência, Nevoeiro do Pânico, Mente Fraturada, Amnésia Mágica) registram o gatilho ao serem REVELADAS, com `persistente=False` (autolimpam depois de disparar 1x) e `origem_card=None` — a própria carta é destruída pela Ação logo após revelar, o que limparia o gatilho antes dele disparar se ele estivesse amarrado a ela.
- **Bug real corrigido por essa refatoração:** Caixa de Pandora ("ao ter Domínio/Combatente destruído") disparava, antes, quando ELA MESMA era destruída — condição diferente da escrita na carta. Agora o gatilho é em `CardDestroyed`, filtrado por `dono_da_carta(evento.card) == player_id` (o dono da Caixa de Pandora).

## Simplificações que restam (documentadas para não serem lidas como bug)

- Rebote Arcano exige rastrear "o próximo feitiço inimigo" — stub comentado, não modelado.
- Apoio Incondicional precisaria de um mecanismo de "par de alvos vinculados" à parte — placeholder deliberado.
- Praga da Ferrugem depende de um subtipo "Equipamento" que não existe nos dados do CSV atual.

Ver o topo de `game/effects.py` para a lista completa.

## Como rodar

```bash
# simulação de texto (prova que o motor funciona sem GUI)
python3 -m game.demo_sim
python3 -m game.demo_mecanismos   # foco em seleção/notificação/shuffle/Domínio/Encantamento/Maldição

# GUI de verdade (precisa de display)
python3 -m game.gui          # seed aleatória
python3 -m game.gui 42       # seed fixa
```

Na GUI: clique numa carta do Panteão pra invocar (Fase de Invocação), clique no seu combatente em campo pra ativar a Habilidade dele, clique numa carta da mão pra jogar Domínio/Encantamento/Maldição (Fase Principal), botão "Atacar" na Fase de Batalha, "Próxima Fase" sempre disponível. Quando um efeito pede uma escolha (ex.: Ressurreição Arcana), aparece um overlay — clique na carta desejada.

## Versão jogável no navegador

Existe também um port completo destas mesmas regras em JavaScript puro (sem framework, sem build), jogável no navegador contra uma IA de escolha aleatória: `webgame/index.html` (abra direto, é um arquivo local — sem servidor). A arquitetura, as decisões de escopo e o mapeamento módulo a módulo com este motor Python estão documentados no plano salvo em `~/.claude/plans/precious-sprouting-river.md`; resumo rápido:

- `webgame/data.js` é gerado por `scripts/gerar_dados_webgame.py` a partir do mesmo CSV (rode de novo só se o CSV mudar).
- `webgame/engine.js` + `actions.js` + `effects.js` espelham `components.py` + `systems.py` + `phases.py` + `actions.py` + `effects.py` — mesma regra, mesmas simplificações que restam (ver acima), sem ECS genérico (objetos simples bastam pra uma única partida numa página).
- `webgame/triggers.js` espelha `triggers.py` — mesma pilha de gatilhos/passivos, com `TCG.EventBus.emit` chamando `TCG.dispararTriggers` a cada evento.
- `webgame/ai.js` é o oponente: escolhas aleatórias, sempre restritas às ações legais.
- `webgame/ui.js` estende o padrão de hover-preview de `gallery.html` para o tabuleiro e a mão.
- Verificação automatizada: `python3 scripts/testar_webgame_playwright.py` (Playwright headless, mesmo espírito de `demo_sim.py`) — roda partidas completas e checa a regra de informação oculta (Maldição virada para baixo do oponente nunca revela a carta real).
