# CLAUDE.md — volume-scanner-b3

## O que é este projeto

Detector de volume financeiro anômalo na B3. Todo pregão, calcula o z-score do volume de cada papel contra seu próprio histórico recente (janelas de 30, 45 e 60 pregões) e avisa por Telegram todo papel que cruzar o limiar configurado.

A interpretação dos eventos é manual, feita pelo usuário no gráfico. O sistema detecta e apresenta; não julga, não filtra por mérito, não prevê.

**A especificação completa está em `docs/PLANO.md`. Leia antes de escrever qualquer código.**

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

## Padrões de código

- Python 3.11+, type hints obrigatórios, `mypy --strict` limpo.
- `ruff` para lint e format. Sem exceção silenciada sem comentário justificando.
- Cálculos vetorizados. Nenhum loop `for` sobre tickers no caminho quente.
- Todo módulo em `src/scanner/` tem teste em `tests/`.
- Migrations via Alembic. Nunca schema por SQL solto.
- Segredos (Neon, Telegram) só via variável de ambiente. Nunca commitados, nem em exemplo.

## Dados

Fonte única: COTAHIST da B3, registros de largura fixa de 245 bytes. Layout na seção 2 do plano.

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
