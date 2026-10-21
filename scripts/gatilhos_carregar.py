"""Le o COTAHIST de 1995 em diante e grava as barras num pickle, para o estudo.

Uso: python scripts/gatilhos_carregar.py <pasta dos anuais> <pasta dos diarios> <saida.pkl>

Comeca em 1995: antes do Plano Real (jul/1994) os precos sao em cruzeiro, com
hiperinflacao, e candle de um dia nao e comparavel com o de outro.

Os zips de 1998 a 2004 nao tem .TXT dentro (o arquivo vem sem extensao). O
parser do main so aceita .TXT; aqui o arquivo e extraido antes, sem mexer nele.
Validacao de preco linha a linha no modo `either` (o mesmo do turbo): a linha
passa se cumprir a regra `truncation` OU a `relative`. Linha que nao cumpre
nenhuma sai do estudo; acima de 0,5% de linhas fora o arquivo e recusado, como
na carga normal.
"""

from __future__ import annotations

import sys
import tempfile
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from scanner.config import IngestConfig, load_config
from scanner.ingest.cotahist import PriceCheckError, parse_file

PRIMEIRO_ANO = 1995


def _ler(caminho: Path, base: IngestConfig) -> tuple[pd.DataFrame, str]:
    with tempfile.TemporaryDirectory() as tmp:
        alvo = caminho
        with zipfile.ZipFile(caminho) as z:
            nomes = [n for n in z.namelist() if not n.endswith("/")]
            if not any(n.upper().endswith(".TXT") for n in nomes):
                (unico,) = nomes
                alvo = Path(tmp) / "cotahist.txt"
                alvo.write_bytes(z.read(unico))
        # Le sem abortar e valida aqui, linha a linha.
        cfg = base.model_copy(update={"price_check_max_failure": 1.0})
        frame, _ = parse_file(alvo, cfg)
    vol = frame["volume_financial"].to_numpy(dtype=float)
    piso = frame["avg_price"].to_numpy(dtype=float) * frame["volume_shares"].to_numpy(dtype=float)
    teto = (frame["avg_price"].to_numpy(dtype=float) + 0.01) * frame["volume_shares"].to_numpy(
        dtype=float
    )
    checavel = vol > 0
    truncation = (vol >= piso * (1 - 1e-6)) & (vol <= teto * (1 + 1e-6))
    relative = np.abs(piso - vol) / np.where(checavel, vol, 1.0) <= base.price_check_tolerance
    ruim = checavel & ~(truncation | relative)
    taxa = ruim.sum() / max(checavel.sum(), 1)
    if taxa > base.price_check_max_failure:
        raise PriceCheckError(f"{caminho.name}: {taxa:.3%} das linhas sem preco coerente")
    return frame.loc[~ruim].reset_index(
        drop=True
    ), f"either, {int(ruim.sum())} linhas fora ({taxa:.3%})"


def main() -> None:
    anuais, diarios, saida = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    base = load_config(Path(__file__).resolve().parents[1] / "config.yaml").ingest
    arquivos = sorted(p for p in anuais.glob("COTAHIST_A*.ZIP") if int(p.stem[-4:]) >= PRIMEIRO_ANO)
    arquivos += sorted(diarios.glob("COTAHIST_D*.ZIP"))
    blocos = []
    for p in arquivos:
        frame, como = _ler(p, base)
        print(f"{p.name}: {len(frame):>7} barras, {como}", flush=True)
        for col in ("open", "high", "low", "close", "avg_price"):
            frame[col] = frame[col].astype(np.float64)
        blocos.append(frame.drop(columns=["volume_shares"]))
    barras = pd.concat(blocos, ignore_index=True)
    barras = barras.drop_duplicates(["ticker", "trade_date"], keep="last")
    barras["ticker"] = barras["ticker"].astype("category")
    barras = barras.sort_values(["trade_date", "ticker"]).reset_index(drop=True)
    barras.to_pickle(saida)
    print(
        f"total {len(barras)} barras, {barras['ticker'].nunique()} papeis, "
        f"{barras['trade_date'].nunique()} pregoes, "
        f"{barras['trade_date'].min():%d/%m/%Y} a {barras['trade_date'].max():%d/%m/%Y}"
    )


if __name__ == "__main__":
    main()
