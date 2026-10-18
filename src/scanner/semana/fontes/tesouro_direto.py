"""Juros do Brasil pelo Tesouro Direto: a taxa que o investidor recebe ao comprar.

Uma fonte so para a curva prefixada e para o juro real (IPCA+). O CSV oficial do
Tesouro Transparente traz, desde 2004, a taxa de cada titulo em cada dia. A
ANBIMA saiu: o download gratis dela guarda so as ultimas semanas (testado em
18/10/2026: 16/04/2026, 2024, 2020 e 2016 voltaram vazios), e uma serie de 10
anos precisa de historico.

Um VERTICE de N anos numa data e a interpolacao LINEAR da taxa em funcao do
prazo (em anos) entre os dois titulos vizinhos. Abaixo do menor prazo o vertice
fica nulo. Acima do maior, so o Pre de 10 anos precisa de ajuda: o Tesouro lanca
uma NTN-F de ~10,9 anos em fevereiro dos anos pares, e de janeiro de cada ano
impar a fevereiro do seguinte o prefixado mais longo vence em 8,87 a 10 anos
(57 semanas a cada 2 anos). Ali a reta dos dois titulos mais longos (sempre a
2,00 anos um do outro) e prolongada por ate EXTRAPOLACAO_MAXIMA_ANOS. Conferido
nas 235 semanas em que o 10 anos existe: erro mediano de 6 bp, maximo de 23 bp.
Na ponta curta o mesmo teste da 13 bp de mediana e 70 de maximo: la NAO se
prolonga, e o Pre de 1 ano fica sem ponto de jan a jun/2023.

Tipos: `Tesouro Prefixado` (LTN, zero cupom) e `... com Juros Semestrais`
(NTN-F) formam a curva nominal; `Tesouro IPCA+` e `... com Juros Semestrais`,
a real. Com dois titulos no MESMO vencimento, vale o sem cupom: o juro dele e o
da taxa spot, o de um titulo com cupom mistura prazos.
"""

from __future__ import annotations

import io
from datetime import date, timedelta
from typing import Any

import httpx
import numpy as np
import pandas as pd

from scanner.semana.fontes import FonteIndisponivelError, baixar
from scanner.semana.periodo import sextas

FONTE = "tesouro_direto"
URL = (
    "https://www.tesourotransparente.gov.br/ckan/dataset/"
    "df56aa42-484a-4a59-8184-7676580c81e3/resource/"
    "796d2059-14e9-44e3-80c9-2d9e30b405c1/download/PrecoTaxaTesouroDireto.csv"
)
DIAS_POR_ANO = 365.25
# O arquivo tem ~15 MB: o timeout padrao de 20 s das outras fontes e curto para ele.
TIMEOUT_DOWNLOAD = 120.0
DIAS_UTEIS_POR_ANO = 252
# Quanto a reta pode passar do titulo mais longo. Medido no CSV inteiro: o maior
# alcance necessario foi 10 - 8,87 = 1,13 ano; 1,2 cobre isso e nada mais.
EXTRAPOLACAO_MAXIMA_ANOS = 1.2

# Tipo do titulo -> (curva, tem cupom).
TIPOS: dict[str, tuple[str, bool]] = {
    "Tesouro Prefixado": ("nominal", False),
    "Tesouro Prefixado com Juros Semestrais": ("nominal", True),
    "Tesouro IPCA+": ("real", False),
    "Tesouro IPCA+ com Juros Semestrais": ("real", True),
}
COLUNAS = ["Tipo Titulo", "Data Vencimento", "Data Base", "Taxa Compra Manha", "Taxa Venda Manha"]

# Serie -> (curva, prazo em anos). A ordem e a da tabela e do grafico.
VERTICES: dict[str, tuple[str, int]] = {
    "pre_1a": ("nominal", 1),
    "pre_2a": ("nominal", 2),
    "pre_5a": ("nominal", 5),
    "pre_10a": ("nominal", 10),
    "ipca_5a": ("real", 5),
    "ipca_10a": ("real", 10),
}
SERIES_PRE = ("pre_1a", "pre_2a", "pre_5a", "pre_10a")
SERIES_REAL = ("ipca_5a", "ipca_10a")

