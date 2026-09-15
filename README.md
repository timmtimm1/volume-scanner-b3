# volume-scanner-b3

[![CI](https://github.com/timmtimm1/volume-scanner-b3/actions/workflows/ci.yml/badge.svg)](https://github.com/timmtimm1/volume-scanner-b3/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](pyproject.toml)
[![Site em produção](https://img.shields.io/badge/site-produção-success)](https://volume-scanner-b3-a11v.vercel.app)

Detector de volume financeiro anômalo na B3.

Todo pregão, o scanner calcula o z-score do volume de cada papel contra o próprio
histórico recente — janelas de 30, 45 e 60 pregões — e avisa por Telegram todo papel
que cruzar o limiar configurado. A interpretação do evento é manual, feita no gráfico.

O sistema **detecta e apresenta**.

## Índice

- [O que torna a leitura possível: o ticket médio](#o-que-torna-a-leitura-possível-o-ticket-médio)
- [A regra mecânica](#a-regra-mecânica)
- [Métricas](#métricas)
- [O alerta](#o-alerta)
- [Stack](#stack)
- [Requisitos](#requisitos)
- [Desenvolvimento](#desenvolvimento)
- [Comandos](#comandos)
- [Estado](#estado)
- [Além do plano](#além-do-plano)
- [A interface](#a-interface)
- [Calendário da B3](#calendário-da-b3)
- [A regra mecânica, verificada no dado real](#a-regra-mecânica-verificada-no-dado-real)
- [Duas coisas que o layout da B3 esconde](#duas-coisas-que-o-layout-da-b3-esconde)
- [Banco de dados](#banco-de-dados)
- [Deploy](#deploy)
- [Dificuldades conhecidas](#dificuldades-conhecidas)
- [Desempenho](#desempenho)
- [Segredos](#segredos)

## Como funciona, ponta a ponta

<img src="docs/diagrams/pipeline.svg" alt="Fluxograma: o arquivo diário da B3 é carregado no banco, as métricas de z-score são calculadas, o scan compara com o limiar de 6σ, e um evento dispara notificação no Telegram e atualização do site até a mensagem chegar no celular do usuário." width="100%">

Arquivo da B3 → carga no Postgres → cálculo de métricas → o scan decide se
algum papel cruzou 6σ → se sim, sai notificação no Telegram **e** o site
reconstrói em paralelo, até a mensagem chegar no celular. `SCAN` é o único
ponto de decisão do sistema — tudo antes dele é ingestão, tudo depois é
distribuição do mesmo resultado por dois canais.

Os tempos no diagrama são desde o disparo do job, medidos numa execução real de
produção (15/09/2026) — detalhado na seção [Desempenho](#desempenho). A mensagem
chega no celular bem antes do site: o rebuild da Vercel não bloqueia o alerta.

## O que torna a leitura possível: o ticket médio

A fonte é o COTAHIST da B3, que traz `TOTNEG` (número de negócios) e `VOLTOT`
(volume financeiro) na mesma linha. Isso permite calcular o **ticket médio**
(`VOLTOT / TOTNEG`)s.

É a informação mais útil do conjunto para a leitura manual:

- ticket **alto** com volume explodindo → bloco institucional
- ticket **baixo** com `TOTNEG` explodindo → correria de varejo

Dois eventos com o mesmo z-score e ticket médio oposto são eventos diferentes.

## A regra

Média e desvio da janela usam **apenas os N pregões anteriores** ao dia avaliado:
`shift(1)` antes do `rolling(N)`.

Se o dia do pico entra na janela que o mede, ele infla o próprio desvio padrão. O
z-score máximo possível de uma amostra de N pontos é `(N−1)/√N`:

| Janela | z máximo | 6σ dispara? |
|---|---|---|
| 30 | 5,29 | **Nunca** |
| 45 | 6,56 | No limite |
| 60 | 7,62 | Sim |


## Métricas

Por janela, com baseline deslocado:

- `z_log` — z-score sobre `log(VOLTOT)`. **Primária**, porque volume é lognormal e
  z-score sobre valor bruto torna "6σ" incomparável entre PETR4 e uma small cap.
- `z_raw` — sobre o volume bruto, persistido como referência.
- `z_robust` — `(x − mediana) / (1,4826 × MAD)` sobre o log, imune a spike anterior
  contaminando o baseline.
- `rvol` — volume dividido pela mediana da janela: "negociou 14× o normal".

## O alerta

Em dia de estresse de mercado isso produz dezenas de alertas de uma vez, porque a
correlação entre papéis dispara junto. É o comportamento pedido: o `z_excess` na
mensagem é o que permite descartar a enxurrada em segundos — se todo mundo está com
`mkt_vol_z` alto, foi o mercado, não os papéis. Abaixo um exemplo:

```
⚡ GGPS3 — volume 28,9× o normal

R$ 943,6 mi negociados
z_log: 30d 9,69 | 45d 9,08 | 60d 7,96
z liquido do mercado: 8,00

R$ 14,80 (-5,7%) | gap -3,7%
Fechou a 25% do range do dia
Faixa de 252d: 31%
20 pregoes anteriores: +10,4%
Ticket medio: R$ 63.553 (z 42,8)

→ abrir grafico
```
**Sem Telegram configurado, o alerta sai no terminal** — perder o evento em silêncio
seria pior do que não mandar pelo canal certo.

## Stack

| Componente | Onde | Custo |
|---|---|---|
| Banco | Neon (Postgres serverless) | grátis |
| Ingestão + scan diário | GitHub Actions (cron, dias úteis) | grátis |
| Alerta | Telegram Bot | grátis |
| Site | Next.js estático na Vercel | grátis |
| Desenvolvimento | Docker local | grátis |

Python 3.11+, pandas/numpy, SQLAlchemy 2.x, Alembic, Pydantic Settings, Typer.

## Requisitos

- **Python 3.11+**, gerenciado via [`uv`](https://docs.astral.sh/uv/)
- **Docker**, só para o Postgres local — a produção roda no GitHub Actions contra o Neon
- **Node.js 20+** e npm, só para a interface (pasta `web/`)

## Desenvolvimento

```bash
uv sync                       # ambiente e dependências
cp .env.example .env          # e preencha
docker compose up -d          # Postgres local
uv run alembic upgrade head   # schema
uv run pytest                 # testes
uv run ruff check . && uv run mypy src/
```

Isso cria o **schema**, vazio — scan, ficha do papel e histórico não têm o que
mostrar ainda. Para ter dado real da B3 no Postgres local:

```bash
uv run scanner ingest backfill --start 2024-01-01   # ~250 MB, alguns minutos
uv run scanner metrics compute --mode full          # z-score do histórico inteiro
```

São os mesmos dois comandos do passo 5 de [Banco no Neon](#1-banco-no-neon) —
aqui sem o prefixo `SCANNER_DATABASE_URL=`, porque o `.env` já aponta para o
Postgres local. `scanner db prune` (também documentado lá) é opcional em
desenvolvimento: corta para os últimos 400 pregões, o que a produção faz para
caber no plano gratuito do Neon, mas localmente não há esse limite.

- a suíte roda em ~20s contra o local, e em minutos contra o Neon;
- os testes criam um banco isolado `<db>_pytest` — que você não quer criando
  dentro do projeto de produção;
- o plano gratuito do Neon tem 100 CU-hours/mês, e rodar teste contra ele
  queima essas horas à toa.

A string do Neon fica nos **GitHub Secrets** e nas variáveis de ambiente da Vercel. No `.env`
ela fica comentada, para o caso de você precisar apontar para produção de
propósito.

**O Docker só é necessário para desenvolver.** O pipeline de produção roda no
GitHub Actions o Neon — se o seu PC estiver desligado, ele funciona igual.

## Comandos

Os comandos abaixo rodam o código e carregam os dados
(`.github/workflows/daily.yml`): carga, métricas, alerta, resumo e poda, na ordem certa,
lendo o banco uma vez só.

```bash
scanner daily --date today            # processa o pregão de hoje
scanner daily --date today --dry-run  # calcula e mostra, sem gravar nem notificar
```

Os passos separados continuam existindo — para carga histórica, depuração pontual ou
rodar só um pedaço:

```bash
scanner ingest backfill --start 2024-01-01
scanner ingest daily
scanner metrics compute --mode incremental
scanner scan --date today --dry-run
scanner scan --date today
scanner resumo --date today --dry-run
scanner report ticker PETR4 --window 60
scanner db status
```

Alertas de rompimento de preço:

```bash
scanner alerta add PETR4 --preco 38.50 --direcao acima
scanner alerta list
scanner alerta checar --dry-run
```

## Estado

As fases de [`docs/PLANO.md`](docs/PLANO.md) estão entregues. O que veio depois
está em "Além do plano", logo abaixo.

| Fase | Escopo | Estado |
|---|---|---|
| F0 | Fundação: estrutura, lint, tipos, testes, Docker, Alembic, CLI | ✅ |
| F1 | Calendário B3 + universo com filtro de liquidez | ✅ |
| F2 | Parser e carga COTAHIST | ✅ |
| F3 | Z-scores + features de contexto | ✅ |
| F4 | Alertas + Telegram | ✅ |
| F5 | Deploy: Neon, Actions, secrets | ✅ código / ⏳ medindo com o cron externo |
| F6 | Interface: scanner, ficha do papel, histórico | ✅ |
| F7 | PWA | ✅ |

O critério de aceite da F5 — *três execuções agendadas consecutivas bem-sucedidas* —
passou a ser medido pelo cron externo (seção "O job diário"), já que o agendador
nativo do GitHub foi abandonado.

## Além do plano

Pedidos feitos depois das fases, nenhum deles filtro, ranking ou previsão:

- **Resumo diário no Telegram.** Os 10 papéis que mais fugiram do próprio volume
  normal no pregão, tenham cruzado o limiar ou não. Sai uma vez por pregão.
- **Alertas de rompimento de preço.** Na ficha do papel, logado, você clica no
  gráfico e escolhe um nível. A cada 15 minutos durante o pregão o
  `rompimentos.yml` consulta a brapi e o Yahoo, fica com a cotação de hora mais
  nova e avisa no Telegram quando o preço toca o nível. Cotação que não é do
  pregão de hoje não dispara. É o único dado do sistema que não vem do COTAHIST.
- **Candle de hoje na ficha.** Depois que a página abre, o gráfico ganha o candle
  do pregão em andamento, vazado, com a hora e a fonte da cotação. Não entra em
  nenhum cálculo e some quando o COTAHIST do dia chega.
- **Login com GitHub**, restrito a uma conta, só para os alertas. O resto do site
  é público.

## A interface

```bash
cd web
npm install
npm run dev        # http://localhost:3000
```

As telas de dado — scanner, histórico, papéis e cada ficha — são **estáticas**.
As consultas rodam no build, o Actions dispara o rebuild depois do scan, e é o
que faz abrir instantâneo no 4G.

Só três rotas rodam no servidor: `/api/auth` (login), `/api/alertas` (exige
login) e `/api/cotacao` (o candle de hoje, com cache de 5 minutos por papel).
Quem abre a ficha pelo link do Telegram recebe a página pronta e o candle chega
depois.

O build lê o mesmo `.env` da raiz, via `dotenv` no `next.config.ts`. Uma cópia
dentro de `web/` seria uma segunda fonte de verdade para a mesma credencial.

**Ao vivo:** [volume-scanner-b3-a11v.vercel.app](https://volume-scanner-b3-a11v.vercel.app)

| Scanner — claro | Scanner — escuro |
|---|---|
| ![Scanner, tema claro](docs/screenshots/scanner-desktop-claro.png) | ![Scanner, tema escuro](docs/screenshots/scanner-desktop-escuro.png) |

| Ficha do papel — desktop | Scanner — celular |
|---|---|
| ![Ficha do papel no desktop](docs/screenshots/ficha-desktop-claro.png) | ![Scanner no celular](docs/screenshots/scanner-celular-claro.png) |

A ficha também funciona em 390px de largura — é o link que chega pelo alerta do Telegram:

<img src="docs/screenshots/ficha-celular-escuro.png" alt="Ficha do papel no celular, tema escuro" width="320">

### Deploy na Vercel

1. Novo projeto apontando para a pasta `web/`
2. Variáveis de ambiente, em **Settings → Environment Variables**:

| Nome | Conteúdo | Ambientes |
|---|---|---|
| `SCANNER_DATABASE_URL` | a connection string do Neon | Production e Preview (o build lê o banco) |
| `AUTH_SECRET` | segredo da sessão (`npx auth secret`) | Production |
| `AUTH_GITHUB_ID` / `AUTH_GITHUB_SECRET` | o OAuth App do GitHub | Production |
| `AUTH_GITHUB_LOGIN` | o login do GitHub que pode entrar | Production |
| `SCANNER_BRAPI_TOKEN` | opcional; sem ele o candle de hoje usa só o Yahoo | Production |

3. Copie o **Deploy Hook** e cadastre como secret `VERCEL_DEPLOY_HOOK` no GitHub —
   é o que faz o `daily.yml` reconstruir o site depois de cada pregão

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

## Banco de dados

Postgres, schema `volume_scanner` (isolado do `public`, para não colidir com outro
projeto no mesmo banco). Sem chaves estrangeiras entre as tabelas — a ligação é por
`(ticker, trade_date)`, não por relação declarada no banco.

```mermaid
erDiagram
    daily_bars {
        text ticker PK
        date trade_date PK
        numeric close
        numeric volume_financial
        bool trades_censored
    }
    volume_metrics {
        text ticker PK
        date trade_date PK
        smallint window_size PK
        numeric z_log
        numeric rvol
    }
    daily_features {
        text ticker PK
        date trade_date PK
        jsonb features
    }
    events {
        bigint id PK
        text ticker
        date trade_date
        numeric max_z_log
        jsonb features
        timestamptz notified_at
    }
    digest_sends {
        date trade_date PK
        timestamptz sent_at
    }
    price_alerts {
        bigint id PK
        text ticker
        date trade_date
        numeric preco
        text direcao
    }

    daily_bars ||--o{ volume_metrics : "ticker + trade_date"
    daily_bars ||--o{ daily_features : "ticker + trade_date"
    daily_bars ||--o{ events : "ticker + trade_date"
    daily_bars ||--o{ price_alerts : "originou"
```

| Tabela | Guarda |
|---|---|
| `daily_bars` | Uma linha por papel/pregão, vinda do COTAHIST |
| `volume_metrics` | Um z-score por papel/pregão/janela (30, 45, 60) |
| `daily_features` | Contexto do pregão (ticket médio, faixa de 252d etc.) — tenha virado evento ou não |
| `events` | Só o que cruzou o limiar. Dedupe por `(ticker, trade_date)` |
| `digest_sends` | Carimbo de que o resumo diário já saiu, para não reenviar |
| `price_alerts` | Alertas de rompimento de preço, criados na ficha do papel |

Migrations via Alembic, em `alembic/versions/` — nunca schema por SQL solto.
`scanner db status` mostra pregões, linhas e tamanho de cada tabela no banco atual.

## Deploy

O pipeline não pode depender do seu PC estar ligado. Tudo roda em serviço gratuito.

### 1. Banco no Neon

1. Crie conta em [neon.tech](https://neon.tech) e um projeto (região mais próxima).
2. Copie a connection string. Ela precisa de `?sslmode=require`.
3. Troque o driver para `psycopg`, que é o que este projeto usa:

```
postgresql+psycopg://USUARIO:SENHA@HOST.neon.tech/NOME?sslmode=require
```

4. Aplique o schema apontando para lá:

```bash
SCANNER_DATABASE_URL="postgresql+psycopg://..." uv run alembic upgrade head
```

5. Carregue o histórico (leva alguns minutos, ~250 MB de download):

```bash
SCANNER_DATABASE_URL="postgresql+psycopg://..." uv run scanner ingest backfill --start 2024-01-01
SCANNER_DATABASE_URL="postgresql+psycopg://..." uv run scanner metrics compute --mode full
SCANNER_DATABASE_URL="postgresql+psycopg://..." uv run scanner db prune
```

O `db prune` deixa os últimos 400 pregões, que é o que cabe folgado nos 0,5 GB
do plano gratuito.

### 2. Bot do Telegram

1. Fale com **@BotFather**, mande `/newbot` e siga. Guarde o token.
2. Mande qualquer mensagem para o seu bot.
3. Pegue o `chat_id` em `https://api.telegram.org/bot<TOKEN>/getUpdates` —
   é o campo `message.chat.id`.

### 3. Secrets no GitHub

Em **Settings → Secrets and variables → Actions**:

| Onde | Nome | Conteúdo |
|---|---|---|
| Secret | `SCANNER_DATABASE_URL` | a connection string do Neon |
| Secret | `SCANNER_TELEGRAM_BOT_TOKEN` | o token do BotFather |
| Secret | `SCANNER_TELEGRAM_CHAT_ID` | o `chat_id` |
| Secret | `VERCEL_DEPLOY_HOOK` | opcional, só a partir da F6 |
| Secret | `SCANNER_BRAPI_TOKEN` | opcional; token da brapi para os alertas de preço |
| Variable | `SCANNER_WEB_BASE_URL` | URL do site; não é segredo |
| Variable | `SCANNER_BRAPI_LOTE` | opcional; papéis por requisição na brapi (gratuito 1, Startup 10, Pro 20) |

### 4. O job diário

`.github/workflows/daily.yml` faz: migrations → carga do pregão → métricas →
scan → resumo → retenção → rebuild na Vercel.

Quem dispara é um cron externo ([cron-job.org](https://cron-job.org)), via
`workflow_dispatch`: o agendador nativo do GitHub, em repositório público
gratuito, entregou cerca de 11% dos horários. A agenda versionada fica em
`.github/cron-externo.yml`, e são dois disparos, ambos pedindo o pregão
encerrado mais recente no relógio de Brasília:

| Quando (Brasília) | Dias | O que acontece |
|---|---|---|
| **21:30** | seg a sex | Processa o pregão do dia. Se a B3 ainda não publicou, termina como **adiado**: sem aviso de falha e sem rebuild |
| **07:40** | ter a sáb | Reserva. Processa o pregão da véspera se a noite não conseguiu; se conseguiu, nada se repete |

Alerta, resumo e carga são idempotentes: rodar duas vezes o mesmo pregão não
manda mensagem duplicada.

Feriado da B3 não precisa de exceção: `scanner ingest daily` conhece o calendário
e sai sem erro quando não houve pregão.

Dá para disparar à mão em **Actions → daily → Run workflow**, inclusive apontando
um pregão específico — é assim que se testa antes de esperar o cron.

> **Por que dois horários.** A B3 publica o arquivo do dia com atraso variável:
> às 21:08 em 08/09/2026, mas em 11/09 às 21:59 ainda dava 404, e às 02:42 a B3
> respondeu 403. O download tenta de novo em 404, 403, 429 e 5xx, com espera
> entre as tentativas. Se mesmo assim não sair à noite, a manhã cobre.

## Dificuldades conhecidas

O sistema depende de dois relógios que este projeto não controla — o da B3 e o
do fornecedor de cotação — e isso explica decisões que, de outra forma,
pareceriam complexas demais para o problema.

- **O agendador nativo do GitHub Actions é melhor esforço, não garantia.** Em
  repositório público gratuito, o `schedule:` entregou cerca de 11% dos
  horários programados — por isso o disparo real é um cron externo
  (seção [O job diário](#4-o-job-diário)), e não o `schedule:` do Actions.
- **A B3 publica o arquivo do pregão com atraso variável**, às vezes horas, às
  vezes com 403/404 no meio do caminho — daí os dois horários de disparo
  (21:30 + 07:40) em vez de um único horário fixo.
- **Cotação de preço não é tempo real.** Isso vale só para os alertas de
  rompimento — a única parte do sistema que não vem do COTAHIST oficial; o
  scan de volume usa dado de fechamento, sem esse problema. A brapi gratuita
  atrasa cerca de 30 minutos, o Yahoo cerca de 15. `ProvedorMaisRecente`
  consulta os dois fornecedores e fica, por papel, com a cotação de hora mais
  nova — sem isso, a brapi, que vem primeiro na ordem de preferência, sempre
  venceria mesmo estando mais atrasada que o Yahoo.
- **Sem `SCANNER_BRAPI_TOKEN`, só o Yahoo responde.** O plano gratuito da
  brapi aceita 1 papel por requisição; sem o token, a brapi fica de fora da
  consulta e a leitura de preço passa a ter uma única fonte.
- **O rompimento só vê o preço do instante da checagem**, a cada 15 minutos
  durante o pregão — não a máxima nem a mínima do intervalo. Um preço que
  ultrapassa o nível e volta antes da próxima checagem não dispara alerta.

## Desempenho

O job diário inteiro leva menos de um minuto. A execução das 21:30 de 14/09/2026,
lida no log do Actions, antes da otimização abaixo:

| Etapa | Tempo | Desde o disparo |
|---|---|---|
| Fila, runner e dependências | ~11s | 11s |
| Migrations (conecta no Neon) | ~7s | 18s |
| `[1/6]` baixa o arquivo da B3 e grava as barras | ~8s | 26s |
| `[2/6]` lê o histórico e calcula z-scores e contexto | ~8s | 34s |
| `[3/6]` grava métricas e contexto | ~5,5s | 40s |
| `[4/6]` scan e **alerta no Telegram** | <1s | **~40s** |
| `[5/6]` resumo no Telegram | ~2s | ~43s |
| `[6/6]` poda do banco | ~3,5s | 46s |
| Aviso de rebuild para a Vercel | ~5s | ~51s |

A mensagem chega no celular por volta dos 40 segundos; poda e Vercel vêm depois
dela. O build do site na Vercel não está nessa conta e ainda não foi medido.

### O que foi otimizado no código

Medido contra o Postgres local, sem latência de rede, com os mesmos 400 pregões
que o Neon guarda (132 mil barras):

| Mudança | Antes | Depois | Ganho |
|---|---|---|---|
| `rolling_mad`: mediana só nas janelas completas | 2,5s | 0,6s | −76% (4,2×) |
| Contexto: um pivô da tabela em vez de nove | 0,65s | 0,11s | −83% (5,9×) |
| **Cálculo inteiro do contexto** | **5,7s** | **2,9s** | **−49% (1,9×)** |

A diferença entre a soma das duas primeiras linhas e o total: `rolling_mad` e o
pivô são a maior parte do cálculo, mas não são tudo — o resto (montar as
matrizes de log, `shift`, `rolling().mean()/.std()`, concatenar as três
janelas) não mudou e continua no mesmo tempo de antes.

O `rolling_mad` usava `np.nanmedian` em todas as janelas. Janela com pregão
faltando tem `NaN`, e isso leva o numpy a um caminho lento, de arrays mascarados
— para calcular valores que a regra de janela cheia descarta logo em seguida.

Nenhum número mudou. Métricas e contexto saem idênticos, na comparação exata,
às versões anteriores. Os testes mantêm as implementações antigas como
referência e exigem igualdade bit a bit.

No Actions, o `uv run` ganhou `--no-sync`: sem ele, cada execução baixava mypy,
ruff e pytest, que o job nunca usa.

**Medido e deixado como está**, porque cada item fica abaixo de 0,1s: converter
os números no SQL em vez de no pandas, as cópias e conversões de data no scan e
no resumo, e a consulta do corte da poda feita duas vezes. O resto do minuto é
preparar o runner e conversar com o Neon, que fica em São Paulo enquanto o
runner roda nos EUA.

## Segredos

Banco e Telegram vêm **só de variável de ambiente** (`SCANNER_*`), nunca do repo.
Veja `.env.example` — os valores lá são placeholders, não credenciais.
