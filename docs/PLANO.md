# Plano de Execução v3 — Detector de Volume Anômalo B3

Documento de especificação para o Claude Code.
Repo: `timmtimm1/volume-scanner-b3`

**Escopo definido:** detectar e avisar. Todo papel que cruzar o limiar de desvios padrão gera alerta. Sem filtro de qualidade, sem classificação preditiva, sem backtest. A leitura do evento é manual, feita no gráfico.

**Consequência de projeto:** a interface é o produto, não um enfeite. Se a interpretação é humana, o gráfico e o contexto do alerta são o que determina se a ferramenta serve ou não.

---

## 1. A regra mecânica que não pode ser violada

O baseline (média e desvio) usa **apenas os N pregões anteriores** ao dia avaliado. `shift(1)` antes do `rolling(N)`.

Motivo: se o dia do pico entra na janela que o mede, ele infla o próprio desvio padrão. O z-score máximo matematicamente possível de uma amostra de N pontos é `(N−1)/√N`:

| Janela | z máximo | 6σ dispara? |
|---|---|---|
| 30 | 5,29 | **Nunca** |
| 45 | 6,56 | No limite |
| 60 | 7,62 | Sim |

Sem o `shift(1)`, a janela de 30 dias é matematicamente incapaz de gerar o alerta que você quer.

---

## 2. Fonte de dados: COTAHIST

Arquivos da B3, registros de largura fixa de 245 bytes. Gratuito, oficial, sem token.

| Campo | Posições | Formato | Uso |
|---|---|---|---|
| TIPREG | 1–2 | N(02) | filtrar `01` |
| DATA | 3–10 | AAAAMMDD | data do pregão |
| CODBDI | 11–12 | N(02) | filtrar `02` (lote padrão) |
| CODNEG | 13–24 | X(12) | ticker |
| TPMERC | 25–27 | N(03) | filtrar `010` (à vista) |
| PREABE | 57–69 | (11)V99 | abertura |
| PREMAX | 70–82 | (11)V99 | máxima |
| PREMIN | 83–95 | (11)V99 | mínima |
| PREMED | 96–108 | (11)V99 | preço médio ponderado |
| PREULT | 109–121 | (11)V99 | fechamento |
| TOTNEG | 148–152 | N(05) | número de negócios |
| QUATOT | 153–170 | N(18) | quantidade de ações |
| VOLTOT | 171–188 | (16)V99 | **volume financeiro em R$** |

Campos `V99` têm 2 decimais implícitos: ler como inteiro, dividir por 100.

**Validação obrigatória do parser:** `VOLTOT ≈ PREMED × QUATOT`, tolerância de 1%. Falhando em mais de 0,5% das linhas, abortar — o parser está desalinhado.

`TOTNEG` é `N(05)` e satura em 99999. Tratar esse valor como censurado.

Arquivo anual para a carga inicial, arquivo diário para o incremental. Verificar o padrão de URL atual na página de cotações históricas da B3 antes de codar o downloader.

---

## 3. Cálculo

### 3.1 Métricas de anomalia

Por janela de 30, 45 e 60 pregões, com baseline deslocado:

- `z_log` — z-score sobre `log(VOLTOT)`. **Métrica primária.** Volume é lognormal; z-score sobre valor bruto torna "6σ" incomparável entre PETR4 e uma small cap.
- `z_raw` — z-score sobre VOLTOT bruto. Persistido como referência.
- `z_robust` — `(x − mediana) / (1,4826 × MAD)` sobre o log. Imune a spike anterior contaminando o baseline.
- `rvol` — VOLTOT dividido pela mediana da janela. Leitura humana direta: "negociou 14× o normal".

### 3.2 Contexto do evento — o que você vai ler na mão

Não filtram nada. São os números que vão no alerta e na tela para você julgar em segundos.

| Feature | Fórmula | O que te diz |
|---|---|---|
| `ret_day` | `PREULT/PREULT_ant − 1` | Direção do dia |
| `clv` | `(C−L)/(H−L)` | Fechou no topo ou no fundo do range |
| `gap` | `PREABE/PREULT_ant − 1` | Notícia overnight ou movimento intradiário |
| `range_norm` | `(H−L)/PREMED` | Amplitude relativa |
| `pos252` | `(C−mín252)/(máx252−mín252)` | Onde está na faixa do ano: 0 = fundo, 1 = topo |
| `ret_prior_20` | retorno dos 20 pregões anteriores | Veio de queda longa ou de alta esticada |
| `avg_ticket` | `VOLTOT/TOTNEG` | **Ticket médio.** Alto = bloco institucional. Baixo com TOTNEG explodindo = correria de varejo |
| `ticket_z` | z-score do ticket vs janela | Normaliza o acima |
| `mkt_vol_z` | z-score do volume agregado do mercado | O mercado inteiro estava assim, ou só este papel? |
| `z_excess` | `z_log − mkt_vol_z` | Anomalia líquida. Separa evento do papel de dia de vencimento ou rebalanceamento |

O `avg_ticket` só existe porque a fonte é COTAHIST — nenhuma API gratuita entrega TOTNEG e VOLTOT juntos. É a informação mais útil do conjunto para leitura manual e vale destaque no README.

### 3.3 Implementação de referência

Vetorizada, sem loop por ticker.

```python
import numpy as np
import pandas as pd

MAD_SCALE = 1.4826


def compute_zscores(df: pd.DataFrame, windows: list[int]) -> pd.DataFrame:
    """df long-format: ticker, trade_date, volume_financial."""
    df = df.sort_values(["ticker", "trade_date"]).copy()
    df["v"] = df["volume_financial"].astype(float)
    df.loc[df["v"] <= 0, "v"] = np.nan  # sem negócio = buraco, não zero
    df["v_log"] = np.log(df["v"])

    out = []
    for w in windows:
        # shift(1) ANTES do rolling: baseline exclui o dia corrente
        prev_log = df.groupby("ticker", group_keys=False)["v_log"].shift(1)
        prev_raw = df.groupby("ticker", group_keys=False)["v"].shift(1)

        def roll(s, fn):
            r = s.groupby(df["ticker"]).rolling(w, min_periods=w)
            return getattr(r, fn)().reset_index(level=0, drop=True)

        mean_log, std_log = roll(prev_log, "mean"), roll(prev_log, "std")
        med_log = roll(prev_log, "median")
        mean_raw, std_raw = roll(prev_raw, "mean"), roll(prev_raw, "std")
        med_raw = roll(prev_raw, "median")

        mad_log = (
            prev_log.groupby(df["ticker"])
            .rolling(w, min_periods=w)
            .apply(lambda x: np.nanmedian(np.abs(x - np.nanmedian(x))), raw=True)
            .reset_index(level=0, drop=True)
        )

        out.append(
            pd.DataFrame(
                {
                    "ticker": df["ticker"].values,
                    "trade_date": df["trade_date"].values,
                    "window_size": w,
                    "z_log": ((df["v_log"] - mean_log) / std_log).values,
                    "z_raw": ((df["v"] - mean_raw) / std_raw).values,
                    "z_robust": ((df["v_log"] - med_log) / (MAD_SCALE * mad_log)).values,
                    "rvol": (df["v"] / med_raw).values,
                }
            )
        )

    return (
        pd.concat(out, ignore_index=True)
        .replace([np.inf, -np.inf], np.nan)
        .dropna(subset=["z_log"])
    )
```

---

## 4. Regra de alerta

Simples e sem julgamento de mérito: cruzou o limiar, avisa.

```yaml
alert:
  metric: z_log             # z_log | z_raw | z_robust
  threshold: 6.0
  windows: [30, 45, 60]
  require_all_windows: false  # false = qualquer janela cruzando dispara
  min_volume_brl: 500000      # piso de sanidade: papel morto não interessa
```

Único filtro é o piso absoluto de volume. Sem ele, uma ação que negocia R$ 3 mil por dia e um dia negocia R$ 40 mil vira 8σ e enche a lista de coisa inoperável.

**Sem cooldown, sem teto diário.** Você pediu todas, e todas aparecem. Dedupe apenas por `(ticker, trade_date)`, para o mesmo evento não notificar duas vezes se o job rodar de novo.

**Expectativa de volume de alertas:** em dias normais, poucos por pregão. Em dia de estresse de mercado, dezenas de uma vez — a correlação entre papéis dispara junto. O `z_excess` na mensagem é o que te permite ignorar essa enxurrada rapidamente: se todo mundo está com `mkt_vol_z` alto, foi o mercado, não os papéis. O `threshold` fica no config para você calibrar depois de ver a realidade por algumas semanas.

### Formato da mensagem

```
⚡ XPTO3 — volume 18,3× o normal

R$ 47,2 mi negociados
z_log: 30d 7,42 | 45d 7,88 | 60d 8,11
z líquido do mercado: 7,60

R$ 12,84 (−7,1%) | gap −2,1%
Fechou a 78% do range do dia
Faixa de 252d: 6% (perto da mínima)
20 pregões anteriores: −24,3%
Ticket médio: R$ 8.420 (z 3,1)

→ [abrir gráfico]
```