COLUNAS_SEMANAL = ["semana", "serie", "taxa", "data_base", "fonte"]


def ler_csv(conteudo: bytes | str) -> pd.DataFrame:
    """Os titulos das duas curvas: curva, sem_cupom, vencimento, data_base, taxa (% a.a.).

    A taxa e a de compra (`Taxa Compra Manha`); se vier 0 ou vazia, a de venda.
    Titulo sem taxa nenhuma fica de fora. Duplicata de vencimento na mesma data:
    fica o sem cupom.
    """
    bruto = conteudo.encode("latin-1") if isinstance(conteudo, str) else conteudo
    try:
        tabela = pd.read_csv(
            io.BytesIO(bruto),
            sep=";",
            decimal=",",
            encoding="latin-1",
            usecols=COLUNAS,
            dtype={"Tipo Titulo": "string"},
        )
    except (ValueError, pd.errors.ParserError) as exc:
        raise FonteIndisponivelError(FONTE, f"CSV ilegivel: {exc}") from exc
    tabela = tabela[tabela["Tipo Titulo"].isin(list(TIPOS))].copy()
    if tabela.empty:
        raise FonteIndisponivelError(FONTE, "CSV sem titulos prefixados nem IPCA+")

    try:
        vencimento = pd.to_datetime(tabela["Data Vencimento"], format="%d/%m/%Y")
        data_base = pd.to_datetime(tabela["Data Base"], format="%d/%m/%Y")
    except ValueError as exc:
        raise FonteIndisponivelError(FONTE, f"data ilegivel: {exc}") from exc

    compra = pd.to_numeric(tabela["Taxa Compra Manha"], errors="coerce")
    venda = pd.to_numeric(tabela["Taxa Venda Manha"], errors="coerce")
    taxa = compra.where(compra > 0, venda.where(venda > 0))
    tipo = tabela["Tipo Titulo"].astype(str)
    titulos = pd.DataFrame(
        {
            "curva": tipo.map(lambda t: TIPOS[t][0]),
            "sem_cupom": ~tipo.map(lambda t: TIPOS[t][1]).astype(bool),
            "vencimento": vencimento,
            "data_base": data_base,
            "taxa": taxa.astype(float),
        }
    )
    titulos = titulos[titulos["taxa"].notna()]
    # Sem cupom primeiro; depois a duplicata do mesmo vencimento cai fora.
    titulos = titulos.sort_values("sem_cupom", ascending=False, kind="stable")
    titulos = titulos.drop_duplicates(["curva", "data_base", "vencimento"], keep="first")
    return titulos.sort_values(["data_base", "vencimento"]).reset_index(drop=True)


def interpolar(titulos: pd.DataFrame, curva: str, data_base: pd.Timestamp, anos: float) -> float:
    """A taxa de `anos` anos na curva, em `data_base`; NaN se estiver fora da faixa.

    Acima do maior prazo vale o prolongamento da reta, ate EXTRAPOLACAO_MAXIMA_ANOS.
    """
    do_dia = titulos[(titulos["curva"] == curva) & (titulos["data_base"] == data_base)]
    prazo = (do_dia["vencimento"] - data_base).dt.days.to_numpy(dtype=float) / DIAS_POR_ANO
    vivos = prazo > 0
    if vivos.sum() < 2:
        return float("nan")
    taxas = do_dia["taxa"].to_numpy(dtype=float)[vivos]
    prazos = prazo[vivos]
    ordem = np.argsort(prazos)
    prazos, taxas = prazos[ordem], taxas[ordem]
    x2 = prazos[-1]
    if anos > x2:
        if anos - x2 > EXTRAPOLACAO_MAXIMA_ANOS:
            return float("nan")
        # Prolonga a reta dos dois titulos mais longos (ja sem duplicata de vencimento).
        x1, y1, y2 = prazos[-2], taxas[-2], taxas[-1]
        return float(y2 + (y2 - y1) / (x2 - x1) * (anos - x2))
    return float(np.interp(anos, prazos, taxas, left=np.nan))


