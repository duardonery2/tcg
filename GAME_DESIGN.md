# O Duelo dos Feiticeiros — Documento de Design

Documento consolidado com a identidade, a narrativa e as regras mecânicas estruturadas para o jogo de cartas.

## Lore

Dois feiticeiros supremos se enfrentam em um combate estratégico pela supremacia arcana. Em vez de lutarem com as próprias mãos, eles rasgam o véu da realidade para invocar Monstros Primordiais e Heróis Lendários diretamente para a arena. Utilizando feitiços antigos, armadilhas traiçoeiras e alterando o próprio campo de batalha a seu favor, o feiticeiro mais astuto dominará os elementos e esmagará as forças de seu oponente.

---

## Preparação e Baralhos

Cada duelista entra na arena portando dois conjuntos distintos de forças:

* **O Panteão:** Um deck especial contendo exatamente **5 Combatentes** (Heróis Lendários ou Monstros Primordiais). Eles não vão para a mão, mas aguardam na zona do Panteão para serem invocados.
* **O Baralho Arcano:** Contém suas cartas de suporte (Encantamentos, Maldições e Domínios).
* **Estado Inicial:** Cada jogador começa a partida com **5 de Mana** na reserva e saca **4 cartas** do Baralho Arcano. O limite máximo permitido na mão é de 6 cartas.

---

## A Estrutura do Turno

O duelo ocorre em turnos sequenciais, divididos rigorosamente em cinco fases:

1. **Fase de Saque:** O jogador da vez compra 1 carta do Baralho Arcano e recebe 2 de Mana para sua reserva — exceto no PRIMEIRO turno de cada jogador, que já começa com a Mana inicial (ver "Preparação e Baralhos" acima) e não soma esse bônus em cima dela. Não há decisão nenhuma aqui — a fase passa direto para a de Invocação assim que compra e mana são resolvidas.
2. **Fase de Invocação:** O feiticeiro pode pagar o custo necessário para trazer um combatente do Panteão para a arena.
3. **Fase Principal:** Momento de usar magias. Pode-se ativar um **Domínio** (destruindo o domínio anterior, pois só pode haver um ativo na mesa), jogar **Encantamentos** da mão ou baixar **Maldições** viradas para baixo (armadilhas ativadas apenas no turno do inimigo).
4. **Fase de Batalha:** O jogador declara um ataque, confrontando a Habilidade de Combate do seu combatente contra a Resistência do inimigo.
5. **Fase Final:** Fase de limpeza, sem ação do jogador. Todo efeito temporário com duração "neste turno"/"até fim de turno" (buffs e debuffs de Habilidade, Encantamento ou Maldição, dos dois lados do campo) expira exatamente aqui — ao fim do turno em que foi aplicado, nunca um turno inteiro depois. Terminada a Fase Final, a vez passa ao oponente e o turno dele começa de novo pela Fase de Saque.

Cada troca de fase é, ela mesma, um evento de jogo (`faseAlterada`/`PhaseChanged`) — cartas podem registrar gatilhos que reagem à entrada numa fase específica, do mesmo jeito que reagem a qualquer outro evento (destruição, ataque declarado, etc.).

---

## Habilidades dos Combatentes

Heróis e Monstros invocados têm uma Habilidade especial impressa na carta, mas ela não é automática: para ativá-la, o feiticeiro precisa pagar o **Custo de Habilidade** em Mana da reserva (mostrado no losango cinza-escuro ao lado do texto de efeito — o mesmo estilo do círculo de custo de invocação, só que em formato de losango). Esse custo é adicional ao custo de invocação já pago para trazer o combatente ao campo.

* Cada Habilidade pode ser ativada **uma vez por turno**, durante a Fase Principal ou a Fase de Batalha (antes de declarar o ataque).
* Pagar o Custo de Habilidade não consome a ação de invocar nem a de atacar — são gastos independentes da mesma reserva de Mana.
* Combatentes sem Mana suficiente na reserva do feiticeiro simplesmente não podem ativar sua Habilidade naquele turno (ela continua em campo, só a ativação fica indisponível).

---

## Combate e Sistema Elemental

