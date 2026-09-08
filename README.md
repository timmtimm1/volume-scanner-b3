# volume-scanner-b3

Detector de volume financeiro anômalo na B3.

Todo pregão, o scanner calcula o z-score do volume de cada papel contra o próprio
histórico recente — janelas de 30, 45 e 60 pregões — e avisa por Telegram todo papel
que cruzar o limiar configurado. A interpretação do evento é manual, feita no gráfico.

O sistema **detecta e apresenta**. Não julga, não filtra por mérito, não prevê.

## O que torna a leitura possível: o ticket médio

A fonte é o COTAHIST da B3, que traz `TOTNEG` (número de negócios) e `VOLTOT`
(volume financeiro) na mesma linha. Isso permite calcular o **ticket médio**
(`VOLTOT / TOTNEG`) — e nenhuma API gratuita entrega esses dois campos juntos.

É a informação mais útil do conjunto para a leitura manual:

- ticket **alto** com volume explodindo → bloco institucional
- ticket **baixo** com `TOTNEG` explodindo → correria de varejo

Dois eventos com o mesmo z-score e ticket médio oposto são eventos diferentes.

## A regra mecânica

Média e desvio da janela usam **apenas os N pregões anteriores** ao dia avaliado:
`shift(1)` antes do `rolling(N)`.

Se o dia do pico entra na janela que o mede, ele infla o próprio desvio padrão. O
z-score máximo possível de uma amostra de N pontos é `(N−1)/√N`:

| Janela | z máximo | 6σ dispara? |
|---|---|---|
| 30 | 5,29 | **Nunca** |
| 45 | 6,56 | No limite |
| 60 | 7,62 | Sim |

Não é preferência de método, é aritmética.

## Métricas

Por janela, com baseline deslocado:

- `z_log` — z-score sobre `log(VOLTOT)`. **Primária**, porque volume é lognormal e
  z-score sobre valor bruto torna "6σ" incomparável entre PETR4 e uma small cap.
- `z_raw` — sobre o volume bruto, persistido como referência.
- `z_robust` — `(x − mediana) / (1,4826 × MAD)` sobre o log, imune a spike anterior
  contaminando o baseline.
- `rvol` — volume dividido pela mediana da janela: "negociou 14× o normal".

## Stack

| Componente | Onde | Custo |
|---|---|---|
| Banco | Neon (Postgres serverless) | grátis |
| Ingestão + scan diário | GitHub Actions (cron, dias úteis) | grátis |
| Alerta | Telegram Bot | grátis |
| Site | Next.js estático na Vercel | grátis |
| Desenvolvimento | Docker local | grátis |

Python 3.11+, pandas/numpy, SQLAlchemy 2.x, Alembic, Pydantic Settings, Typer.

## Desenvolvimento

```bash
uv sync                       # ambiente e dependências
cp .env.example .env          # e preencha
docker compose up -d          # Postgres local
uv run alembic upgrade head   # schema
uv run pytest                 # testes
uv run ruff check . && uv run mypy src/
```

## Comandos

```bash
scanner ingest backfill --start 2024-01-01
scanner ingest daily
scanner metrics compute --mode incremental
scanner scan --date today --dry-run
scanner scan --date today
scanner report ticker PETR4 --window 60
```

## Estado

Em construção, fase por fase, segundo [`docs/PLANO.md`](docs/PLANO.md).

| Fase | Escopo | Estado |
|---|---|---|
| F0 | Fundação: estrutura, lint, tipos, testes, Docker, Alembic, CLI | ✅ |
| F1 | Calendário B3 + universo com filtro de liquidez | ✅ |
| F2 | Parser e carga COTAHIST | ✅ |
| F3 | Z-scores + features de contexto | ✅ |
| F4 | Alertas + Telegram | ⬜ |
| F5 | Deploy: Neon, Actions, secrets | ⬜ |
| F6 | Interface: scanner, ficha do papel, histórico | ⬜ |
| F7 | PWA | ⬜ |

## Calendário da B3

A B3 só para em **feriado nacional**. Desde 2022 ela negocia normalmente nos
feriados estaduais e municipais de São Paulo — **25 de janeiro e 9 de julho são
pregão**. Além dos nacionais, ela fecha em **24 e 31 de dezembro** por conta do
expediente interno dos bancos, e o 20 de novembro entrou como feriado nacional
**a partir de 2024** (Lei 14.759/2023).

Quarta-feira de Cinzas **é pregão**, com abertura às 13h — o horário reduzido não
suprime a barra diária, que é o que este projeto consome.

As datas móveis (carnaval, Sexta-feira Santa, Corpus Christi) são derivadas da
Páscoa por algoritmo, nunca tabeladas: tabela de data móvel envelhece em silêncio.

```bash
scanner calendar holidays --year 2026
scanner calendar sessions --start 2026-01-01 --end 2026-01-31
scanner universe show --date today
```

## A regra mecânica, verificada no dado real

Com 671 pregões de 2024 a 2026 carregados, a janela de 30 dias produz z-scores
**acima do teto que existiria sem o `shift(1)`**:

| Janela | Teto `(N−1)/√N` | Máx. z_log obtido | Linhas acima do teto |
|---|---|---|---|
| 30 | 5,29 | **9,69** | 201 |
| 45 | 6,56 | 9,75 | 31 |
| 60 | 7,62 | 10,12 | 5 |

Sem o baseline deslocado, a janela de 30 travaria em 5,29 e nenhum dos 96 eventos
de 6σ que ela encontra existiria.

## Duas coisas que o layout da B3 esconde

**`FATCOT` (fator de cotação, posições 211–217)** não está na tabela da seção 2 do
plano, mas é obrigatório: em 0,5% das linhas o preço é cotado por lote de 100, 1.000
ou 1.000.000 de ações. Sem dividir por ele, `close × volume_shares` erra por 1000× e
o gráfico mostra um preço mil vezes maior que o real.

**`PREMED` é truncado a 2 casas, nunca arredondado.** Verificado em 100,0000% das
linhas de um arquivo real: `PREMED × QUATOT / FATCOT ≤ VOLTOT`, sempre. A consequência
é que a validação `VOLTOT ≈ PREMED × QUATOT` com tolerância de 1% é **inalcançável**
para papel abaixo de R$ 1,00 — o erro de quantização sozinho já passa disso. Acima de
R$ 1,00 não há uma única falha em 53 mil linhas.

Por isso o `price_check_mode` do `config.yaml` tem dois modos:

| Modo | Regra | Falha em 2026 |
|---|---|---|
| `relative` | desvio relativo ≤ `price_check_tolerance` (regra literal do plano) | 1,59% |
| `truncation` | `VOLTOT` dentro de `[PREMED, PREMED+0,01) × QUATOT / FATCOT` | 0,07% |

`truncation` é o padrão. Não é uma tolerância afrouxada: é a aritmética exata de um
campo truncado, e continua estreita o bastante para pegar desalinhamento real — em
papel de R$ 20 a folga é de 0,05%.

## Segredos

Banco e Telegram vêm **só de variável de ambiente** (`SCANNER_*`), nunca do repo.
Veja `.env.example` — os valores lá são placeholders, não credenciais.
