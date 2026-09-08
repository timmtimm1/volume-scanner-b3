# Demo visual no n8n — parqueado

Ideia: reproduzir o pipeline como um workflow visual do n8n, para gravar um GIF
curto mostrando o gatilho disparando, o dado saindo do Postgres e a mensagem
chegando no Telegram. Serve para apresentacao, nao para producao.

**O GitHub Actions continua sendo o pipeline real.** O `daily.yml` roda testado
e sem custo; o n8n seria so uma vitrine.

## Onde parou

O container esta pronto nesta maquina:

```bash
docker start n8n-demo     # ja criado, imagem n8nio/n8n
# http://localhost:5678
```

Falta preencher a tela "Set up owner account" (email, nome, senha — tudo local,
nada e verificado) e montar tres nos:

1. **Manual Trigger** — para disparar na hora de gravar
2. **Postgres** — credencial apontando para o Neon, com a query abaixo
3. **Telegram** — credencial com o token do BotFather, mandando a mensagem

## A query do no Postgres

```sql
-- Evento mais forte, para a demo ter um caso vistoso.
-- Troque por "ORDER BY trade_date DESC" se quiser sempre o mais recente.
SELECT
  ticker,
  trade_date,
  max_z_log,
  triggered_windows,
  volume_financial,
  features
FROM volume_scanner.events
ORDER BY max_z_log DESC
LIMIT 1;
```

`features` e JSONB: no n8n, os campos da secao 3.2 saem como
`{{ $json.features.ret_day }}`, `{{ $json.features.avg_ticket }}` e assim por
diante.