Os atributos base dos Heróis e Monstros possuem um limite natural de 20 pontos, que só pode ser quebrado por feitiços. Além disso, as batalhas são definidas pela superioridade das Naturezas Elementais:

* **Água** possui vantagem sobre o **Fogo**.
* **Fogo** possui vantagem sobre o **Vento**.
* **Vento** possui vantagem sobre a **Terra**.
* **Terra** possui vantagem sobre a **Água**.

**Cálculo do dano:** antes de comparar, cada combatente pode ganhar um bônus de **vantagem elemental**: quem tiver a Natureza que leva vantagem sobre a Natureza do oponente ganha **+2 de Combate só para esse confronto** — vale para os dois papéis (atacando ou defendendo), não só para o atacante. Depois disso, o dano é a **diferença** entre o Combate (já com o bônus elemental somado, se houver) dos dois — e essa diferença acerta **quem tiver o Combate menor**, não sempre o defensor: atacar um combatente mais forte machuca o próprio atacante (combatentes parelhos não se machucam, diferença 0). O resultado é descontado da Resistência de quem foi atingido; se ultrapassar a Resistência (chegando a 0, destruindo o combatente), o **excedente é descontado dos Pontos de Vida do feiticeiro dono dele**. Quando não há combatente para bloquear, o dano vai direto para os Pontos de Vida do feiticeiro adversário (ver seção abaixo).

**Recompensa por destruir:** o feiticeiro que **causou** o dano ganha **+1 de Mana** na reserva quando um combatente é destruído em combate — vale para o atacante de costume, para o defensor nos casos em que o dano volta pro próprio atacante por reflexão (Espelho das Ilusões, Retribuição Kármica), e também para o defensor quando o próprio atacante morre por atacar algo mais forte (contra-ataque, ver "Cálculo do dano" acima).

---

## Diretrizes de Design de Combatentes (notas de design para cartas futuras)

Esta seção registra a filosofia de curva de poder e a taxonomia pretendidas para o Panteão. São diretrizes pra orientar a criação de novos Heróis/Monstros — não uma regra que o motor já aplica sobre os 20 Heróis/Monstros existentes.

**Curva de poder — farm antes do finalizador:** a partida deve começar com combatentes fracos, usados pra gerar Mana e comprar cartas ("farm"), abrindo caminho pra invocar combatentes poderosos mais à frente. Um combatente poderoso não deve ser invocável no primeiro turno — na prática, isso significa dar a ele um Custo de Mana alto o bastante pra nunca caber nos 5 de Mana inicial (ver "Preparação e Baralhos").

**Papéis por faixa de Combate (POW):**

| Faixa de POW | Papel | Descrição |
|---|---|---|
| **até 10** | Suporte | Combatente barato focado em busca de carta e farm de Mana, não em brigar. |
| **11–16** | Intermediário | Eficiente em Mana, se sustenta sozinho em campo, e prepara o caminho pro combatente poderoso seguinte. Tipicamente tem Resistência alta e um efeito complementar (não um finalizador). |
| **17–20** | Poderoso | O finalizador do Panteão — nunca deve ser invocável no primeiro turno (ver acima). |

**Função (nova taxonomia, além de Herói/Monstro):** cada combatente também tem uma Função — uma subcategoria dentro de Herói/Monstro: **Guerreiro, Arqueiro, Mago, Dragão, Primordial, Deus, Demônio, Espírito**.

**Efeito primário e secundário:** um combatente pode ter dois efeitos em vez de um — um primário e um secundário. Quando a carta tem os dois, ambos são impressos em fonte reduzida, pra caber os dois no mesmo espaço da carta.

**Elemento:** a lista de Naturezas Elementais de combatente passa a incluir **Neutro**, além de Fogo, Água, Terra e Vento — um combatente Neutro não tem vantagem nem desvantagem elemental contra nenhuma Natureza (ver "Combate e Sistema Elemental" acima).

> Nada disso está implementado no motor ainda (nem no CSV, nem em `game/`/`webgame/`) — é a especificação pra quando novas cartas seguindo essas diretrizes forem adicionadas.

---

## Vocabulário de Mecânicas: Ações do Jogador vs. Gatilhos de Evento