O link abre a ficha do papel no site. Do celular, deve ser um toque entre o alerta e o gráfico.

---

## 5. Topologia

Dois planos, porque o pipeline não pode depender do seu PC estar ligado.

| Componente | Onde | Custo |
|---|---|---|
| Banco | Neon (Postgres serverless) | Grátis — 0,5 GB, 100 CU-hours/mês |
| Ingestão + scan diário | GitHub Actions (cron 21:00 UTC, dias úteis) | Grátis em repo público |
| Alerta | Telegram Bot | Grátis |
| Site | Next.js estático na Vercel | Grátis |
| Desenvolvimento | Docker local | Grátis |

Total: **R$ 0/mês.**

O banco hospedado guarda os últimos 400 pregões de barras e a tabela de eventos. Isso cabe em ~60 MB. Histórico mais longo, se quiser, fica em Parquet local.

**Os dados mudam uma vez por pregão.** O Actions termina o scan e dispara rebuild estático na Vercel. Sem API sempre no ar, sem cold start de 50 segundos no 4G, carregamento instantâneo no celular.

Segredos (Neon, Telegram) em GitHub Actions Secrets e variáveis de ambiente da Vercel. Nunca no repo.

---

## 6. Interface

Stack: Next.js + TypeScript + Tailwind + **TradingView lightweight-charts**. Essa biblioteca é gratuita e é o que faz o app parecer ferramenta de mercado em vez de notebook exportado.

### Tela 1 — Scanner do dia

Lista de todos os eventos do pregão, ordenada por `z_log` decrescente. Colunas: ticker, z (maior das janelas), rvol, variação, CLV, ticket médio, volume em R$.

No desktop, tabela densa e ordenável. No mobile (390px), vira lista de cards com ticker, z e variação em destaque e o resto atrás de um toque.

### Tela 2 — Ficha do papel

**Esta é a tela que importa**, porque é onde a leitura manual acontece.

Candlestick com histograma de volume abaixo, escala compartilhada. A barra do evento destacada. Marcadores em todos os eventos anteriores do mesmo papel no histórico disponível — ver que o papel deu 6σ três vezes nos últimos oito meses, e o que o preço fez em cada uma, é exatamente o tipo de coisa que você resolve em cinco segundos no olho e que nenhuma estatística substitui.

Painel lateral com todas as features da seção 3.2 do dia do evento.

### Tela 3 — Histórico

Todos os eventos, filtráveis por período, ticker e faixa de z. Serve para revisitar e para ir construindo seu próprio repertório de padrões.

### Princípios de design

Escuro por padrão. Numerais tabulares (`font-variant-numeric: tabular-nums`) em toda coluna numérica — sem isso as casas decimais dançam e o painel parece amador. Verde e vermelho reservados para direção; nada mais no layout pode usar essas cores. Uma família tipográfica, hierarquia por peso e tamanho. Densidade de informação é a estética correta: terminal, não landing page.

PWA com `manifest.json` e ícones, para instalar na tela inicial do celular e abrir como app.

---

## 7. Estrutura do repositório

```
volume-scanner-b3/
├── src/scanner/
│   ├── config.py             # Pydantic Settings + config.yaml
│   ├── calendar.py           # pregões B3, feriados ANBIMA
│   ├── universe.py           # tickers ativos + filtro de liquidez
│   ├── ingest/cotahist.py    # parser posicional + validação
│   ├── storage/              # models, repository, migrations Alembic
│   ├── metrics.py            # z-scores (seção 3.3)
│   ├── features.py           # contexto do evento (seção 3.2)
│   ├── alerts.py             # regra de disparo + dedupe
│   ├── notify/telegram.py
│   └── cli.py                # Typer
├── web/                      # Next.js
├── tests/
├── docker-compose.yml
├── .github/workflows/daily.yml
└── config.yaml
```

Stack Python: 3.11+, pandas/numpy, SQLAlchemy 2.x, Alembic, Pydantic Settings, Typer, pytest, ruff, mypy.

---

## 8. Modelo de dados

```sql
CREATE SCHEMA IF NOT EXISTS volume_scanner;

CREATE TABLE volume_scanner.daily_bars (
    ticker           TEXT NOT NULL,
    trade_date       DATE NOT NULL,
    open             NUMERIC(18,4),
    high             NUMERIC(18,4),
    low              NUMERIC(18,4),
    close            NUMERIC(18,4) NOT NULL,
    avg_price        NUMERIC(18,4),
    volume_shares    BIGINT,
    volume_financial NUMERIC(20,2) NOT NULL,
    trades_count     INTEGER,
    trades_censored  BOOLEAN NOT NULL DEFAULT FALSE,
    ingested_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (ticker, trade_date)
);
CREATE INDEX ON volume_scanner.daily_bars (trade_date);

CREATE TABLE volume_scanner.volume_metrics (
    ticker      TEXT NOT NULL,
    trade_date  DATE NOT NULL,
    window_size SMALLINT NOT NULL,
    z_log       NUMERIC(10,4),
    z_raw       NUMERIC(10,4),
    z_robust    NUMERIC(10,4),
    rvol        NUMERIC(10,4),
    PRIMARY KEY (ticker, trade_date, window_size)
);

CREATE TABLE volume_scanner.events (
    id                BIGSERIAL PRIMARY KEY,
    ticker            TEXT NOT NULL,
    trade_date        DATE NOT NULL,
    max_z_log         NUMERIC(10,4) NOT NULL,
    triggered_windows SMALLINT[] NOT NULL,
    volume_financial  NUMERIC(20,2) NOT NULL,
    features          JSONB NOT NULL,   -- todo o contexto da seção 3.2
    notified_at       TIMESTAMPTZ,
    UNIQUE (ticker, trade_date)
);
```

---

## 9. Fases

| Fase | Escopo | Critério de aceite |
|---|---|---|
| F0 | Fundação: estrutura, pyproject, ruff, mypy, pytest, docker-compose, Alembic, CLI esqueleto | Os quatro comandos da seção 11 rodam limpos |
| F1 | Calendário B3 + universo com filtro de liquidez | 100% dos feriados 2024–2026 corretos; universo entre 150 e 450 tickers |
| F2 | Parser e carga COTAHIST (2 anos) | Validação `VOLTOT ≈ PREMED × QUATOT` >99,5%; recarga idempotente |
| F3 | Z-scores + features de contexto | Testes da seção 10 passam; recálculo full < 60s |
| F4 | Alertas + Telegram | Spike sintético de 20× dispara 1 alerta com todas as features preenchidas |
| F5 | Deploy: Neon, Actions cron, secrets | Três execuções agendadas consecutivas bem-sucedidas |
| F6 | Interface: scanner, ficha do papel, histórico | Utilizável em 390px; rebuild disparado pelo Actions |
| F7 | PWA | Instalável na tela inicial do celular |

---

## 10. Testes obrigatórios

1. **Baseline não vaza o dia corrente**: série com valor 1000× apenas no último dia deve gerar `z_log > 10` com N=30. Travando abaixo de 5,29, o `shift(1)` está faltando.
2. **Série constante**: desvio zero → `NaN`, nunca divisão por zero.
3. **Histórico insuficiente**: ticker com N−1 pregões produz zero linhas (`min_periods=w`).
4. **Invariância de escala**: multiplicar a série por 1000 não altera `z_log` nem `rvol`.
5. **Buracos**: dias sem negócio viram `NaN`, jamais zero.
6. **Parser**: fixture de COTAHIST real com 100 linhas, todos os campos conferidos contra leitura manual.
7. **Idempotência**: rodar o pipeline duas vezes produz o mesmo estado e um único alerta.
8. **Ticket censurado**: `TOTNEG = 99999` marca `trades_censored` e não gera `avg_ticket`.

---

## 11. Comandos

```bash
docker compose up -d
alembic upgrade head
pytest
ruff check . && mypy src/

scanner ingest backfill --start 2024-01-01
scanner ingest daily
scanner metrics compute --mode incremental
scanner scan --date today --dry-run
scanner scan --date today
scanner report ticker PETR4 --window 60
```

---

## 12. Instrução de arranque para o Claude Code

> Leia este plano inteiro antes de escrever código. Execute fase por fase, um PR por fase, e não avance sem o critério de aceite cumprido.
>
> A seção 1 (baseline deslocado) é mecânica, não estilo: sem o `shift(1)`, a janela de 30 dias jamais atinge 6σ e o sistema nunca alerta. Se parecer complicado de implementar, PARE e reporte.
>
> O escopo é detectar e avisar. Não adicione filtro de qualidade, score de confiança, classificação de padrão ou qualquer heurística que decida por conta própria quais eventos merecem alerta. Todo evento acima do limiar vai para a lista. A leitura é do usuário.
>
> A seção 6 (interface) não é acessório: é onde a ferramenta é usada. Trate a ficha do papel com o mesmo cuidado do pipeline.

---

## 13. Setups — a aba de candles gatilho (decidida em 21/10/2026)

