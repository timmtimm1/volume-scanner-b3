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
