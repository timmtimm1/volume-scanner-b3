"""Baixa o historico diario de todas as moedas da Binance para o backtest de cripto.

    SCANNER_BINANCE_URL=https://api.binance.com/api/v3 \\
        python scripts/cripto_historico.py <pasta>

Grava `<pasta>/barras.pkl`, no formato que `scripts/backtest_setups.py processar`
le. Uma moeda por arquivo em `<pasta>/moedas/`, para a carga poder ser retomada.

Entram todos os pares a vista contra USDT que a Binance ja listou, inclusive os
deslistados que a API ainda conhece: testar so as moedas que sobreviveram ate
hoje inflaria o resultado (o controle sorteado tambem vem dessa lista, entao o
vies que sobra vale para os dois lados).

Ficam de fora o que nao e "cripto que se mexe":
- tokens alavancados da Binance (BTCUP, ETHDOWN, ...), pelo nome;
- stablecoins e moeda estatal tokenizada (USDC, EUR, ...), pelo proprio preco:
  quem passou a vida a menos de 10% de distancia da propria mediana em 95% dos
  dias nao e ativo de risco, tenha o nome que tiver;
- ouro e bitcoin embrulhados (PAXG, WBTC, ...), por lista: o preco deles e de
  outro ativo.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import httpx
import pandas as pd

from scanner.cripto import binance

INICIO = date(2017, 1, 1)
# Preco de outro ativo: ouro, bitcoin e ether embrulhados.
EMBRULHADOS = frozenset({"PAXG", "XAUT", "WBTC", "WBETH", "BETH", "BNSOL"})
# Stablecoin: a 95% dos dias a menos de 10% da propria mediana.
FAIXA_ESTAVEL = 0.10
DIAS_ESTAVEIS = 0.95


def e_estavel(fechamento: pd.Series) -> bool:
    if len(fechamento) < 30:
        return False
    mediana = float(fechamento.median())
    perto = ((fechamento / mediana - 1).abs() < FAIXA_ESTAVEL).mean()
    return bool(perto >= DIAS_ESTAVEIS)


def main(pasta: Path) -> None:
    moedas_dir = pasta / "moedas"
    moedas_dir.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=60) as cliente:
        pares = binance.buscar_pares(so_negociando=False, cliente=cliente)
        print(f"{len(pares)} pares contra USDT", flush=True)
        for k, (moeda, par) in enumerate(sorted(pares.items()), start=1):
            destino = moedas_dir / f"{moeda}.pkl"
            if destino.exists():
                continue
            try:
                barras = binance.buscar_barras(moeda, par, INICIO, cliente=cliente)
            except Exception as exc:  # um par ruim nao derruba os outros 500
                print(f"  {moeda}: falhou ({exc})", flush=True)
                continue
            barras.to_pickle(destino)
            if k % 25 == 0:
                print(f"  {k}/{len(pares)}", flush=True)

    partes: list[pd.DataFrame] = []
    fora: list[str] = []
    for arquivo in sorted(moedas_dir.glob("*.pkl")):
        b = pd.read_pickle(arquivo)
        if b.empty:
            continue
        moeda = arquivo.stem
        if moeda in EMBRULHADOS or e_estavel(b["close"]):
            fora.append(moeda)
            continue
        partes.append(b)
    barras = pd.concat(partes, ignore_index=True)
    barras["ticker"] = barras["ticker"].astype(str)
    barras.to_pickle(pasta / "barras.pkl")
    print(
        f"{barras['ticker'].nunique()} moedas, {len(barras):,} barras, de "
        f"{barras['trade_date'].min().date()} a {barras['trade_date'].max().date()}"
    )
    print(f"fora ({len(fora)}): {', '.join(fora)}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(Path(sys.argv[1]))