Exceção escrita ao escopo da seção 12, pedida pelo usuário: o volume anômalo é condição necessária, mas a entrada dele acontece quando um candle de reversão aparece num suporte. A aba mostra esses candles, filtrados. Não mexe no alerta de 6σ.

### A regra

| Camada | Regra |
|---|---|
| Candle | Martelo, doji libélula, engolfo de alta, piercing, estrela da manhã. Só contam com a mínima do padrão no suporte. |
| Suporte | Preço onde o preço bate várias vezes e não fecha além, até fechar. 3+ toques do mesmo lado. Rompido, troca de papel uma vez (resistência rompida vira suporte); nível fraco rompido some. |
| Volume | 1,5× a mediana dos 20 pregões anteriores ou mais; destaque a partir de 2,5×. |
| Contexto | Fora de queda recente (−10% em 20 pregões) e de tendência de baixa (abaixo da MM200 caindo). Lateralização e correção em alta aparecem como etiqueta. |
| Espaço | Resistência mais próxima a 2× o risco ou mais (risco = fechamento − mínima do padrão), ou nenhuma acima. |

O candle de força (verde largo saindo do suporte ou rompendo resistência, mesmos filtros) aparece numa seção à parte, com aviso: passou em 1995–2015 e falhou em 2016–2026.

**Na média** (categoria `media`, decidida em 21/10/2026): o mesmo candle de reversão, fora de suporte horizontal, encostando na MME 9 ou na MMA 20 (as médias do gráfico) com a média subindo (acima de 10 pregões atrás), o preço vindo de cima (4 dos 5 fechamentos anteriores acima dela) e o fechamento do candle acima dela. Mesmos filtros de volume, contexto e espaço; seção própria, com alerta de confirmação. No estudo, retorno contra o mercado em 20 pregões de +0,28% em 1995–2015 e −0,34% em 2016–2026 (as duas médias juntas), e trade de referência confirmado de +0,24 R e +0,12 R. A MME 9 sozinha foi positiva nas duas medidas e nos dois períodos; a MMA 20 enfraqueceu em 2016–2026. Juntar a média à regra principal piorou a regra (+0,69% → −0,17% em 2016–2026): por isso a seção é separada.

### O ciclo

1. **Armado** na noite do candle: "confirma acima da máxima".
2. **Confirmado** se o pregão seguinte passar da máxima (entrada de referência: a máxima, ou a abertura se abriu acima). Se não passar, **não confirmou**.
3. Confirmado fica **em andamento** até fechar abaixo da mínima do padrão (`stop`) ou completar 20 pregões (`prazo`).
4. **Histórico** com o resultado (5, 10 e 20 pregões, contra a média do universo líquido) — a conferência ao vivo da regra.

### O estudo que sustenta os cortes

COTAHIST de 1995 a 2026, 1,41 milhão de dias de papel líquido, retorno em excesso à média do mercado em 20 pregões:

| Grupo | 1995–2015 (escolha) | 2016–2026 (conferência) |
|---|---|---|
| Candle no suporte, sem filtro | −0,73% | −0,44% |
| Regra acima | +0,32% | +0,69% |
| Destaque (≥ 2,5×) | +1,09% | +1,88% |

Os intervalos de 95% ainda cruzam o zero: é sinal consistente, não garantia. Esperar a confirmação melhora o trade de referência (stop na mínima, alvo 2R) de +0,02 R para +0,10 R.

### Fases

