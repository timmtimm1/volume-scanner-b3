# CLAUDE.md — volume-scanner-b3

## O que é este projeto

A plataforma pessoal de trades do usuário na B3 (virada decidida por ele em 05/11/2026). O centro são os **setups de compra no diário**: Larry Williams 9.1 a 9.4, 123 de compra, PFR, toque na MMA 20, pullback de rompimento e os candles de reversão em suporte e na média. Para cada setup, a plataforma mostra os armados do dia, avisa quando confirma, mede o resultado em 30 anos de COTAHIST (a suíte de backtest), calcula o lote pelo risco e guarda o diário dos trades dele em R.

O **detector de volume anômalo** continua rodando igual, em segundo plano: todo pregão calcula o z-score do volume de cada papel contra seu próprio histórico recente (janelas de 30, 45 e 60 pregões) e avisa por Telegram todo papel que cruzar o limiar. O volume também entra como item do checklist de cada setup — apoia, não é o foco.

A decisão de entrar é sempre do usuário, no gráfico. O sistema detecta, mede e apresenta; não recomenda e não prevê.

**A especificação completa está em `docs/PLANO.md`. Leia antes de escrever qualquer código.** A plataforma de setups está na seção 14.

## Regras de trabalho

1. Execute fase por fase, na ordem da seção 9 do plano. Um PR por fase.
2. Não avance sem os critérios de aceite da fase atual cumpridos.
3. Se um critério não for atingível como especificado, **pare e reporte**. Não contorne silenciosamente.

## A regra mecânica

Média e desvio da janela usam apenas os N pregões **anteriores** ao dia avaliado: `shift(1)` antes do `rolling(N)`.

Se o dia entra na própria janela, o z-score máximo possível é `(N−1)/√N` = 5,29 para N=30, e o limiar de 6σ nunca dispara. Isso não é preferência de método, é aritmética.

## Escopo — o que NÃO fazer

Não adicione, por iniciativa própria:

- filtro de qualidade, score de confiança ou ranking de "melhores" eventos
- classificação de padrão gráfico ou rótulo preditivo
- backtest, event study ou qualquer estimativa de retorno futuro
- cooldown, teto diário de alertas ou supressão de eventos

Todo evento acima do limiar entra na lista. O único filtro é o piso absoluto de volume em `config.yaml`.

Se você achar que uma dessas coisas melhoraria o sistema, sugira em texto. Não implemente.

## As exceções escritas: Setups e backtest

A lista acima vale para o alerta de 6σ. Os setups e a suíte de backtest são exceções pedidas pelo usuário, com regras próprias, e não mudam nada no alerta:

- **Setups** (21/10/2026 e 05/11/2026): cada setup é uma regra mecânica com nome (`scanner/gatilhos/regra.py` para os candles em suporte e na média, `scanner/gatilhos/classicos.py` para 9.1 a 9.4, 123, PFR, MMA 20 e pullback). Seções 13 e 14 do plano.
- **Backtest** (05/11/2026): `scanner/backtest/` roda na máquina do usuário, sobre o COTAHIST desde 1995 (`scripts/backtest_setups.py`); só o resultado vai para o banco. Todo trade tem um trade de controle (papel sorteado no mesmo dia, mesma saída) — o número que importa é o setup contra o controle, não contra zero.
- Mudar uma regra ou um corte exige refazer a suíte: escolher com 1995–2015 e conferir em 2016–2026, que não pode ser usado para escolher. Setup que falha na conferência continua visível, à parte e com aviso — não some.
- Tendência é etiqueta ("em alta" ou "contra a tendência"), não filtro: os dois grupos aparecem.
- É lente separada: não alimenta, não altera e não suprime o alerta de 6σ. A regra mecânica da seção 1 continua valendo para o alerta.
- Nada de "probabilidade", "chance de subir" ou "recomendação" no texto: a plataforma mostra uma leitura e o que ela fez no passado, não uma promessa. Setups, backtest, lote e diário só para quem está logado.
- O site usa só os 400 pregões do banco. Os 30 anos ficam na máquina do usuário.

## Padrões de código

- Python 3.11+, type hints obrigatórios, `mypy --strict` limpo.
- `ruff` para lint e format. Sem exceção silenciada sem comentário justificando.
- Cálculos vetorizados. Nenhum loop `for` sobre tickers no caminho quente.
- Todo módulo em `src/scanner/` tem teste em `tests/`.
- Migrations via Alembic. Nunca schema por SQL solto.
- Segredos (Neon, Telegram) só via variável de ambiente. Nunca commitados, nem em exemplo.

## Dados

**Preço e volume têm fonte única: o COTAHIST da B3**, registros de largura fixa de 245 bytes. Layout na seção 2 do plano. A regra do alerta nunca depende de outra fonte.

Fora disso, duas fontes entram só para o que o COTAHIST não tem, e nenhuma delas alimenta a regra do alerta:

- **Cotação durante o pregão** (brapi e Yahoo), para os alertas de rompimento e o candle do dia.
- **Balanços e cadastro de empresas** (dados abertos da CVM), para a aba Fundamentos da ficha. A CVM publica uma vez por semana. O código de negociação de cada empresa vem do FCA da CVM; o que faltar é procurado no site da B3 e só é aceito quando a própria B3 lista aquele papel para aquela empresa. **Nunca ligue ticker a empresa pelo prefixo de 4 letras** — o emissor "EMBR" na B3 é a EMBRAST, não a Embraer.

Validação obrigatória do parser: `VOLTOT ≈ PREMED × QUATOT`, tolerância 1%. Falhando em mais de 0,5% das linhas, abortar a carga.

`TOTNEG` é `N(05)` e satura em 99999 — tratar como censurado, não como valor real.

Filtros de ingestão: `TIPREG='01'`, `CODBDI='02'`, `TPMERC='010'`.

Dias sem negociação são `NaN`, nunca zero.

## Interface

A interface não é acessório. Como a leitura dos eventos é manual, a ficha do papel — candles, histograma de volume, marcadores dos eventos anteriores — é onde a ferramenta é efetivamente usada. Trate a seção 6 do plano com o mesmo cuidado do pipeline.

Precisa funcionar em 390px de largura. O usuário abre pelo celular, a partir do link no alerta do Telegram.

## Comandos

```bash
docker compose up -d          # Postgres local
alembic upgrade head          # schema
pytest                        # testes
ruff check . && mypy src/     # qualidade
```

## Comunicação

Responda em português. Ao final de cada fase, resuma o que foi feito, o que os testes cobrem e o que ficou pendente.