def data_base_da_semana(datas: pd.DatetimeIndex, sexta: date) -> pd.Timestamp | None:
    """A ultima data base <= sexta e >= a segunda da semana; None se a semana nao teve dado."""
    alvo = pd.Timestamp(sexta)
    posicao = int(datas.searchsorted(alvo, side="right")) - 1
    if posicao < 0:
        return None
    candidata: pd.Timestamp = datas[posicao]
    return candidata if candidata >= alvo - pd.Timedelta(days=4) else None


def serie_semanal(titulos: pd.DataFrame, desde: date, ate: date) -> pd.DataFrame:
    """Um ponto por semana e por serie: semana (sexta), serie, taxa, data_base, fonte.

    Ponto sem taxa (vertice fora da faixa de prazos) nao entra; semana sem dado do
    Tesouro tambem nao. Um loop por DATA (cerca de 520), nao por ticker.
    """
    datas = pd.DatetimeIndex(sorted(titulos["data_base"].unique()))
    por_data = dict(tuple(titulos.groupby("data_base")))
    linhas: list[dict[str, Any]] = []
    for sexta in sextas(desde, ate):
        base = data_base_da_semana(datas, sexta)
        if base is None:
            continue
        do_dia = por_data[base]
        for serie, (curva, anos) in VERTICES.items():
            taxa = interpolar(do_dia, curva, base, anos)
            if np.isfinite(taxa):
                linhas.append(
                    {
                        "semana": sexta,
                        "serie": serie,
                        "taxa": round(taxa, 4),
                        "data_base": base.date(),
                        "fonte": FONTE,
                    }
                )
    return pd.DataFrame(linhas, columns=COLUNAS_SEMANAL)


def baixar_titulos(*, cliente: httpx.Client | None = None) -> pd.DataFrame:
    """Baixa o CSV inteiro (~15 MB, atras de um redirecionamento) e le os titulos."""
    proprio = cliente is None
    http = cliente or httpx.Client(timeout=TIMEOUT_DOWNLOAD, follow_redirects=True)
    try:
        return ler_csv(baixar(FONTE, URL, cliente=http).content)
    finally:
        if proprio:
            http.close()


def montar_curva(historico: pd.DataFrame, sexta: date, series: tuple[str, ...]) -> dict[str, Any]:
    """Os vertices de `series` na semana de `sexta` contra a semana anterior.

    Mesma forma do bloco antigo: data, data_anterior, vertices (du, anos, taxa,
    taxa_anterior, variacao_bp), mais `fonte`. `data` e a data base real do
    ponto desta semana. Vertice sem taxa nesta semana sai da lista; sem nenhum,
    a fonte e dada como indisponivel.
    """
    anterior = sexta - timedelta(days=7)
    atual = historico[(historico["semana"] == sexta) & historico["serie"].isin(series)]
    if atual.empty:
        raise FonteIndisponivelError(FONTE, f"sem taxa do Tesouro Direto na semana de {sexta}")
    antes = historico[(historico["semana"] == anterior) & historico["serie"].isin(series)]
    taxa_antes: dict[str, float] = dict(
        zip(antes["serie"], antes["taxa"].astype(float), strict=True)
    )
    taxa_atual: dict[str, float] = dict(
        zip(atual["serie"], atual["taxa"].astype(float), strict=True)
    )
    base_antes = antes["data_base"].max() if not antes.empty else None

    vertices: list[dict[str, Any]] = []
    for serie in series:
        if serie not in taxa_atual:
            continue
        anos = VERTICES[serie][1]
        taxa = taxa_atual[serie]
        ant = taxa_antes.get(serie)
        vertices.append(
            {
                "du": anos * DIAS_UTEIS_POR_ANO,
                "anos": float(anos),
                "taxa": taxa,
                "taxa_anterior": None if ant is None else float(ant),
                "variacao_bp": None if ant is None else (taxa - float(ant)) * 100,
            }
        )
    return {
        "data": atual["data_base"].max(),
        "data_anterior": base_antes,
        "vertices": vertices,
        "fonte": FONTE,
    }