1. Motor e dados: `scanner.gatilhos`, migration 0013 (`setups`, `niveis`), etapa 6/8 do `scanner daily`. Feita (PR #87).
2. Feita (PR #89). Alerta automático de rompimento um centavo acima da máxima de cada armado, válido só no pregão seguinte (migration 0014: `price_alerts.expira_em` e `setup_id`); mensagem própria quando dispara; bloco "Setups armados" no resumo diário do Telegram.
3. Site: aba Setups (só logado: armados, em andamento, candle de força à parte, histórico com resultado contra o mercado, ao vivo separado dos retroativos), linhas de suporte e resistência na ficha de todo papel (públicas, com botão para esconder) e setas dos setups (só logado). Item Setups no menu.


## 14. Plataforma de setups e suíte de backtest (decidida em 05/11/2026)

O usuário transformou o projeto na plataforma pessoal de trades dele. O foco passa a ser os setups de compra no diário; o alerta de 6σ continua igual, em segundo plano, e o volume vira item do checklist de cada setup. Decisões tomadas em quatro rodadas de perguntas, depois de uma pesquisa sobre as regras e a evidência publicada de cada setup (nenhum tem teste rigoroso publicado na B3; os números que circulam são amostras pequenas, sem custo).

### Os setups

Todos armam no fechamento de `t` e compram R$ 0,01 acima da máxima de `t`, só no pregão seguinte. Stop inicial R$ 0,01 abaixo da mínima do padrão. Código em `scanner/gatilhos/classicos.py`.

| Setup | Regra |
|---|---|
| 9.1 | MME 9 vinha caindo e vira para cima no dia, com a mínima num suporte de 3+ toques e volume de 1,5× ou mais (06/11/2026) |
| 9.2 | MME 9 subindo e fechamento abaixo da mínima do candle anterior; perto da média** e só em tendência* |
| 9.3 | MME 9 subindo e dois fechamentos abaixo do fechamento de `t-2`; perto da média** e só em tendência* |
| 9.4 | MME 9 subia, virou para baixo em `t-1` e volta a subir em `t` sem perder a mínima de `t-1`; stop na mínima de `t-1`; perto da média** e só em tendência* |
| 123 | o candle do meio tem a mínima mais baixa dos três (estrito); stop na mínima dele |
| PFR | mínima abaixo das dos dois candles anteriores e fechamento acima do anterior |
| 123 no suporte | o 123, com a mínima do candle do meio num suporte de 3+ toques (09/11/2026) |
| PFR no suporte | o PFR, com a mínima do dia num suporte de 3+ toques (09/11/2026) |
| MMA 20 | MMA 20 subindo (acima de 10 pregões atrás), fechamento acima da MMA 200, mínima até 1% da MMA 20 e fechamento acima dela |
| Pullback | resistência de 3+ toques rompida no fechamento (vira suporte); a volta até ela em até 20 pregões, com o fechamento segurando o nível |
| Suporte, Na média, Força | as regras da seção 13, inalteradas |

\* Tendência dos 9.2 a 9.4 (pedido de 06/11/2026): MME 80 acima do valor de 20 pregões atrás e topos e fundos ascendentes (último fundo conhecido acima do anterior e último topo acima do anterior; fundo e topo são os pivôs de 3 pregões de cada lado do motor de níveis, conhecidos 3 pregões depois).

\*\* Perto da média (pedido de 09/11/2026): a mínima do candle do sinal a no máximo 0,35 ATR (14 pregões) acima da MME 9; encostar ou furar a média vale. Sem isso o 9.2 a 9.4 não arma.

Versões dos 9.x: as do Palex/TradingView, as mais documentadas. Tendência é etiqueta: "em alta" = fechamento acima da MMA 200 e MMA 200 acima de 20 pregões atrás.

### A suíte de backtest

Roda na máquina (`scripts/backtest_setups.py processar` e `relatorio`), sobre o COTAHIST de 1995 a hoje, preços ajustados por desdobramento (não por provento). Universo de cada dia sem olhar o futuro: mediana do volume dos 60 pregões anteriores acima de R$ 500 mil em dinheiro de hoje (escalado pelo tamanho do mercado de cada época).

- **Entrada:** no gatilho, ou na abertura se abriu acima; se o pregão seguinte não chega ao gatilho, não houve trade.
- **Saídas** (escolha do usuário): alvo de 1, 2 ou 3 R; stop móvel na menor mínima dos 2 últimos candles; saída na abertura seguinte ao fechamento que vira a MME 9 para baixo. Teto de 60 pregões em todas.
- **Conservador onde a ordem dos preços no dia é desconhecida:** mínima no stop no dia da entrada conta como stop; stop e alvo no mesmo dia contam como stop; gap abaixo do stop sai na abertura.
- **Custo:** 0,08% por lado (0,03% de taxas da B3 + 0,05% de derrapagem).
- **Um trade por vez** por papel e setup.
- **Controle:** para cada trade, um papel sorteado entre os líquidos do mesmo dia, comprado na abertura seguinte, com stop à mesma distância e a mesma saída. O setup só vale alguma coisa se ganhar do controle.
- **Números:** expectativa em R líquida, intervalo de 95% por bootstrap por mês, acerto, payoff, fator de lucro, dias, % por motivo de saída, ano a ano e curva de R acumulado.
- **Protocolo:** para cada setup, a melhor combinação de saída e tendência é escolhida só com 1995–2015 (mínimo de 100 trades) e conferida uma vez em 2016–2026. Três níveis, pela conferência (decisão de 05/11/2026): **firme** (intervalo de 95% acima de zero e ganha do controle), **fraco** (positivo e ganha do controle, mas o intervalo cruza o zero) e **falhou** (o resto).
- **Volume:** só etiqueta (volume do dia do sinal sobre a mediana dos 20 anteriores), mostrada no app; não entra na escolha (decisão de 05/11/2026).

### Resultado da primeira rodada (COTAHIST até 09/10/2026, 1,41 milhão de trades)

| Setup | Escolhida em 1995–2015 | 1995–2015 | 2016–2026 [IC 95%] | Contra o controle em 2016–2026 | |
|---|---|---|---|---|---|
| Força | MME 9, em alta | +0,21 R | +0,31 R [+0,09; +0,54] | +0,32 R | firme |
| 9.4 | MME 9, em alta | +0,21 R | +0,04 R [−0,06; +0,12] | +0,02 R | fraco |
| Suporte | alvo 3R, em alta | +0,06 R | +0,03 R [−0,22; +0,28] | +0,01 R | fraco |
| 9.1 | MME 9, em alta | +0,09 R | +0,01 R [−0,08; +0,10] | −0,04 R | falhou |
| 123 | alvo 3R, em alta | +0,11 R | +0,03 R [−0,08; +0,12] | −0,04 R | falhou |
| 9.2 | MME 9, em alta | +0,41 R | −0,05 R [−0,20; +0,09] | −0,19 R | falhou |
| 9.3 | MME 9, em alta | +0,03 R | +0,06 R [−0,07; +0,18] | −0,05 R | falhou |
| PFR | alvo 3R, em alta | +0,05 R | +0,00 R [−0,10; +0,10] | −0,05 R | falhou |
| MMA 20 | alvo 3R, em alta | +0,05 R | −0,00 R [−0,11; +0,09] | −0,06 R | falhou |
| Na média | alvo 3R, contra | +0,51 R | −0,13 R [−0,44; +0,20] | −0,36 R | falhou |
| Pullback | MME 9, contra | −0,03 R | −0,06 R [−0,19; +0,08] | −0,15 R | falhou |

Leitura: só a Força tem intervalo acima de zero, e com poucos trades (404) e resultado puxado por poucos ganhos grandes (mediana −0,27 R; média sem os 5% de cada ponta +0,06 R). Os setups clássicos ficam perto de zero depois do custo e, em 2016–2026, quase todos perdem do controle: o que parecia ganho era o mercado subindo. A saída pela MME 9 (deixar o lucro correr) é a melhor em quase todo setup; alvo fixo de 1 ou 2 R fica negativo na maioria.

### Fases

1. Motor dos setups clássicos, suíte de backtest local, testes, este plano e o CLAUDE.md. Feita (PR #95).
2. Feita (PR #96). Resultado no banco e a página Backtest no app (`/setups/backtest`, só logado): escolher setup e variação; números, curva, ano a ano e lista de trades. Migration 0016: uma rodada por envio (`scripts/backtest_setups.py enviar`), com a grade, a escolha e o nível de cada setup, o ano a ano, a curva mensal e os 200 trades mais recentes de cada setup e saída; ficam as duas últimas rodadas (uns 13 MB cada).
3. Feita (PR #97). Setups no pregão diário. Decisões de 05/11/2026, depois de medir que os clássicos armam mais de 100 por pregão (123 ~35, 9.1 ~25, PFR ~18, 9.4 ~6):
   - pipeline: os clássicos gravados todo dia na tabela `setups`, com a etiqueta de tendência; migration 0017 (`saida_regra`, `alta`, estados `alvo`/`movel`/`mme9`, tabela `setup_preferencias`);
   - saída do "em andamento": escolhida por setup no app (padrão: a do backtest), gravada na linha quando o setup arma; o estado é a conta do `simulador` do backtest;
   - alerta liga/desliga por setup no app; padrão `setups.padroes` do `config.yaml` (ligado em Força e Suporte; o 9.4 também até 10/11/2026, quando caiu para "falhou" com o filtro de tendência);
   - passado de 400 pregões só para setup com alerta ligado (os outros começam na estreia; o passado deles está no Backtest);
   - Telegram: lista só os setups com alerta ligado e uma linha com a contagem dos outros;
   - site: na aba, os setups com alerta ligado em cima e "Outros setups" em blocos fechados com o nível do backtest; alerta e saída escolhidos ali; etiquetas de tendência e volume; Setups é o 1º item do menu e o atalho do celular abre nela (a inicial pública continua o scanner); setas e linhas de entrada/stop/alvo na ficha só dos setups com alerta ligado.
4. Calculadora de lote e diário ligado ao setup (migration 0018):
   - lote: capital e risco por trade salvos na conta (`perfil_de_risco`, risco padrão 1%); ações inteiras (fracionário), o menor entre capital × risco ÷ (entrada − stop) e capital ÷ entrada. Aparece em cada setup armado e no "Entrei";
   - diário: botão "Entrei" no setup confirmado, com papel, data, entrada, stop e o lote já preenchidos (`trades.setup_id`); no formulário comum, campos setup e stop para trade feito fora do site (`trades.categoria_setup`, `trades.stop`);
   - resultado em R = resultado total ÷ risco em reais (soma das compras × (preço − stop)); na página Trades, o resultado por setup (encerrados, acerto, média e soma em R), em ordem fixa.

### Os filtros dos 9.x (06/11/2026)

Pedido do usuário: 9.2 a 9.4 só em tendência (média de 80 inclinada para cima e topos e fundos ascendentes), e o 9.1 só em suporte com volume, para filtrar melhor os trades e subir o acerto. Medido antes de ir ao ar, com o protocolo de sempre:

- **Média de 80:** simples ou exponencial, escolhida pela média dos 9.2 a 9.4 em 1995–2015 (regra fixada antes de ver o resultado): MME 80 com +0,28 R por trade, contra +0,10 R da MMA 80. "Subindo" é acima do valor de 20 pregões atrás (escolha do usuário).
- **O que mudou** (saída pela MME 9, todos os trades; antes → depois):

| Setup | Trades em 30 anos | Acerto 1995–2015 | Acerto 2016–2026 | R por trade 2016–2026 | Contra o controle 2016–2026 |
|---|---|---|---|---|---|
| 9.1 (suporte + volume) | 71 mil → 2,8 mil | 30% → 34% | 28% → 28% | +0,02 → +0,01 | −0,05 → −0,07 |
| 9.2 (tendência) | 9 mil → 2,9 mil | 25% → 26% | 25% → 26% | −0,06 → −0,08 | −0,20 → −0,26 |
| 9.3 (tendência) | 33 mil → 10,6 mil | 26% → 26% | 26% → 27% | −0,00 → +0,00 | −0,13 → −0,09 |
| 9.4 (tendência) | 14,5 mil → 3,8 mil | 33% → 34% | 30% → 31% | +0,04 → +0,04 | −0,02 → −0,04 |

Leitura: os filtros cortam de 2/3 a 96% dos sinais, o que tira ruído da aba, mas o acerto quase não muda (0 a 4 pontos) e a melhora que aparece em 1995–2015 não se repete em 2016–2026. Com alvo de 2R o 9.4 melhora um pouco nos dois períodos (acerto 38% → 41% e 36% → 37%; contra o controle −0,04 → +0,03 R em 2016–2026). Na conferência, o 9.4 cai de "fraco" para "falhou" na combinação escolhida, e o 9.1 continua em "falhou". Os filtros ficaram porque foram pedidos; esta tabela é a referência para revê-los.

### Perto da MME 9 nos 9.2 a 9.4 (09/11/2026)

Pedido do usuário: os 9.2, 9.3 "e afins" têm de acompanhar a média de 9; com o candle longe dela, não é o setup, e a lista trazia muitos casos assim.

- **Pesquisa.** Lidos o blog do Palex (2014), o livro dele, FL Journal e Scanner da Bolsa. Nenhuma fonte dá um número para a distância; o curso do Palex lista a "proximidade da mm9" entre as características desejáveis dos setups de correção. As fontes divergem no candle de referência do 9.2 (o de maior fechamento da perna, no Palex; o candle anterior, nos scripts) e todas descrevem um gatilho que desce para a máxima seguinte enquanto a MME 9 não vira, que o sistema não implementa (o setup vale só o pregão seguinte).
- **Conferência com o usuário.** 54 casos reais de 2026 (24 de 9.2, 21 de 9.3, 9 de 9.4), marcados um a um como "é o setup" ou "não é", sem ver o que veio depois. A distância da mínima do candle do sinal até a MME 9, em ATR, explica 46 das 54 marcações: ele aceitou 24 dos 29 casos com a mínima até 0,35 ATR acima da média e recusou 22 dos 25 acima disso (qualquer corte entre 0,32 e 0,39 dá esse acerto; ficou 0,35). Exigir a referência no maior fechamento da perna não bateu com as marcações (ele aceitou 8 casos sem isso) e ficou de fora.
- **Regra.** Mínima do candle do sinal ≤ MME 9 + 0,35 ATR (`RegrasClassicas.perto_9x`). Vale junto com o filtro de tendência.
- **O que mudou no backtest** (saída pela MME 9, todos os trades, já com o filtro de tendência; antes → depois).:

| Setup | Trades em 30 anos | Acerto 1995–2015 | Acerto 2016–2026 | R por trade 2016–2026 | Contra o controle 2016–2026 |
|---|---|---|---|---|---|
| 9.2 | 2,9 mil → 2,3 mil | 26% → 26% | 26% → 26% | −0,08 → −0,07 | −0,26 → −0,10 |
| 9.3 | 10,6 mil → 9,5 mil | 26% → 27% | 27% → 28% | +0,00 → +0,02 | −0,09 → −0,07 |
| 9.4 | 3,8 mil → 3,7 mil | 34% → 33% | 31% → 31% | +0,04 → +0,04 | −0,04 → −0,01 |

Leitura: a regra tira da lista o que o usuário não reconhece como o setup (19% dos 9.2, 10% dos 9.3, 2% dos 9.4), mas o resultado não muda: os três continuam em "falhou" na conferência (o controle é sorteado, então a coluna contra o controle oscila alguns centésimos de uma rodada para outra). É um acerto de definição, não uma melhora de retorno. Os 8 casos em que a distância não explica a marcação têm, em parte, a média quase parada (fechamento colado nela); com 4 casos, não virou regra.

### 1-2-3 e PFR no suporte (09/11/2026)

Pedido do usuário: análises de reversão e padrões de compra em região de suporte.

- **Pesquisa.** Nos estudos com custo e correção de garimpo de dados, candle sozinho não dá vantagem (Marshall, Young e Rose); os padrões de 3 candles sobrevivem, e só por poucos dias (Caginalp e Laurent; Lu, Chen e Hsu). Nas contagens do Bulkowski, a taxa de virada é 78% na estrela da manhã, 75% no três por fora, 63% no engolfo, 60% no martelo e 53% no harami. Falso rompimento (spring de Wyckoff, turtle soup de Raschke) não tem estatística publicada confiável. Nada disso foi medido na B3.
- **Conferência com o usuário.** 52 casos reais de 2026, 4 por padrão, marcados como "entraria" ou "não entraria" sem ver o que veio depois: os 5 padrões da seção 13 e 8 candidatos novos. Aprovados: martelo 4 de 4, 1-2-3 no suporte 4 de 4, engolfo 3, libélula 3, PFR no suporte 3, estrela 2, três por fora 2, harami 1, martelo invertido 1, piercing 1, pinça de fundo 1, falso rompimento 1, três por dentro 0. Toques do suporte, volume, ter furado o suporte, risco e queda recente têm a mesma mediana entre aprovados e recusados. Com 4 casos por padrão isso escolhe o que medir, não fixa regra.
- **O que entrou.** `123_suporte` e `pfr_suporte`: a regra de sempre de cada um, com a mínima do padrão num suporte de 3+ toques do motor de níveis (`RegrasClassicas.toques_suporte`). São setups à parte; o 123 e o PFR soltos continuam. Os outros seis candidatos ficaram de fora.
- **Medição** (1995–2015 escolhe, 2016–2026 confere):

| Setup | Escolhida em 1995–2015 | 1995–2015 | 2016–2026 [IC 95%] | Contra o controle em 2016–2026 | |
|---|---|---|---|---|---|
| 123 no suporte | alvo 3R, em alta | +0,05 R | −0,01 R [−0,13; +0,10] | −0,06 R | falhou |
| PFR no suporte | alvo 3R, em alta | −0,01 R | −0,04 R [−0,16; +0,08] | −0,05 R | falhou |

Leitura: exigir o suporte não melhora o 1-2-3 nem o PFR; os dois ficam em "falhou", como as versões soltas (na mesma rodada: 123 +0,03 R e PFR +0,00 R na conferência, os dois perdendo do controle). O suporte corta os sinais a cerca de um quarto. Entraram porque foram pedidos, com o alerta desligado por padrão (a regra da casa: alerta ligado só em firme e fraco) e a saída padrão de alvo 3R. Esta tabela é a referência para revê-los.

### Entradas de hoje: a aba simples (11/11/2026)

Pedido do usuário: a aba Setups estava confusa, com um bloco por setup e informação demais em cada cartão. Ele quer ver as possíveis entradas de um jeito direto, para trades de poucos dias com pouco capital. Decisões tomadas em três rodadas de perguntas:

- **Uma lista só**, "Entradas de hoje", com todos os setups armados juntos. Em andamento, Encerrados e Ajustes dos setups (alerta, saída, perfil de risco, conferência ao vivo) ficam recolhidos embaixo.
- **O cartão** responde cinco perguntas: o que é (papel, setup, tendência), onde entra ("Compra acima de"), quanto perde se der errado, quanto ganha se der certo, e o que o setup fez no passado. Mais um mini gráfico dos últimos 30 candles com as linhas de entrada, stop e alvo, e uma régua stop–entrada–alvo na proporção certa. Suporte, toques, resistência e contexto saíram do cartão: estão na ficha do papel.
- **Se der errado:** a perda no stop, em % e em reais para o lote do perfil; em letra menor, a pior fase do setup (abaixo).
- **Se der certo:** o alvo, em % e em reais, e o ganho médio histórico dos trades que deram lucro. Nas saídas sem alvo fixo (MME 9, mínimas) vale só o ganho médio, e o cartão diz como o trade termina.
- **Semáforo** = a nota do backtest, não uma probabilidade: verde (firme), amarelo (fraco), vermelho (falhou), pela mesma regra dos três níveis, medida em 2016–2026 **com a saída do setup e a tendência do papel** (um Força contra a tendência é julgado pelos Força contra a tendência). Combinação sem trades fica cinza, "sem histórico". O usuário pediu "as chances de dar bom"; ficou a nota do histórico porque taxa de acerto sozinha engana: alvo de 1R acerta perto de 50% e perde dinheiro depois do custo.
- **Ordem:** verdes, amarelas, vermelhas; dentro da cor, mais volume primeiro. Todas aparecem. No topo, a contagem por cor.
- **Bolso:** entrada em que nem 1 ação cabe no risco do perfil fica escondida, com aviso de quantas são e um botão que as abre. Sem capital salvo, tudo aparece só em percentual.
- **Saída:** cada setup usa a melhor saída do backtest (o padrão de `setup_preferencias`), e ela vale para o cartão, o acompanhamento e os alertas. O usuário cogitou alvo de 2R para sair mais rápido; desistiu ao ver que, com 2R, nenhum setup fica verde. Se ele trocar a saída em Ajustes, a nota passa a ser a daquela saída, e a tela avisa qual é a melhor do backtest.

**Pior fase** (`scanner.backtest.metricas.pior_fase`, migration 0020: `pior_sequencia` e `pior_recuo` em `backtest_resultados`). A curva da suíte soma todos os papéis e não serve para uma pessoa (um setup com dez sinais por dia "perde 40 seguidas" numa semana). A medida nova simula quem opera **um trade por vez**: entra num sinal, espera sair, pega um sinal do primeiro dia seguinte que tiver algum (sorteado entre os daquele dia). São 200 caminhos; de cada um saem a maior sequência de perdas e o maior recuo do R acumulado, e o número gravado é a mediana. No cartão o recuo vira reais (R × a perda do lote). Sobre os trades da rodada de 10/11/2026, no histórico inteiro e na combinação escolhida: Força 8 perdas seguidas e −20,5 R; Suporte 12 e −31 R; 9.4 15 e −31 R; 9.2 27 e −79 R. As colunas antigas da grade não mudaram (diferença zero contra a rodada anterior).

Site: `web/src/lib/entradas.ts` (as contas, com teste), `entradas-dados.ts` (as consultas; sem a migration 0020 a linha da pior fase some do cartão), `components/CartaoDeEntrada.tsx`, `AjustesDosSetups.tsx`, `SecaoRecolhida.tsx` e `app/setups/page.tsx`. Saíram `ListaDeSetups.tsx`, `BlocoDeSetup.tsx` e o cartão armado antigo.

### Varredura de padrões de candle (11/11/2026)

Pedido do usuário: procurar nas bibliotecas abertas algum padrão de candle que passe no critério dos setups. `scripts/estudo_candles.py` detecta os 62 padrões do `pandas-ta-classic` (os 61 do TA-Lib em Python puro, mais `inside`; instalado só para o estudo, fora do `pyproject`) e testa cada um como dois sinais de compra: o sinal de alta (`NOME+`) e a falha do sinal de baixa (`NOME-`, o preço passa da máxima no pregão seguinte). Mesma entrada, stop na menor mínima dos candles do padrão, mesmas cinco saídas, custo e controle da suíte (`trades_dos_sinais`, que saiu de dentro de `rodar_lote` sem mudar o resultado dela). 1.180 papéis, COTAHIST até 09/10/2026.

Resultado, com o protocolo de sempre (escolher em 1995–2015, conferir em 2016–2026): dos 72 sinais com 100 trades ou mais na escolha, **57 falharam, 12 ficaram fracos e 3 firmes**. Com 72 conferências, uns 2 passariam do intervalo de 95% só por acaso; por isso o relatório tem um critério rígido (piso do intervalo com correção de Bonferroni), e **nenhum dos três passa nele**.

| Sinal | Escolhida | 2016–2026 | Piso 95% | Contra o controle | Trades |
|---|---|---|---|---|---|
| Advance block, falha | alvo 3R, em alta | +0,18 R | +0,02 | +0,04 R | 922 |
| Marubozu de alta | MME 9, em alta | +0,12 R | +0,01 | +0,03 R | 5.027 |
| Closing marubozu de alta | MME 9, em alta | +0,10 R | +0,01 | +0,02 R | 10.817 |

Leitura: nenhum padrão novo merece virar setup. Os dois marubozu são o candle de Força da casa em versão mais frouxa (candle verde cheio, em alta, saída pela MME 9), e ganham do controle por 0,02 a 0,03 R, contra +0,30 R do Força. A varredura confirma por outro caminho o que a suíte já dizia: o que funciona é candle de força em tendência de alta, deixando o lucro correr; desenho de reversão não ganha do papel sorteado. A grade completa fica na máquina (`data/backtest_setups/v7_candles/escolha.csv`).

### Variações do Força: mais sinais e stop mais curto (11/11/2026)

Pedido do usuário, depois da varredura: o Força é o único firme, mas arma pouco (uns 38 trades por ano no mercado inteiro) e o stop na mínima do candle fica a 7% da entrada em média, o que encolhe o lote de quem tem pouco capital. `scripts/estudo_forca.py` cruza 7 versões do sinal com 4 stops (28 combinações), cada uma com as cinco saídas, o controle e o protocolo de sempre. A regra de hoje com o stop de hoje reproduz a suíte (404 trades, +0,31 R em 2016–2026).

**Stop** (sinal de hoje, saída pela MME 9, em alta; a mesma combinação seria a escolhida em 1995–2015 nos três primeiros):

| Stop | 1995–2015 | 2016–2026 [piso 95%] | Contra o controle | Acerto | Distância do stop | Dura |
|---|---|---|---|---|---|---|
| mínima do candle (hoje) | +0,21 R | +0,31 R [+0,09] | +0,25 R | 39% | 7,2% | 10 pregões |
| meio do candle | +0,30 R | +0,47 R [+0,12] | +0,40 R | 32% | 3,8% | 7 pregões |
| 1 ATR abaixo da entrada | +0,26 R | +0,38 R [+0,04] | +0,30 R | 31% | 3,6% | 7 pregões |
| 0,5 ATR abaixo da entrada | +0,10 R | −0,10 R | −0,17 R | 17% | 2,0% | 3 pregões |

O stop no meio do candle é melhor nos dois períodos, corta a distância pela metade e é o único cuja vantagem sobre o controle tem intervalo de 95% acima de zero (+0,06 R). O de 1 ATR conta a mesma história; o de 0,5 ATR é apertado demais e vira prejuízo. O acerto cai de 39% para 32%: perde-se mais vezes, com perda menor.

**Mais sinais** (melhor combinação de cada versão, em 2016–2026):

| Versão | Trades por ano | Resultado | Contra o controle | Nível |
|---|---|---|---|---|
| de hoje, stop no meio | 38 | +0,47 R | +0,40 R | firme |
| corpo ≥ 1,0 ATR, stop no meio | 51 | +0,30 R | +0,22 R | firme |
| nível de 2 toques, stop no meio | 66 | +0,24 R | +0,19 R | firme |
| sem exigir nível, alvo 3R | 218 | +0,15 R | +0,09 R | firme |
| sem nível e sem volume, alvo 3R | 308 | +0,16 R | +0,05 R | firme |
| acima da máxima de 20, alvo 3R | 162 | +0,17 R | +0,05 R | firme |

Afrouxar o sinal dá mais trades e menos vantagem em cada um, na mesma proporção: o nível de 3 toques e o corpo de 1,2 ATR são o que separa o Força do mercado. Nenhuma das 28 combinações passa no critério rígido (Bonferroni), nem a regra de hoje: são 400 trades em dez anos, pouco para esse rigor. A leitura que fica é de direção, coerente nos dois períodos: **stop mais curto (meio do candle) melhora; sinal mais frouxo dilui.**

### Padrões de estrutura com entrada clara (11/11/2026)

Pedido do usuário: modelos de padrão com definição fechada e entrada clara, testados. `scripts/estudo_estrutura.py` escreve dez modelos como regra mecânica (as ideias vêm dos projetos abertos pesquisados; nenhum código foi copiado) e roda cada um com o stop próprio e com 1 ATR abaixo da entrada: 20 combinações pelo protocolo da suíte. As definições completas estão no cabeçalho do script.

Melhor combinação de cada modelo com o stop próprio, em 2016–2026:

| Modelo | Escolhida | 1995–2015 | 2016–2026 [piso 95%] | Contra o controle | Trades/ano | Stop | Dura | Nível |
|---|---|---|---|---|---|---|---|---|
| Contração de volatilidade | alvo 3R, todos | +0,44 R | +0,34 R [+0,06] | +0,19 R | 27 | 6,1% | 21 | firme |
| Rompimento da máxima de 20 | alvo 3R, em alta | +0,24 R | +0,21 R [+0,08] | +0,04 R | 521 | 6,6% | 21 | firme |
| Rompimento da máxima de 55 | alvo 3R, em alta | +0,23 R | +0,19 R [+0,06] | +0,07 R | 424 | 6,4% | 20 | firme |
| Rompimento de resistência (3+ toques, volume) | MME 9, em alta | +0,15 R | +0,17 R [−0,01] | +0,12 R | 121 | 5,6% | 9 | fraco |
| Gap com volume | MME 9, em alta | +0,70 R | +0,18 R [−0,02] | +0,07 R | 94 | 5,1% | 8 | fraco |
| Gap de valor justo | alvo 3R, em alta | +0,25 R | +0,12 R [−0,03] | +0,04 R | 129 | 5,9% | 17 | fraco |
| Quebra de estrutura | alvo 3R, em alta | +0,20 R | +0,11 R [−0,03] | +0,03 R | 121 | 11,0% | 36 | fraco |
| Bandeira | MME 9, contra | +0,25 R | +0,03 R | +0,06 R | 24 | 6,7% | 8 | fraco |
| Fundo duplo | alvo 3R, em alta | +0,27 R | +0,26 R [+0,08] | 0,00 R | 63 | 9,1% | 34 | falhou |
| NR7 | MME 9, em alta | −0,08 R | −0,12 R | −0,26 R | 1.522 | 2,3% | 3 | falhou |

Leitura:

- **Contração de volatilidade** é o único modelo novo que ganha do controle com folga nos dois períodos (+0,27 R e +0,19 R). São poucos trades (289 na conferência) e o intervalo da vantagem sobre o controle ainda cruza o zero.
- **Rompimento da máxima de 20** é o único das 120 conferências dos três estudos que passa no critério rígido pelo resultado bruto, mas ganha do controle por só 0,04 R: o lucro é estar comprado em papel em alta com alvo longo, não o rompimento. O fundo duplo é o mesmo caso, mais claro: +0,26 R, igual ao controle.
- **Rompimento de resistência de 3+ toques com volume** é o mais consistente entre os frequentes: positivo e acima do controle nos dois períodos, 121 trades por ano, 9 pregões. É o nível da casa sem exigir o candle de Força.
- **O stop de 1 ATR piora quase todos** (ao contrário do Força): nesses padrões o stop natural é parte do padrão.

Este estudo não mexeu no app; o que entrou depois está na seção seguinte.

### Contração e rompimento viram setups (11/11/2026)

O usuário abriu o app, viu os mesmos setups de antes e cobrou: os estudos tinham ficado só no papel. Entraram os dois modelos que passaram, como setups de verdade (cartão, alerta, acompanhamento, nota do backtest):

- **Contração de volatilidade** (`contracao`): três blocos seguidos de 10 pregões, cada um com amplitude menor que 70% da do anterior, e o último a até 1 ATR da máxima de 60 pregões. Compra 1 centavo acima da **máxima do último bloco** (é o primeiro setup cujo gatilho não é a máxima do dia: a coluna `maxima` da linha guarda a do bloco, e o alerta e a confirmação saem dela como sempre); stop 1 centavo abaixo da mínima do bloco. Padrão: alerta ligado, alvo de 3R.
- **Rompimento de resistência** (`rompimento`): o dia fecha acima de uma resistência de 3+ toques (o motor de níveis), com volume de 1,5× ou mais. Compra acima da máxima do dia, stop abaixo da mínima. Padrão: alerta ligado, saída pela MME 9.

Os padrões de candle das bibliotecas não entraram: todos falharam na varredura, e pela regra da casa entrariam só para encher a lista de cartões vermelhos.

Rodada da suíte com os dois (COTAHIST até 09/10/2026, 1,11 milhão de trades), que reproduz o estudo:

| Setup | Escolhida | 1995–2015 | 2016–2026 [IC 95%] | Contra o controle | Pior fase (30 anos) | |
|---|---|---|---|---|---|---|
| Contração | alvo 3R, todos | +0,44 R | +0,34 R [+0,05; +0,61] | +0,32 R | 9 perdas seguidas, −12 R | firme |
| Força | MME 9, em alta | +0,21 R | +0,31 R [+0,09; +0,54] | +0,30 R | 8 perdas seguidas, −21 R | firme |
| Rompimento | MME 9, em alta | +0,15 R | +0,17 R [−0,02; +0,36] | +0,06 R | 12 perdas seguidas, −48 R | fraco |

O Suporte caiu de fraco para falhou nesta rodada sem a regra dele mudar: o resultado é o mesmo (+0,03 R), mas o controle sorteado mudou de −0,02 R para +0,11 R porque dois setups novos entraram antes dele na ordem do sorteio. Estava na fronteira; o alerta padrão dele ficou como estava, à espera de decisão do usuário.

**Envio da rodada pelo GitHub** (`backtest-enviar.yml`, `scanner/backtest/pacote.py`). O endereço do banco de produção vive só nos segredos do GitHub, e pedir para o usuário achar a credencial no painel travou o envio da pior fase. Agora `scripts/backtest_setups.py empacotar` grava a rodada num JSON compactado, sem os trades; o arquivo sobe cifrado (chave no segredo `BACKTEST_CHAVE`) numa release, e o workflow abre, aplica as migrations e grava. Migration 0021: só a lista de categorias.

## 15. Cripto (16/11/2026)

Pedido do usuário: uma aba de criptomoedas com os mesmos setups. Decisões dele, em três rodadas de perguntas:

| Pergunta | Escolha |
|---|---|
| Quais moedas | As 50 maiores por valor de mercado com par em dólar (USDT), sem stablecoin |
| Direção | Só compra, como na B3 |
| Tempo gráfico | Diário (o candle fecha às 21h de Brasília) |
| Semáforo | Backtest próprio de cripto |
| Moeda | Dólar (USDT) |
| Lugar | Aba Cripto própria; ações e criptos não se misturam |
| Na primeira entrega | Aviso no Telegram, volume anômalo, diário de trades e página de backtest |

### Como foi feito

O pipeline inteiro roda uma segunda vez, com `SCANNER_MERCADO=cripto`, num schema próprio do mesmo banco (`cripto_scanner`). Misturar moedas nas tabelas das ações faria o universo, o z-score, a média do mercado e o sorteio do controle enxergarem os dois mercados; com schema separado, carga, métricas, setups, níveis, backtest e resumo são o mesmo código, sem nenhum `WHERE mercado = ...`.

O que muda fica em `src/scanner/mercado.py`:

- **Dado**: candles diários da Binance pela API pública (`scanner/cripto/binance.py`). O candle é o dia UTC; o do dia em andamento nunca é gravado.
- **Universo**: ranking da CoinGecko cruzado com os pares que a Binance negocia (`scanner/cripto/universo.py`). Moeda que sai das 50 continua sendo carregada enquanto tiver barra, para um setup aberto conseguir encerrar.
- **Passo de preço**: na B3 é 1 centavo. Em cripto é a quinta casa significativa do preço (1 dólar para o BTC a 65 mil, 0,00001 para uma moeda a 0,52): de 1 a 10 pontos-base. É o "1 centavo acima da máxima" das regras.
- **Custo do backtest**: 0,15% por lado (0,10% de taxa da Binance + 0,05% de derrapagem), contra 0,08% na B3.
- **Calendário**: todo dia é dia de negociação.
- **Preço no banco**: as colunas passaram de 4 para 10 casas decimais (migration 0022).

Roda todo dia pelo workflow `cripto.yml`, disparado pelo cron externo às 21:10 e às 00:10 de Brasília (`.github/cron-externo.yml`); ele aplica as migrations no schema de cripto, carrega, calcula e manda o resumo.

### O backtest de cripto: todos os setups falharam

`scripts/cripto_historico.py` baixou o diário de 684 moedas (todos os pares contra USDT que a Binance já listou, inclusive os deslistados que a API ainda conhece; stablecoins e ativos embrulhados de fora), de 17/08/2017 a 15/11/2026. A suíte é a mesma das ações, sem mudar regra nem corte: 189 mil trades em 413 moedas que foram líquidas em algum dia, escolhendo a saída de cada setup em 2017–2021 e conferindo em 2022–2026.

| Setup | Escolhida | 2017–2021 | 2022–2026 [IC 95%] | Contra o controle | Trades | |
|---|---|---|---|---|---|---|
| 123 | MME 9, em alta | +0,28 R | +0,01 R [−0,22; +0,35] | −0,10 R | 3.447 | falhou |
| PFR | MME 9, em alta | +0,47 R | −0,01 R [−0,26; +0,36] | −0,07 R | 1.803 | falhou |
| MMA 20 | MME 9, em alta | +0,75 R | −0,02 R [−0,29; +0,37] | −0,05 R | 1.296 | falhou |
| Rompimento | alvo 3R, em alta | +0,56 R | −0,05 R [−0,45; +0,34] | −0,14 R | 181 | falhou |
| 9.1 | MME 9, todos | +0,20 R | −0,05 R [−0,28; +0,27] | −0,23 R | 249 | falhou |
| Força | alvo 1R, todos | +0,23 R | −0,10 R [−0,30; +0,06] | −0,09 R | 111 | falhou |
| PFR no suporte | MME 9, em alta | +0,37 R | −0,11 R [−0,27; +0,11] | −0,09 R | 572 | falhou |
| Na média | MME 9, em alta | +0,40 R | −0,12 R [−0,41; +0,22] | −0,27 R | 100 | falhou |
| 9.4 | MME 9, em alta | +0,47 R | −0,21 R [−0,50; +0,03] | −0,15 R | 144 | falhou |
| Pullback | MME 9, em alta | +0,41 R | −0,22 R [−0,47; +0,02] | −0,28 R | 511 | falhou |
| 123 no suporte | alvo 3R, em alta | +0,26 R | −0,27 R [−0,52; −0,02] | −0,26 R | 806 | falhou |
| 9.3 | MME 9, em alta | +1,19 R | −0,28 R [−0,46; −0,09] | −0,41 R | 422 | falhou |
| 9.2 | MME 9, todos | +0,18 R | −0,72 R [−0,84; −0,55] | −1,24 R | 124 | falhou |

Contração e reversão no suporte não chegaram a 100 trades em 2017–2021, e ficam sem nota.

Leitura:

- **Nenhum setup de compra das ações ganha da moeda sorteada em cripto.** Todos foram bem em 2017–2021 (o ciclo de alta) e nenhum se manteve em 2022–2026.
- **Não é efeito de moeda pequena.** Refazendo a conta só com as 50 moedas de maior volume em cada dia (137 mil dos 189 mil trades), o quadro é o mesmo; dois setups passam de falhou para fraco (MMA 20, +0,07 R; Na média, +0,05 R), nenhum fica firme.
- **O setup perde do controle em todos os anos, não só nos ruins.** Com a saída pela MME 9, a média anual do setup ficou abaixo da do controle de 2018 a 2026 sem exceção (em 2024: +0,06 R contra +0,20 R). A diferença entre os dois é a entrada: o setup compra acima da máxima do dia, o controle compra na abertura seguinte. No diário de cripto, comprar o rompimento da máxima custa caro com consistência.
- Esse último ponto é a pista para um estudo próprio de cripto (inclusive do lado da venda, que o usuário mencionou): se entrar no rompimento perde sempre, o padrão que funciona ali pode ser o contrário. Não foi estudado; é hipótese.

Pela regra da casa, setup que falha continua visível, com aviso: a aba Cripto mostra todas as entradas com o semáforo vermelho, e nenhum setup de cripto tem alerta ligado.

### Site

`/cripto` (entradas de hoje, volume fora do normal, em andamento, encerrados e o capital em dólar), `/cripto/[moeda]` (gráfico diário com níveis e setups) e `/cripto/backtest`. As consultas são as mesmas das ações: a página roda a leitura dentro de `noMercado("cripto", ...)` e a conexão troca o schema no SQL. O lote é em fração de moeda (`calcularLoteFracionado`), com mínimo de US$ 5 de posição.

### Diário de trades em cripto (17/11/2026)

Decisões do usuário: o mesmo diário das ações, com filtro Tudo / Ações / Cripto; valores em dólar; quantidade fracionada; taxa da Binance de 0,1% por lado, saindo da moeda comprada (o padrão da Binance sem BNB); botão "Entrei" nos cartões de cripto, inclusive no sinal de compra do RSI do estudo, que vira o setup "RSI (estudo)".

- **Banco** (migration 0027, nos dois schemas): quantidade e posição passam a `numeric(28, 10)`, preço e stop a dez casas, preço médio a dez casas; `trades.sinal_estudo_id` liga o trade ao sinal do estudo. Na B3 nada muda no valor.
- **Contas** (`regrasDoDiario` em `web/src/lib/mercado.ts`): compra de q a p custa q × p e deixa q × 0,999 na posição; o preço médio é o custo dividido pelas moedas que ficaram. Venda de q a p realiza q × (p × 0,999 − PM). Na B3, taxa zero, ação inteira e centavo: as contas de antes. O risco do R é o planejado, sem taxa: um trade que bate no stop fecha um pouco abaixo de −1 R, que é o custo de verdade.
- **Calendário**: todo dia é dia; a data é o dia UTC do candle (depois das 21h de Brasília já é o dia seguinte).
- **Site**: os ids repetem entre os schemas, então rota e link levam `?mercado=cripto`. O preço de agora de um trade aberto vem da Binance (`/api/cotacao/MOEDA?mercado=cripto`). A venda tem o botão "tudo", para fechar o trade quando a corretora deixa um resto pequeno demais para vender.
- **Marcação noturna e Telegram**: a mesma etapa do `scanner daily` marca os trades de cripto no workflow `cripto`; o bloco "Seus trades" do resumo de cripto fala em moeda e dólar.
- Fica de fora: venda a descoberto (a compressão na venda do estudo não tem "Entrei") e o cartão "Seu trade" na ficha da moeda.

### O que ficou para a próxima fase

- **Alerta de preço durante o dia** (o "confirmou" na hora): a checagem de rompimento usa brapi e Yahoo, que não cotam cripto.
- **Ajustes por setup** (alerta e saída) na aba Cripto: hoje vale o `config-cripto.yaml`.
- **Página de backtest completa** (curva, ano a ano, lista de trades), como a das ações: a de cripto mostra o resumo por setup.
- **Estudo de padrões próprio de cripto**, compra e venda.

## 16. Valuation simples (16/11/2026)

Pedido do usuário: "métodos básicos de valuation no app, nada muito complexo e que dê para automatizar para todas as empresas listadas". Decisões dele, por perguntas:

| Pergunta | Escolha |
|---|---|
| Métodos | Graham, Bazin e fluxo de caixa simples (DCF) |
| Onde aparece | Na ficha do papel e numa lista geral |
| Como mostra | Preço justo, diferença para o preço de hoje e semáforo por método |
| Premissas do DCF | Padrão automático, com ajuste na tela |

### As três contas

Todas saem do balanço da CVM que a aba Fundamentos já usa e do fechamento do pregão (`web/src/lib/valuation.ts`).

- **Graham**: raiz de 22,5 × lucro por ação × valor patrimonial por ação. Lucro de 12 meses e patrimônio dos controladores, do último trimestre publicado. Não se aplica com prejuízo ou patrimônio negativo.
- **Bazin**: provento médio por ação dos últimos 3 anos dividido por 6%. Janelas de 12 meses pela data com; ano sem provento conta como zero.
- **Fluxo de caixa**: o lucro por ação cresce por 5 anos, depois 4% ao ano para sempre, e tudo é trazido a valor de hoje. Padrão: crescimento = o do lucro de 12 meses da própria empresa nos últimos 2 anos, limitado entre 0% e 15% (4% sem histórico); desconto = juro do Tesouro prefixado de 10 anos (ou a Selic) + 5 pontos. Na ficha, crescimento e desconto têm controle deslizante e o número recalcula na hora. É a versão mais simples do método: usa o lucro como se fosse o caixa do acionista, sem separar investimento, capital de giro nem dívida.

O semáforo de cada método: verde com o preço mais de 10% abaixo do resultado, vermelho mais de 10% acima, amarelo no meio. O resumo conta quantos métodos concordam ("2 de 3 métodos: abaixo do preço justo"), sem tirar média entre eles.

### O que precisou ser consertado no caminho

**Proventos não eram ajustados por desdobramento.** A B3 informa o provento pelo valor por ação da época, e é assim que ele fica no banco. Depois de um desdobramento de 1 para 3, um dividendo antigo de R$ 2,00 era somado inteiro contra um preço três vezes menor. Apareceu na primeira versão da lista: Direcional com preço teto de Bazin de R$ 40,83 para um preço de R$ 10,50. O mesmo erro já estava no **dividend yield de 12 meses** da ficha, desde a estreia da aba.

A correção (`fatorDoSalto` e `fatorAteODia`, em `web/src/lib/fundamentos.ts`): os desdobramentos são reconhecidos pelo salto de abertura nas barras, com a mesma regra do motor de suportes em Python (`gatilhos/matrizes.py`), e cada provento é levado para a escala das ações do dia que a ficha está mostrando. Com isso o Bazin da Direcional foi para R$ 19,35.

Limite conhecido: a detecção só alcança os 400 pregões de barras do banco, e o Bazin olha 3 anos. Desdobramento mais antigo que as barras não é visto. Para esse caso (e para pagamento extraordinário), o Bazin não é calculado quando o provento médio passa de 30% do preço de hoje; a tela diz "fora de escala".

### Onde aparece

- **Ficha**, aba Fundamentos, bloco "Preço justo": os três resultados, o resumo, a conta de cada método com os números usados e os dois controles do fluxo de caixa.
- **`/valuation`**: todas as empresas com balanço e preço no último pregão, ordenável por método, com busca e filtro de liquidez. Cinco consultas no total (`valuation-dados.ts`), e cada empresa passa pela mesma `indicadoresNaData` da ficha, com as seis camadas de conferência da contagem de ações: o número da lista é o da ficha.

Só para quem está logado, como os setups.

### O que estas contas não são

Não consideram setor, dívida, ciclo, qualidade do lucro nem nada que não esteja nos três ou quatro números de entrada. Banco e seguradora passam pelo Graham e pelo fluxo de caixa como qualquer empresa. Empresa cíclica no pico do lucro parece barata nos três. Servem para olhar todas as empresas com a mesma régua e decidir onde vale abrir o balanço, não para dizer quanto uma empresa vale.

### Fora desta fase

Múltiplos contra a própria história (P/L e EV/EBITDA médios de 5 anos), que foi oferecido e não escolhido; valuation em data passada na lista geral (a ficha já calcula para o pregão que está aberta); ajuste por bonificação pequena (10%, 20%), que a regra do salto não distingue de um gap.


## 17. Tendência por médias móveis (17/11/2026)

Pedido do usuário: escolher, no scanner e na aba Cripto, os ativos em tendência de alta, lateral ou baixa pela inclinação das médias móveis, e procurar o setup no gráfico deles. Nada de aba nova; as médias não aparecem no gráfico; o usuário escolhe quais combinar.

### Como funciona

- **Pipeline** (`scanner/tendencia.py`, etapa 7 de 9 do `scanner daily`, nos dois mercados): para o último pregão, cada média (MME e MMA de 9, 20, 50, 80 e 200) vale +1 (subindo), −1 (caindo) ou 0 (sem histórico). "Subindo" é a média de hoje acima da de k pregões atrás: 9 contra 1 (a virada do Larry Williams), 20 contra 5, 50 contra 10, 80 e 200 contra 20 — as convenções que o projeto já usava. Preço ajustado por desdobramento (`matrizes.montar`). Tabela `tendencias` (migration 0028), uma linha por ativo, trocada a cada noite, com a liquidez de hoje pela regra do backtest (mediana de 60 pregões, com 48 negociados, acima do piso do mercado).
- **Site** (`web/src/lib/tendencia.ts`, `PainelDeTendencia`): alta = todas as médias marcadas subindo; baixa = todas caindo; lateral = discordam; sem histórico em alguma = fica de fora. Começa em MME 9 + 80; a escolha fica no navegador, por mercado.
- É descrição da direção das médias no último fechamento, não previsão. Não alimenta alerta, setup, semáforo nem backtest.

### O estudo que escolheu o ponto de partida

Sobre os trades da saída escolhida de cada setup (176 mil sinais da B3 de 1995 a 2026; 42 mil de cripto de 2017 a 2026), as 62 combinações de médias (31 de cada tipo). Ganho = R médio do setup com a combinação em alta menos o R fora dela, cada setup pesando igual. Escolha em 1995–2015 (cripto 2017–2021), conferência em 2016–2026 (cripto 2022–2026).

| Médias subindo | B3 escolha → conferência | Cripto escolha → conferência |
|---|---|---|
| MME 9 | +0,19 → +0,20 R | +0,52 → +0,08 R |
| MME 9 + 20 | +0,16 → +0,13 R | +0,50 → +0,01 R |
| MME 9 + 80 | +0,13 → +0,10 R | +0,52 → +0,03 R |
| MME 9 + 80 + 200 | +0,03 → +0,03 R | +0,56 → +0,05 R |
| MME 200 | −0,08 → −0,06 R | +0,25 → +0,01 R |
| Preço acima da MMA 200, subindo (a etiqueta "em alta" dos setups) | 0,00 → +0,02 R | +0,44 → −0,13 R |

Leitura: a direção curta (MME 9) é a que separa, nos dois mercados e nos dois períodos; as médias longas sozinhas não ajudam, e em cripto só pareciam ajudar no ciclo de alta de 2017–2021. Com 62 combinações testadas, a chance de uma "melhor" ser sorte é alta: por isso o ponto de partida é uma combinação simples que se confirmou, e a escolha final é do usuário. A etiqueta de tendência dos setups e o semáforo continuam na definição antiga (MMA 200); trocá-los pede refazer a suíte.
