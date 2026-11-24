"""Baixa o historico diario de todas as moedas da Binance para o backtest de cripto.

    SCANNER_BINANCE_URL=https://api.binance.com/api/v3 \\
        python scripts/cripto_historico.py <pasta>

Grava `<pasta>/barras.pkl`, no formato que `scripts/backtest_setups.py processar`
le. Uma moeda por arquivo em `<pasta>/moedas/`, para a carga poder ser retomada.

Entram todos os pares a vista contra USDT que a Binance ja listou, inclusive os
deslistados que a API ainda conhece: testar so as moedas que sobreviveram ate
hoje inflaria o resultado (o controle sorteado tambem vem dessa lista, entao o
vies que sobra vale para os dois lados).

Fica de fora o que nao e "cripto que se mexe" (alavancados, stablecoins,
embrulhados): a regra mora em `scanner.cripto.filtros`, a mesma da analise
contra o Bitcoin.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import httpx
import pandas as pd

from scanner.cripto import binance
from scanner.cripto.filtros import motivo_de_fora

INICIO = date(2017, 1, 1)


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
        # Indexada pela data: a regra das acoes tokenizadas olha a estreia.
        if motivo_de_fora(moeda, b.set_index("trade_date")["close"]) is not None:
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