As 64 cartas do Baralho Arcano e do Panteão usam um vocabulário mecânico comum. Vale separar esse vocabulário em dois tipos, porque a diferença importa para saber **quando** algo acontece e **quem** decide que acontece:

* **Ação do Jogador** — o feiticeiro da vez escolhe fazer isso, geralmente pagando um custo, numa fase específica do turno.
* **Gatilho de Evento** — acontece sozinho, como reação a uma condição do jogo (início de turno, uma carta sendo destruída, um ataque sendo declarado). Ninguém "escolhe" ativar; ele simplesmente dispara quando a condição é satisfeita.

### Recursos e zonas

| Recurso / Zona | O que é |
|---|---|
| **Mana** | Reserva pessoal do feiticeiro; paga custos de invocação, habilidade, Encantamentos e Domínios. |
| **Baralho Arcano** | De onde se compra (Encantamentos, Maldições, Domínios). |
| **Mão** | Cartas do Baralho Arcano compradas e ainda não jogadas (máx. 6). |
| **Pilha de Descarte** | Cartas do Baralho Arcano usadas ou descartadas; algumas cartas as recuperam. |
| **Panteão** | Reserva dos 5 Combatentes (Heróis/Monstros) ainda não invocados. |
| **Campo** | Onde ficam o(s) Combatente(s) invocado(s) e o Domínio ativo. |
| **Pontos de Vida do Feiticeiro** | Vida do próprio jogador, separada da Resistência dos combatentes. Começa em 20 (ver seção abaixo). |

### Ações do Jogador

| Ação | Quando | Custo | Exemplo de carta |
|---|---|---|---|
| Invocar um Combatente | Fase de Invocação | Custo de Mana da carta | qualquer Herói/Monstro |
| Ativar a Habilidade de um Combatente ("Habilidade de Mana") | Fase Principal ou de Batalha, 1x/turno | Custo de Habilidade (losango) | Rei Arthur, Surtur, ... |
| Ativar um Domínio | Fase Principal | Custo de Mana da carta (destrói o Domínio anterior) | Vulcão Primordial, Valhalla |
| Jogar um Encantamento | Fase Principal | Custo de Mana da carta | Tomo do Oráculo, Pacto de Sangue |
| Jogar um Encantamento Contínuo | Fase Principal | Nenhuma Mana — um sacrifício próprio, no lugar (ver abaixo) | Oásis do Saara, Geleiras do Ártico, Selva Amazônica |
| Baixar uma Maldição virada para baixo | Fase Principal | Nenhum (grátis) | qualquer Maldição |
| Revelar/ativar uma Maldição já setada | A qualquer momento no turno do oponente | Custo de Mana da carta | qualquer Maldição |
| Declarar um ataque | Fase de Batalha, 1x/turno por combatente, nunca no 1º turno da partida | — | — |

> **Maldição: o custo é pago na ativação, não ao baixar.** Setar uma Maldição virada para baixo é grátis — ela só cobra o Custo de Mana impresso na carta no momento em que é revelada/ativada. Isso significa que dá pra baixar uma Maldição mesmo sem mana nenhuma, mas se não houver mana disponível quando chegar a hora de ativá-la, a ativação falha (a carta continua virada para baixo em campo até haver mana ou até ser destruída por outro efeito).

> **Encantamento Contínuo:** ao contrário de um Encantamento normal (resolve na hora e vai pra Pilha de Descarte), fica em campo — num slot de magia, disputando o mesmo limite de 5 com Domínio/Maldição. Tem Custo de Mana **0**: o preço de entrada é um sacrifício pago na hora de jogar (descartar carta, perder Pontos de Vida, ou reduzir permanentemente o POW/RES do próprio combatente em campo — varia por carta), e o benefício é um bônus de **Mana por turno** enquanto continuar em campo (some se a carta for destruída). Vários podem estar ativos ao mesmo tempo, e os bônus se somam.

> **Nota de consistência:** quatro cartas já citavam "Habilidade de Mana" como um termo do jogo antes de existir uma regra formal para ela — **Templo de Atlântida** (dispara quando um combatente de Água usa uma), **Minotauro** e **Roubo de Essência** (impedem/roubam o uso de uma) e **Amnésia Mágica** (faz uma falhar). A regra da seção "Habilidades dos Combatentes" acima (Custo de Habilidade, losango cinza) formaliza exatamente esse termo: "usar uma Habilidade de Mana" = ativar a habilidade impressa de um combatente pagando seu Custo de Habilidade.

