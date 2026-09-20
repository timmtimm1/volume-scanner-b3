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
- [Recriar do zero](#recriar-do-zero)
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
(`.github/workflows/pregao.yml`): carga, métricas, alerta, resumo e poda, na ordem certa,
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
- **Login com GitHub**, restrito a uma conta, só para alertas e trades. O resto do
  site é público.
- **Acompanhamento de trades.** Logado, você registra na ficha do papel as compras
  e vendas que fez na corretora, inclusive parciais e com data passada. O site
  calcula preço médio e realizado, e o trade aparece marcado a mercado: na ficha
  (com setas de compra e venda no gráfico e a linha do preço médio), em `/trades`
  e no detalhe de cada trade, com o resultado por pregão. O fechamento de cada dia
  fica guardado em `trade_snapshots`, gravado pelo job noturno, e o resumo diário
  no Telegram ganha o bloco **Seus trades** com a posição de cada trade aberto e
  dos encerrados no pregão. Sem custos de corretagem e sem proventos, por enquanto.
- **Fundamentos da CVM.** A carga traz para o banco os balanços trimestrais e
  anuais de cada empresa negociada (ITR e DFP dos dados abertos da CVM), com a
  data em que cada um foi entregue, e os proventos em dinheiro de cada papel —
  dividendo e juros sobre capital próprio, por classe, porque a ON e a PN
  recebem valores diferentes. Em cima disso, o trimestre já calculado: receita,
  EBITDA e lucro do trimestre e dos últimos 12 meses, patrimônio dos
  controladores, dívida líquida e liquidez. Na ficha do papel isso vira a aba
  **Fundamentos**, com os múltiplos calculados **na data que a ficha está
  mostrando**: abrindo a ficha por um evento de março, o P/L é o de março, com o
  balanço que já era público naquele dia. As datas de entrega viram marca no
  gráfico, para dar para ver se o volume anômalo veio logo depois do resultado.
- **Régua no gráfico.** Um toque mede de agora até um nível (%, R$ por ação e,
  logado, o efeito no trade aberto, com botão para virar alerta de preço); dois
  toques medem o movimento entre dois pontos e quantos pregões ele levou.

## A interface

```bash
cd web
npm install
npm run dev        # http://localhost:3000
```

As telas de dado — scanner, histórico, papéis e cada ficha — são **estáticas**.
As consultas rodam no build, o Actions dispara o rebuild depois do scan, e é o
que faz abrir instantâneo no 4G.

Só roda no servidor o que depende de quem está olhando ou do preço de agora:
`/api/auth` (login), `/api/alertas` e `/api/trades` (exigem login), as páginas
`/alertas` e `/trades` (mostram só o convite para entrar sem login) e
`/api/cotacao` (o candle de hoje, com cache de 5 minutos por papel).
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
   é o que faz o `pregao.yml` reconstruir o site depois de cada pregão

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
projeto no mesmo banco). Sem chaves estrangeiras entre as tabelas de mercado — a ligação é por
`(ticker, trade_date)`, não por relação declarada no banco, porque a poda apaga barras
antigas e os eventos ficam. A exceção são os trades: operação e snapshot não existem
sem o trade, e apagar o trade apaga os dois.

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
    trades {
        bigint id PK
        text ticker
        date aberto_em
        date encerrado_em
    }
    trade_operacoes {
        bigint id PK
        bigint trade_id FK
        text tipo
        date data
        int quantidade
        numeric preco
        numeric preco_medio_apos
        numeric realizado_apos
    }
    trade_snapshots {
        bigint trade_id PK, FK
        date trade_date PK
        int quantidade
        numeric fechamento
        numeric resultado
    }
    empresas {
        int cd_cvm PK
        text cnpj
        text nome
        text setor_cvm
        text situacao
    }
    empresa_tickers {
        text ticker PK
        int cd_cvm FK
        text fonte
        timestamptz verificado_em
    }
    cvm_documentos {
        int cd_cvm PK, FK
        text tipo PK
        date dt_refer PK
        smallint versao
        date recebido_original
        text escopo
        text layout
    }
    cvm_resultados {
        int cd_cvm PK, FK
        date dt_ini PK
        date dt_fim PK
        numeric receita
        numeric lucro_liquido
        numeric ebit
    }
    cvm_balancos {
        int cd_cvm PK, FK
        numeric ativo_total
        numeric patrimonio_liquido
        numeric emprestimos_lp
        bigint acoes_on
    }
    fundamentos_trimestre {
        int cd_cvm PK, FK
        date dt_fim PK
        text rotulo
        text origem
        date publicado_em
        numeric receita_12m
        numeric lucro_12m
    }
    proventos {
        bigint id PK
        text ticker FK
        text tipo
        numeric valor
        date data_com
        text fonte
    }

    daily_bars ||--o{ volume_metrics : "ticker + trade_date"
    daily_bars ||--o{ daily_features : "ticker + trade_date"
    daily_bars ||--o{ events : "ticker + trade_date"
    daily_bars ||--o{ price_alerts : "originou"
    trades ||--o{ trade_operacoes : "compras e vendas"
    trades ||--o{ trade_snapshots : "um por pregão"
    empresas ||--o{ empresa_tickers : "papéis da empresa"
    empresas ||--o{ cvm_documentos : "ITR e DFP entregues"
    cvm_documentos ||--o{ cvm_resultados : "DRE por período"
    cvm_documentos ||--|| cvm_balancos : "posição na data"
    empresa_tickers ||--o{ proventos : "dividendos e JCP"
    empresas ||--o{ fundamentos_trimestre : "trimestre calculado"
```

| Tabela | Guarda |
|---|---|
| `daily_bars` | Uma linha por papel/pregão, vinda do COTAHIST |
| `volume_metrics` | Um z-score por papel/pregão/janela (30, 45, 60) |
| `daily_features` | Contexto do pregão (ticket médio, faixa de 252d etc.) — tenha virado evento ou não |
| `events` | Só o que cruzou o limiar. Dedupe por `(ticker, trade_date)` |
| `digest_sends` | Carimbo de que o resumo diário já saiu, para não reenviar |
| `price_alerts` | Alertas de rompimento de preço, criados na ficha do papel |
| `trades` | Um trade real por papel: aberto na primeira compra, encerrado quando a quantidade zera |
| `trade_operacoes` | Cada compra e venda, com a posição depois dela (quantidade, preço médio, realizado) |
| `trade_snapshots` | O trade marcado a mercado no fechamento de cada pregão. **Fica fora da poda**: as barras de 400 pregões atrás somem, o resultado daquele dia não |
| `empresas` | Cadastro da CVM das empresas alcançadas por algum papel do banco |
| `empresa_tickers` | De qual empresa é cada ticker, e de onde veio essa ligação. Linha sem empresa é o "já procurei e não achei", que evita procurar de novo todo dia |
| `cvm_documentos` | Cada ITR ou DFP entregue: versão, data da primeira entrega e da última, e se o balanço é consolidado ou individual |
| `cvm_resultados` | As linhas da DRE por período (trimestre e acumulado do ano) e a depreciação da DVA |
| `cvm_balancos` | As linhas do balanço na data e a composição do capital (ações e tesouraria) |
| `fundamentos_trimestre` | O trimestre já calculado que a ficha lê: receita, EBITDA e lucro do trimestre e de 12 meses, patrimônio dos controladores, dívida líquida, liquidez e ações em circulação. É derivada — pode ser apagada e refeita a partir das tabelas acima |
| `proventos` | Dividendos e JCP por papel, com a data com. Uma linha por provento e por classe: a ON e a PN da mesma empresa recebem valores diferentes |
| `arquivos_externos` | Controle de download condicional dos arquivos da CVM: o que já foi baixado, e quando a CVM publicou |

Migrations via Alembic, em `src/scanner/storage/migrations/versions/` — nunca schema por SQL solto.
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

`.github/workflows/pregao.yml` faz: migrations → carga do pregão → métricas →
scan → snapshot dos trades → resumo → retenção → fundamentos da CVM → rebuild
na Vercel.

O passo dos fundamentos não pode derrubar o pregão: ele roda com
`continue-on-error`, tem teto de 15 minutos e aviso próprio no Telegram. Se a
CVM estiver fora do ar, o alerta e o resumo saem do mesmo jeito, e a aba
Fundamentos fica com os dados da véspera.

O teto existe porque `continue-on-error` sozinho não bastava. O limite de 30
minutos vale para o job inteiro: em 19/09/2026 a carga ficou 29min36s de pé, o
job foi cancelado, e o **rebuild na Vercel nem chegou a rodar**. O pregão estava
no banco havia meia hora e o site continuou mostrando o build anterior até
alguém rodar o pregão manual. Uma passada boa leva cerca de 7 minutos.

Cortar a carga no meio é seguro: ela grava empresa por empresa e marca cada uma
como consultada, então a passada seguinte continua de onde parou; e a tabela de
trimestres é trocada inteira numa transação só.

Ele não roda sozinho. Dois workflows o chamam, e os dois executam exatamente as
mesmas etapas:

| Workflow | Quem dispara | Pregão |
|---|---|---|
| `daily.yml` — **daily (agendado)** | o cron externo, nos horários abaixo | sempre `ultimo` |
| `pregao-manual.yml` — **pregao manual** | você, se quiser | `ultimo` ou uma data |

O manual é opcional: se ninguém rodar, a agenda faz o serviço.

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

Para rodar à mão: **Actions → pregao manual → Run workflow**, com `ultimo` ou uma
data. Pelo terminal:

```bash
gh workflow run pregao-manual.yml -f trade_date=ultimo
```

> **Nunca use Re-run numa execução antiga.** O Re-run do GitHub repete a execução
> inteira: a data que ela pediu e o commit daquele dia. Em 16/09/2026 um Re-run
> reprocessou o pregão da véspera num commit temporário e reenviou o resumo no
> Telegram. Por isso o primeiro passo do `pregao.yml` é uma guarda: se a execução
> é uma repetição e o `main` já mudou, ela para antes de tocar no banco, sem aviso
> de falha no Telegram, e diz na tela do Actions para usar o manual. Repetir no
> `main` atual continua valendo — é o que se faz quando a B3 saiu do ar.

> **Por que dois horários.** A B3 publica o arquivo do dia com atraso variável:
> às 21:08 em 08/09/2026, mas em 11/09 às 21:59 ainda dava 404, e às 02:42 a B3
> respondeu 403. O download tenta de novo em 404, 403, 429 e 5xx, com espera
> entre as tentativas. Se mesmo assim não sair à noite, a manhã cobre.

## Recriar do zero

Roteiro para subir uma cópia própria do projeto — repositório, banco, bot, site e
agendamento — com as suas contas. Cada peça já está explicada nas seções acima;
aqui fica a **ordem**, que importa, e o que não está escrito em outro lugar.

Não é preciso copiar o banco de ninguém: os dados de mercado vêm dos arquivos
públicos da B3 e são carregados do zero.

**Contas**, todas no plano gratuito: GitHub, [Neon](https://neon.tech),
[Vercel](https://vercel.com), [cron-job.org](https://cron-job.org) e Telegram.
**Na máquina:** o que está em [Requisitos](#requisitos).

### 1. Repositório

1. Faça fork, ou clone e suba num repositório novo seu.
2. Num fork, a aba **Actions** vem desligada: ative. Secrets não acompanham o fork.
3. Quando o seu site existir, troque os badges do topo e o link "Ao vivo" para ele.

### 2. Local, para ver funcionando

Siga [Desenvolvimento](#desenvolvimento), incluindo a carga do histórico, e depois
[A interface](#a-interface). Se o scanner abre em `localhost:3000` com dado, o
código está certo e o resto é configuração.

### 3. Banco

[Banco no Neon](#1-banco-no-neon), passos 1 a 5. Vem antes do site porque o build
da Vercel lê o banco.

### 4. Bot

[Bot do Telegram](#2-bot-do-telegram).

### 5. Site

1. Faça o [Deploy na Vercel](#deploy-na-vercel), de início só com
   `SCANNER_DATABASE_URL`. O primeiro deploy dá a URL do site, que os passos
   seguintes usam.
2. Crie um OAuth App no GitHub, em **Settings → Developer settings → OAuth Apps**:
   - Homepage URL: `https://SEU-SITE.vercel.app`
   - Authorization callback URL: `https://SEU-SITE.vercel.app/api/auth/callback/github`
3. Complete as variáveis da Vercel: `AUTH_SECRET`, `AUTH_GITHUB_ID`,
   `AUTH_GITHUB_SECRET` e `AUTH_GITHUB_LOGIN` — **o seu login do GitHub**. Sem ela
   o site recusa todo login, inclusive o seu.
4. Faça um redeploy para as variáveis valerem e copie o **Deploy Hook**
   (**Settings → Git → Deploy Hooks**).

### 6. Secrets no GitHub

[Secrets no GitHub](#3-secrets-no-github), com o Deploy Hook em
`VERCEL_DEPLOY_HOOK` e a URL do site em `SCANNER_WEB_BASE_URL` — é ela que monta o
link que chega no Telegram.

### 7. Primeiro teste

Em **Actions → pregao manual → Run workflow**, com `ultimo`. O resumo do pregão
deve chegar no Telegram e a Vercel deve reconstruir o site.

Para rodar de novo, use sempre **Run workflow**, nunca **Re-run**
([por quê](#4-o-job-diário)).

### 8. Agendamento

Quem dispara os workflows é o cron-job.org, não o agendador do GitHub
([por quê](#4-o-job-diário)).

1. Crie um token em **Settings → Developer settings → Personal access tokens →
   Fine-grained tokens**, com acesso só a este repositório e permissão
   **Actions: Read and write**.
2. No cron-job.org, crie um job para cada entrada de
   [`.github/cron-externo.yml`](.github/cron-externo.yml) — `daily-noite`,
   `daily-manha` e `rompimentos` —, no fuso **America/Sao_Paulo**, com o `cron`
   de lá:
   - URL: `https://api.github.com/repos/SEU-USUARIO/SEU-REPO/actions/workflows/ARQUIVO.yml/dispatches`,
     com o `workflow` da entrada no lugar de `ARQUIVO.yml`
   - Método `POST`, corpo `{"ref":"main"}`
   - Headers: `Authorization: Bearer SEU-TOKEN`, `Accept: application/vnd.github+json`
     e `Content-Type: application/json`
3. Sucesso é **204, sem corpo**. Se o painel validar a resposta, a validação
   precisa aceitar isso.

### Com Claude Code

O repositório tem `CLAUDE.md`, então dá para pedir *"siga a seção Recriar do zero
do README"*. Criar as contas, falar com o BotFather, criar o OAuth App e o token
e montar os jobs no cron-job.org continuam sendo à mão: são logins e telas de
site.

Não cole connection string nem token na conversa — o que passa por ela fica no
histórico da sessão. O que leva segredo (a carga no Neon, `gh secret set`, as
variáveis da Vercel) rode num terminal seu, fora do Claude Code.

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
- **A CVM publica os balanços uma vez por semana**, não todo dia. Um resultado
  divulgado numa terça só entra na próxima atualização, até cerca de 7 dias
  depois. A ficha mostra a data dos dados para não confundir "ainda não saiu"
  com "a CVM ainda não publicou o arquivo".
- **A CVM não publica o quarto trimestre.** Saem ITR para o 1T, 2T e 3T e o DFP
  do ano; o 4T é a diferença entre os dois. E a depreciação só vem acumulada no
  ano, então a do trimestre também é uma diferença — sem ela não há EBITDA. Nas
  duas contas, quando falta o acumulado para subtrair, o trimestre fica de fora
  em vez de sair inflado: é o caso de quem mudou o exercício social.
- **O histórico antigo de proventos só entra depois de conferido.** A consulta
  do histórico na B3 casa pelo nome da empresa, que é chave fraca: "KLABIN"
  devolve os proventos de outra companhia, e "AMBEV S/A" — o nome que a própria
  B3 publica — não devolve nada, enquanto "AMBEV S.A." devolve 39. Por isso
  cada histórico é conferido antes de entrar, de dois jeitos: o fechamento que
  a B3 informa na data com tem de bater com a barra do COTAHIST daquele dia,
  ou os valores têm de coincidir com os proventos que já entraram identificados
  pelo ISIN. Sem prova, o histórico é descartado — hoje isso acontece em 117
  das 321 empresas, quase sempre porque os proventos delas são anteriores aos
  400 pregões que o banco guarda. Os proventos dos últimos 12 meses não
  dependem disso: vêm com o ISIN do papel e entram sempre.
- **Papel que parou de negociar costuma ficar sem empresa ligada.** São 9 dos
  447 do banco: a Marfrig virou MBRF3, a Eletrobras virou AXIA e as classes
  AXIA5/AXIA6 deixaram de existir, a Santos Brasil saiu da bolsa, e há dois
  ETFs e um recibo de subscrição. Ligar pelo prefixo do ticker resolveria e
  está fora de questão: na B3, o emissor "EMBR" é a EMBRAST, e não a Embraer.
  Melhor ficar sem fundamentos do que mostrar o balanço de outra empresa.
- **Um terço das empresas declara as ações em milhares, e a CVM não diz qual
  delas.** O `composicao_capital` não tem coluna de escala: a Unipar informa
  113.173.265 ações e a Afluente informa 63.085, que são 63.085.000. Nada no
  arquivo separa as duas. Sem tratar isso, P/L, P/VP, EV/EBITDA e valor de
  mercado sairiam **mil vezes errados** em um terço da base — a Afluente
  apareceria valendo R$ 461,8 mil.

  Nenhuma conferência sozinha manda. São seis camadas independentes, e a
  contagem só vale passando em **todas**:

  | camada | o que olha | pega o que as outras não pegam |
  |---|---|---|
  | `existe` | a própria contagem | ausente ou negativa |
  | `piso` | só a ordem de grandeza | contagem pequena e ilíquida |
  | `teto` | só a ordem de grandeza | contagem inflada, sem preço |
  | `serie` | o histórico da empresa | a troca de escala no meio dela |
  | `giro` | o volume negociado | impossibilidade, não estimativa |
  | `patrimonio` | preço contra o balanço | o ilíquido que o giro não vê |

  A redundância não é decorativa: dos 143 papéis recusados hoje, **19 caem por
  uma única camada** — 12 só pelo patrimônio, 4 só pelo giro, e um cada pelo
  piso, pelo teto e pela série. Tirar qualquer uma delas deixa dado errado
  passar.

  Os limites são calibrados contra a base, não chutados. O piso de 100 mil
  ações não custa nenhum papel bom: a menor contagem legítima da base é
  153.464. O corte de 2% do patrimônio cai num vão largo — os papéis com a
  escala certa não descem de 0,063 e os errados não passam de 0,006. E a série
  tolera queda de até 500×, porque grupamento de 100:1 acontece (a Mobly fez um)
  e o erro de escala é sempre de mil.

  A referência da série **só aceita trimestres que passariam no piso e no
  teto** — sem isso ela se envenena: a Gol declarou 9,17 trilhões de ações em
  três trimestres de 2025, e comparar contra esse pico reprovaria justamente os
  trimestres em que ela declarou os 3,2 bilhões corretos.

  **Reprovada a contagem publicada, uma hipótese é testada: "veio em
  milhares".** Ela não é aceita por ser plausível — passa pelas mesmas seis
  camadas, e só vale se sobreviver a todas. Não passando, o número continua
  recusado; corrigir às cegas seria trocar um erro conhecido por um chute.

  Isso resgata **127 dos 143 papéis** que a recusa pura deixaria sem valuation,
  incluindo VALE3, ITUB4, ABEV3, ITSA4, LREN3, ASAI3, ELET3 e EMBR3 — as
  gigantes são justamente as que mais declaram em milhares. Das 30 blue chips
  testadas, 30 mostram P/L e P/VP e 28 mostram valor de mercado. A ficha avisa
  quando o número foi corrigido.

  Nos 16 que nem assim passam, os quatro múltiplos que dividem por ação viram
  travessão e **a ficha diz qual conferência falhou**. Receita, lucro, EBITDA,
  patrimônio, ROE, margem, liquidez e dividend yield não dependem da contagem e
  continuam — são 9 dos 13 números.

- **51 dos 447 tickers estão sem classe**, porque a B3 não devolveu o ISIN
  deles. Sem classe, o fechamento não entra na soma por classe e o valor de
  mercado ficaria nulo mesmo com preço e quantidade em mãos. Duas saídas,
  ambas por construção e não por chute:

  - **empresa de classe única** usa o fechamento do papel aberto: se o balanço
    só tem ON, o papel que o usuário está olhando só pode ser o ON. Resolve
    EMBR3 e JBSS3;
  - **classe irrelevante não bloqueia a conta**: a Sabesp declara UMA ação
    preferencial ao lado de 3,5 bilhões de ordinárias, e exigir o preço dela
    deixaria a empresa inteira sem valor de mercado por R$ 50 de diferença.
    Abaixo de 0,1% do total, a classe não move nenhum múltiplo na segunda casa.

  Empresa com duas classes de verdade e preço faltando continua nula — somar
  só parte das ações daria um valor menor que o real. É o caso de CPLE6 e
  ELET3 enquanto a B3 não devolver o ISIN delas.
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
