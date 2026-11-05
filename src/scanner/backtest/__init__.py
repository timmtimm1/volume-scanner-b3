"""Suite de backtest dos setups (pedido do usuario em 05/11/2026).

Roda na maquina, sobre o COTAHIST desde 1995; so o resultado vai para o app.
Nao alimenta a regra do alerta de 6 sigma e nao muda nada nela.

- `simulador`: entrada no pregao seguinte, stop, alvo, stop movel, saida pela
  MME 9, custos -- pregao a pregao, sem olhar o futuro;
- `suite`: todos os setups x todas as saidas num lote de papeis, com um trade
  de controle (papel sorteado no mesmo dia) para cada trade;
- `metricas`: expectativa em R com intervalo, contra o controle, e o protocolo
  de escolha (1995-2015) e conferencia (2016-2026).
"""