### Gatilhos de Evento

| Gatilho | Dispara quando | Exemplos de carta |
|---|---|---|
| Início de turno | vira o turno | Fenda de R'lyeh (ambos descartam 1), Oceano Primordial (revela o topo) |
| Combatente/Domínio destruído ou derrotado | uma carta em campo morre | Cu Chulainn (dano mútuo), Trono de Camelot (compra 1), Valhalla (volta ao Panteão), Jardins Suspensos (ganha Mana), Caixa de Pandora (oponente descarta 3) |
| Combatente entra em campo | é invocado | Areias Movediças (-5 Resistência), Aperto da Múmia (-5 Resistência/-3 Combate) |
| "Sempre que" uma ação específica ocorre | outra ação dispara a reação | Templo de Atlântida (sempre que usa Habilidade de Mana), Céus de Valíria (sempre que ataca) |
| Combatente é atacado | inimigo declara ataque | Escudo de Gelo Absoluto, Barreira de Vento Cortante, Espelho das Ilusões, Retribuição Kármica |

### Alterações de POW/RES e Mana — sempre resolução de efeito, não zona nova

"Ganhar/perder Combate", "recuperar/perder Resistência" e "ganhar/roubar/perder Mana" não são mecânicas à parte — são apenas o **resultado numérico** de uma Ação do Jogador ou de um Gatilho de Evento acima (ex.: Excalibur é uma Ação de Habilidade que soma +4 de Combate; Fenrir devorando um Domínio é a mesma Ação de Habilidade destruindo uma carta). O limite de 20 pontos em atributos (ver "Combate e Sistema Elemental") se aplica ao resultado final desses efeitos.

---

## Pontos de Vida do Feiticeiro e Condição de Vitória

Cada feiticeiro começa a partida com **20 Pontos de Vida** (mesmo teto usado nos atributos de combate, por consistência). Nenhuma carta ataca a Resistência de um combatente e os Pontos de Vida do feiticeiro ao mesmo tempo — são alvos distintos:

* Efeitos de **"dano direto"** que não têm um combatente-alvo obrigatório — ex.: **Atalanta** ("Causa 5 de dano direto, ignorando combate") e **Surtur** quando o campo inimigo está vazio — atingem os Pontos de Vida do feiticeiro adversário.
* **Condição de vitória:** um feiticeiro perde quando (a) seus Pontos de Vida chegam a 0, **ou** (b) é a vez dele invocar, seu Panteão e seu campo estão vazios, e ele não tem como colocar um Combatente em jogo.

---

## Nota técnica: carregamento dos dados das cartas

Tentativa de leitura de um CSV falhou por causa do nome/caminho do arquivo:

```python
import pandas as pd
df = pd.read_csv('c67ccc8c.csv')
print(df.head())
```

```text
FileNotFoundError: [Errno 2] No such file or directory: 'c67ccc8c.csv'
```

`c67ccc8c.csv` era um nome de arquivo temporário de outro ambiente (não existe neste projeto). O CSV real das cartas está no repositório com o nome:

```
Cartas do Jogo de Duelo de Feiticeiros - Cartas do Jogo de Duelo de Feiticeiros.csv
```

Para carregar corretamente a partir da raiz do projeto:

```python
import pandas as pd
df = pd.read_csv('Cartas do Jogo de Duelo de Feiticeiros - Cartas do Jogo de Duelo de Feiticeiros.csv')
print(df.head())
```

Isso é o mesmo arquivo referenciado (comentado) em `main.py`:

```python
# df = pd.read_csv('Cartas_do_Jogo_de_Duelo_de_Fei.csv')
```

> Atenção: o nome do arquivo comentado em `main.py` (`Cartas_do_Jogo_de_Duelo_de_Fei.csv`) difere do nome real do arquivo no repositório — vale atualizar essa linha para o nome exato acima (ou renomear o CSV) antes de descomentar o carregamento via pandas.
