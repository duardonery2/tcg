# Gramáticas Livres de Contexto — O Duelo dos Feiticeiros

Duas gramáticas separadas, porque "a linguagem do jogo" existe em dois níveis diferentes:

1. **Gramática do Turno** — a sintaxe das sequências de ações legais dentro de um turno (o "programa" que um jogador executa).
2. **Gramática do Texto de Habilidade** — a sintaxe das frases usadas na coluna `Efeito / Habilidade` das 60 cartas (a mini-linguagem em que as habilidades são escritas).

Ambas usam notação BNF: `::=` define uma produção, `|` é alternativa, `?` é opcional (0 ou 1), `*` é zero ou mais, `+` é uma ou mais, `ε` é a cadeia vazia. Terminais estão em `CAIXA_ALTA` ou entre aspas; não-terminais entre ⟨colchetes angulares⟩.

---

## 1. Gramática do Turno

### Terminais

`COMPRAR`, `GANHAR_MANA`, `INVOCAR`, `ATIVAR_DOMINIO`, `JOGAR_ENCANTAMENTO`, `BAIXAR_MALDICAO`, `ATIVAR_HABILIDADE`, `DECLARAR_ATAQUE`

### Produções

```
⟨Partida⟩       ::= ⟨Turno⟩ ⟨Partida⟩ | ⟨Turno⟩

⟨Turno⟩         ::= ⟨FaseRecurso⟩ ⟨FaseInvocacao⟩ ⟨FaseTatica⟩ ⟨FaseCombate⟩

⟨FaseRecurso⟩   ::= COMPRAR GANHAR_MANA

⟨FaseInvocacao⟩ ::= INVOCAR | ε

⟨FaseTatica⟩    ::= ⟨AcaoTatica⟩ ⟨FaseTatica⟩ | ε

⟨AcaoTatica⟩    ::= ATIVAR_DOMINIO
                   | JOGAR_ENCANTAMENTO
                   | BAIXAR_MALDICAO
                   | ATIVAR_HABILIDADE

⟨FaseCombate⟩   ::= ⟨AcaoDeHabilidade⟩ ⟨Ataque⟩
                   | ⟨Ataque⟩
                   | ε

⟨AcaoDeHabilidade⟩ ::= ATIVAR_HABILIDADE

⟨Ataque⟩        ::= DECLARAR_ATAQUE
```

Cada não-terminal mapeia direto para uma seção de `GAME_DESIGN.md`: `⟨FaseRecurso⟩` é a Fase de Recurso e Compra, `⟨AcaoTatica⟩` é a lista de "Ações do Jogador" da Fase Tática, etc.

### Observação estrutural

Essa gramática não tem recursão aninhada de verdade — `⟨Partida⟩` e `⟨FaseTatica⟩` só repetem um bloco (o equivalente a `*` do Kleene), sem nada tipo parênteses que precisem "casar". Isso significa que a linguagem gerada é, na prática, **regular** (daria pra reconhecer com um autômato finito), não estritamente livre-de-contexto. Escrevê-la como CFG continua correto — toda linguagem regular é um caso particular de livre-de-contexto — só vale registrar que o jogo não tem estrutura recursiva/aninhada no nível do turno.

### Derivação de exemplo

Um turno onde o jogador compra, invoca o Fenrir, ativa um Domínio, joga um Encantamento, ativa a Habilidade do Fenrir e ataca:

```
⟨Turno⟩
⇒ ⟨FaseRecurso⟩ ⟨FaseInvocacao⟩ ⟨FaseTatica⟩ ⟨FaseCombate⟩
⇒ COMPRAR GANHAR_MANA ⟨FaseInvocacao⟩ ⟨FaseTatica⟩ ⟨FaseCombate⟩
⇒ COMPRAR GANHAR_MANA INVOCAR ⟨FaseTatica⟩ ⟨FaseCombate⟩
⇒ COMPRAR GANHAR_MANA INVOCAR ATIVAR_DOMINIO JOGAR_ENCANTAMENTO ⟨FaseCombate⟩
⇒ COMPRAR GANHAR_MANA INVOCAR ATIVAR_DOMINIO JOGAR_ENCANTAMENTO ATIVAR_HABILIDADE DECLARAR_ATAQUE
```

### Restrições semânticas (fora da gramática)

Um CFG só descreve *forma* — não conta pontos nem compara números, então ele aceitaria sequências ilegais como "invocar sem mana" ou "ativar duas habilidades no mesmo turno". Essas regras são semânticas, aplicadas por cima da gramática:

* `INVOCAR` só é válido se não houver combatente ativo em campo (o jogo usa exatamente 1 por vez — ver "combatente ativo" nas cartas).
* Cada token de custo (`INVOCAR`, `ATIVAR_DOMINIO`, `JOGAR_ENCANTAMENTO`, `BAIXAR_MALDICAO`, `ATIVAR_HABILIDADE`) exige Mana suficiente na reserva, debitada no momento da ação.
* `ATIVAR_HABILIDADE` só pode aparecer **uma vez por turno**, mesmo podendo estar na `⟨FaseTatica⟩` ou na `⟨FaseCombate⟩` (a gramática permite os dois lugares; a regra de "uma vez" é contada fora da gramática).
* `⟨Mão⟩` nunca pode ter mais que 6 cartas após `COMPRAR`.
* `⟨Partida⟩` termina quando os Pontos de Vida de um feiticeiro chegam a 0, ou quando ele precisa invocar e não tem combatente disponível — ambas são checagens numéricas/de estado, não parte do CFG.

---

## 2. Gramática do Texto de Habilidade

Descreve o padrão comum às 60 strings de `Efeito / Habilidade` do CSV. É uma gramática *descritiva* (encontrada olhando o corpus real), não prescritiva — cobre a maioria das cartas; frases muito idiossincráticas podem escapar dela.

### Produções

```
⟨Habilidade⟩   ::= ⟨Rotulo⟩? ⟨Gatilho⟩? ⟨Clausula⟩ ("." ⟨Clausula⟩)* "."

⟨Rotulo⟩       ::= NOME_DA_HABILIDADE ":"

⟨Gatilho⟩      ::= "Quando" ⟨Evento⟩ ","
                  | "Se" ⟨Evento⟩ ","
                  | "Sempre que" ⟨Evento⟩ ","
                  | "No início do turno" ","
                  | "Ao ter" ⟨Evento⟩ ","

⟨Evento⟩       ::= ⟨Sujeito⟩ ⟨VerboEvento⟩

⟨Clausula⟩     ::= ⟨Sujeito⟩? ⟨Verbo⟩ ⟨Quantidade⟩? ⟨Recurso⟩? ⟨Modificador⟩*

⟨Sujeito⟩      ::= "Oponente" | "Inimigo" | "Você" | "O combatente" | "O seu combatente" | ε

⟨Verbo⟩        ::= "Ganha" | "Recupera" | "Causa" | "Compre" | "Compra"
                  | "Descarta" | "Destrói" | "Destrua" | "Retorna" | "Retorne"
                  | "Anula" | "Perde" | "Rouba" | "Reduz" | "Ignora" | "Cancele"
                  | "Envie" | "Escolha" | "Revele" | "Embaralhe" | "Sacrifique" | "Inverte"

⟨Quantidade⟩   ::= NUMERO | "todos" | "1" | "2" | "3"

⟨Recurso⟩      ::= "de Combate" | "de Resistência" | "de Mana"
                  | "cartas" | "carta(s) do Baralho Arcano" | "de dano"
                  | "carta de Domínio" | "carta de Maldição" | "Habilidade de Mana"

⟨Modificador⟩  ::= ⟨Duracao⟩ | ⟨Condicao⟩ | ⟨AlvoPreposicional⟩

⟨Duracao⟩      ::= "neste turno" | "até o fim do turno" | "permanente(mente)"
                  | "até o início do seu próximo turno"

⟨Condicao⟩     ::= "se" ⟨Evento⟩ | "ignorando combate"

⟨AlvoPreposicional⟩ ::= "do oponente" | "da mão" | "em campo" | "ao atacante"
```

### Derivações de exemplo

**"Excalibur: Ganha +4 de Combate neste turno."**

```
⟨Habilidade⟩
⇒ ⟨Rotulo⟩ ⟨Clausula⟩ "."
⇒ "Excalibur:" ⟨Verbo⟩ ⟨Quantidade⟩ ⟨Recurso⟩ ⟨Modificador⟩ "."
⇒ "Excalibur:" "Ganha" "+4" "de Combate" "neste turno" "."
```

**"No início do turno, revela a carta do topo do Baralho. Se for de Água ou Encantamento, compra de graça."** *(Oceano Primordial — duas cláusulas, a segunda com sua própria condição)*

```
⟨Habilidade⟩
⇒ ⟨Gatilho⟩ ⟨Clausula⟩ "." ⟨Clausula⟩ "."
⇒ "No início do turno," "revela a carta do topo do Baralho" "."
     ⟨Condicao⟩ "," "compra de graça" "."
⇒ "No início do turno," "revela a carta do topo do Baralho" "."
     "Se for de Água ou Encantamento," "compra de graça" "."
```

**"Quando um Espírito Heróico for derrotado, em vez de ir para a Pilha de Descarte, ele retorna para o Panteão."** *(Valhalla — gatilho + cláusula com alvo preposicional)*

```
⟨Habilidade⟩
⇒ ⟨Gatilho⟩ ⟨Clausula⟩ "."
⇒ "Quando" ⟨Evento⟩ "," ⟨Sujeito⟩ ⟨Verbo⟩ ⟨AlvoPreposicional⟩ "."
⇒ "Quando um Espírito Heróico for derrotado," "ele" "retorna" "para o Panteão" "."
```

### Uso prático

Essa gramática dá dois usos diretos pro projeto:

1. **Geração:** um gerador de cartas novas pode sortear `⟨Verbo⟩ + ⟨Quantidade⟩ + ⟨Recurso⟩ + ⟨Modificador⟩` para produzir habilidades no mesmo estilo das 60 existentes, em vez de escrever cada uma à mão.
2. **Validação:** ao adicionar uma carta nova no CSV, dá pra checar se o texto em `Efeito / Habilidade` "parseia" nessa gramática — se não parsear, é sinal de que o texto fugiu do padrão do resto do baralho (o que pode ser intencional, ou pode ser um lembrete pra revisar a redação).

---

## 3. Validação do corpus (as 60 cartas atuais)

Implementei um parser recursivo-descendente de verdade para a gramática acima (`scripts/validar_habilidades.py`) e rodei contra as 60 strings de `Efeito / Habilidade` do CSV. Resultado, honesto:

| Versão do parser | Resultado | O que mudou |
|---|---|---|
| **v1** — termos exatamente como na 1ª versão desta gramática (verbos como palavra literal, sensível a maiúscula) | **1/60** passam | linha de base |
| **v2** — verbos casados por radical, sem diferenciar maiúscula/minúscula (cobre "ganha/ganham", "compra/compre/compram" etc.), + padrão "N pontos de X", + cláusulas coordenadas com "e" | **3/60** passam | resolveu a maior parte dos casos de verbo não reconhecido |

Cartas que passam na v2: **Rei Arthur**, **Beowulf**, **Tomo do Oráculo**.

### Causa raiz do que ainda falha (57/60)

Investiguei antes de simplesmente alargar listas às cegas — a primeira hipótese ("o Sujeito é uma lista fechada demais") **não bateu com os dados**: contei manualmente e nenhuma falha era só por causa do Sujeito. A causa real, confirmada nos números:

* **~50 falhas eram o Verbo** — a v1 listava cada verbo como uma única palavra exata e capitalizada ("Ganha", "Compre"), mas o corpus conjuga por número/pessoa em qualquer posição da frase ("ganham", "causam", "perdem", "compra" minúsculo no meio da frase). A v2 corrigiu a maior parte disso casando por radical (regex) e ignorando maiúscula/minúscula.
* **O que sobrou (a maioria das 57 falhas restantes) é o complemento, não o verbo.** `⟨Recurso⟩` e `⟨Modificador⟩` foram definidos como listas fechadas de frases curtas e fixas ("de Combate", "do oponente"), mas o objeto real das cláusulas é um **sintagma nominal aberto**, com artigo + adjetivo + núcleo + preposições encadeadas:
  - "**a próxima Maldição** do oponente" (Odisseu)
  - "**um aliado** em campo" (Joana d'Arc)
  - "**carta de Equipamento** do baralho" (Gilgamesh)
  - "**todos os combatentes** em campo" (Surtur)
  - "**a carta de Domínio ativa** no campo" (Fenrir)

  Uma lista fechada de frases nunca vai cobrir isso — sintagma nominal em português é uma classe aberta e recursiva (substantivo + qualquer número de modificadores encaixados), não um vocabulário fixo.

### O que resolveria de vez (não implementado — ficaria grande demais pro parser atual)

Pra fechar essa lacuna de verdade, `⟨Recurso⟩`/`⟨Modificador⟩` precisariam virar um sintagma nominal recursivo:

```
⟨SN⟩   ::= ⟨Det⟩? ⟨Adj⟩? ⟨Nucleo⟩ ⟨PP⟩*
⟨PP⟩   ::= Prep ⟨SN⟩
⟨Det⟩  ::= "a" | "o" | "um" | "uma" | "todos os" | "a próxima" | ...
⟨Adj⟩  ::= "próxima" | "ativa" | "ocultas" | ...
⟨Nucleo⟩ ::= "Maldição" | "aliado" | "carta" | "combatente" | "equipamento" | ...
```

Essa é literalmente a razão clássica pela qual linguagem natural exige gramáticas maiores que gramáticas de brinquedo: o sintagma nominal se auto-referencia via `⟨PP⟩ → Prep ⟨SN⟩` (uma Maldição *do oponente*, um Equipamento *do baralho*, um combatente *do Panteão do oponente*...), then permitindo aninhamento arbitrário. Dá pra construir, mas é um projeto à parte — o parser atual (`scripts/validar_habilidades.py`) já serve bem pro que importa na prática: checar que toda carta tem um **verbo reconhecível no início de cada cláusula**, o que pega erros de digitação/formatação muito mais rápido do que tentar validar a frase inteira.

### Conclusão prática

A gramática da seção 2 captura corretamente o **esqueleto** de uma habilidade (rótulo? + gatilho? + cláusula(s) com Sujeito?+Verbo+Objeto, terminadas em ponto, opcionalmente coordenadas com "e"). Ela não é — e não seria realista tentar torná-la — um parser completo de português; usar como *checagem estrutural leve* ao escrever cartas novas (tem rótulo? tem um verbo reconhecível? termina em ponto?) é o uso que se sustenta sem precisar da extensão de SN acima.
