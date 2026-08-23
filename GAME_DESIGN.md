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

O duelo ocorre em turnos sequenciais, divididos rigorosamente em quatro fases:

1. **Fase de Recurso e Compra:** O jogador da vez compra 1 carta do Baralho Arcano e recebe 2 de Mana para sua reserva.
2. **Fase de Invocação:** O feiticeiro pode pagar o custo necessário para trazer um combatente do Panteão para a arena.
3. **Fase Tática:** Momento de usar magias. Pode-se ativar um **Domínio** (destruindo o domínio anterior, pois só pode haver um ativo na mesa), jogar **Encantamentos** da mão ou baixar **Maldições** viradas para baixo (armadilhas ativadas apenas no turno do inimigo).
4. **Fase de Combate:** O jogador declara um ataque, confrontando a Habilidade de Combate do seu combatente contra a Resistência do inimigo.

---

## Habilidades dos Combatentes

Heróis e Monstros invocados têm uma Habilidade especial impressa na carta, mas ela não é automática: para ativá-la, o feiticeiro precisa pagar o **Custo de Habilidade** em Mana da reserva (mostrado no losango cinza-escuro ao lado do texto de efeito — o mesmo estilo do círculo de custo de invocação, só que em formato de losango). Esse custo é adicional ao custo de invocação já pago para trazer o combatente ao campo.

* Cada Habilidade pode ser ativada **uma vez por turno**, durante a Fase Tática ou a Fase de Combate (antes de declarar o ataque).
* Pagar o Custo de Habilidade não consome a ação de invocar nem a de atacar — são gastos independentes da mesma reserva de Mana.
* Combatentes sem Mana suficiente na reserva do feiticeiro simplesmente não podem ativar sua Habilidade naquele turno (ela continua em campo, só a ativação fica indisponível).

---

## Combate e Sistema Elemental

Os atributos base dos Heróis e Monstros possuem um limite natural de 20 pontos, que só pode ser quebrado por feitiços. Além disso, as batalhas são definidas pela superioridade das Naturezas Elementais:

* **Água** possui vantagem sobre o **Fogo**.
* **Fogo** possui vantagem sobre o **Vento**.
* **Vento** possui vantagem sobre a **Terra**.
* **Terra** possui vantagem sobre a **Água**.

**Cálculo do dano:** quando um combatente ataca outro, o dano é a **diferença** entre o Combate do atacante e o Combate do defensor (nunca negativo — combatentes parelhos ou com o defensor mais forte não causam dano nenhum um no outro). Se o atacante tiver vantagem elemental sobre o defensor, esse dano é multiplicado por 1,5. O resultado é descontado da Resistência do alvo; quando a Resistência chega a 0, o combatente é destruído. Quando não há combatente para bloquear, o dano vai direto para os Pontos de Vida do feiticeiro adversário (ver seção abaixo).

**Recompensa por destruir:** o feiticeiro que destrói o combatente do adversário em combate ganha **+1 de Mana** na reserva — vale tanto para o atacante de costume quanto para o defensor, nos casos em que o dano volta para o próprio atacante por reflexão (Espelho das Ilusões, Retribuição Kármica).

---

## Vocabulário de Mecânicas: Ações do Jogador vs. Gatilhos de Evento

As 60 cartas do Baralho Arcano e do Panteão usam um vocabulário mecânico comum. Vale separar esse vocabulário em dois tipos, porque a diferença importa para saber **quando** algo acontece e **quem** decide que acontece:

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
| Ativar a Habilidade de um Combatente ("Habilidade de Mana") | Fase Tática ou de Combate, 1x/turno | Custo de Habilidade (losango) | Rei Arthur, Surtur, ... |
| Ativar um Domínio | Fase Tática | Custo de Mana da carta (destrói o Domínio anterior) | Vulcão Primordial, Valhalla |
| Jogar um Encantamento | Fase Tática | Custo de Mana da carta | Tomo do Oráculo, Pacto de Sangue |
| Baixar uma Maldição virada para baixo | Fase Tática | Nenhum (grátis) | qualquer Maldição |
| Revelar/ativar uma Maldição já setada | A qualquer momento no turno do oponente | Custo de Mana da carta | qualquer Maldição |
| Declarar um ataque | Fase de Combate, 1x/turno por combatente, nunca no 1º turno da partida | — | — |

> **Maldição: o custo é pago na ativação, não ao baixar.** Setar uma Maldição virada para baixo é grátis — ela só cobra o Custo de Mana impresso na carta no momento em que é revelada/ativada. Isso significa que dá pra baixar uma Maldição mesmo sem mana nenhuma, mas se não houver mana disponível quando chegar a hora de ativá-la, a ativação falha (a carta continua virada para baixo em campo até haver mana ou até ser destruída por outro efeito).

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
