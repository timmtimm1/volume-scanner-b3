"""Do dado bruto da CVM para o trimestre que a ficha mostra.

Aqui nada depende de preco: sao os numeros da empresa, nao do papel. O que
muda com a cotacao -- P/L, P/VP, EV/EBITDA, dividend yield -- e calculado na
hora de desenhar a ficha, porque depende da data que o usuario esta olhando.

Tres coisas que o dado da CVM obriga:

1. **O quarto trimestre nao existe.** A CVM publica ITR para o 1T, 2T e 3T e o
   DFP anual; o 4T sai da diferenca entre o anual e o acumulado ate o 3T.
2. **A depreciacao so vem acumulada no ano.** A DVA do ITR nao tem coluna de
   trimestre, entao a do trimestre e a diferenca entre dois acumulados. Sem
   ela nao ha EBITDA.
3. **Banco nao tem EBITDA nem divida liquida** no sentido que esses numeros
   tem numa empresa comum. No layout financeiro eles ficam nulos, e a ficha
   simplesmente nao mostra a linha.

Tudo vetorizado: uma passada sobre todas as empresas, sem laco por empresa.
"""

from __future__ import annotations

import pandas as pd

COLUNAS = [
    "cd_cvm",
    "dt_fim",
    "rotulo",
    "origem",
    "publicado_em",
    "layout",
    "receita_tri",
    "ebitda_tri",
    "lucro_tri",
    "receita_12m",
    "ebitda_12m",
    "lucro_12m",
    "patrimonio_liquido",
    "ativo_total",
    "divida_liquida",
    "divida_liquida_sem_arrendamento",
    "liquidez_corrente",
    "acoes_em_circulacao",
]

# Quantos dias separam o fim de um trimestre do fim do terceiro anterior. Sao
# 9 meses, e nao 12: a soma de 12 meses cobre quatro trimestres, e do primeiro
# ao ultimo vao tres saltos. Serve para nao somar uma janela com trimestre
# faltando no meio, que daria um acumulado de 15 meses disfarcado.
_DIAS_ENTRE_QUATRO_TRIMESTRES = (240, 310)


def _fim_do_periodo(resultados: pd.DataFrame) -> pd.DataFrame:
    """Separa, em cada documento, a linha do trimestre da linha do acumulado.

    O ITR traz as duas para a mesma conta; o DFP so traz o ano inteiro. Quem
    distingue e `dt_ini`: a do acumulado comeca no inicio do exercicio.
    """
    ordenado = resultados.sort_values(["cd_cvm", "tipo", "dt_refer", "dt_ini"])
    chave = ["cd_cvm", "tipo", "dt_refer"]
    acumulado = ordenado.groupby(chave, as_index=False).head(1).copy()
    trimestre = ordenado.groupby(chave, as_index=False).tail(1).copy()
    return acumulado.merge(
        trimestre,
        on=chave,
        suffixes=("_acum", "_tri"),
    )


def _quarto_trimestre(acumulados: pd.DataFrame) -> pd.DataFrame:
    """O 4T, que a CVM nao publica: o anual menos o acumulado ate o 3T.

    A ligacao e pelo inicio do exercicio (`dt_ini`), e nao pelo ano civil: a
    empresa com exercicio que fecha em marco tem o mesmo tratamento.
    """
    anuais = acumulados[acumulados["tipo"] == "DFP"]
    parciais = acumulados[acumulados["tipo"] == "ITR"]
    if anuais.empty or parciais.empty:
        # Sem ITR do mesmo exercicio nao ha o que subtrair, e o ano inteiro
        # viraria um "trimestre" -- que ainda estragaria a soma de 12 meses.
        return anuais.iloc[0:0].assign(origem="derivado")

    ultimo_parcial = (
        parciais.sort_values(["cd_cvm", "dt_ini", "dt_fim"])
        .groupby(["cd_cvm", "dt_ini"], as_index=False)
        .tail(1)
    )
    juntos = anuais.merge(
        ultimo_parcial,
        on=["cd_cvm", "dt_ini"],
        how="left",
        suffixes=("", "_ate_3t"),
    )
    # Sem acumulado do mesmo exercicio nao ha o que derivar: subtrair zero
    # transformaria o ano inteiro num "trimestre". Acontece com empresa que
    # mudou o exercicio social, e o numero sairia varias vezes maior.
    tem_acumulado = juntos["dt_fim_ate_3t"].notna()
    for campo in ("receita", "ebit", "lucro_controladores", "depreciacao_amortizacao"):
        juntos[campo] = juntos[campo] - juntos[f"{campo}_ate_3t"]
    juntos["origem"] = "derivado"
    return juntos[tem_acumulado]


def _depreciacao_do_trimestre(acumulados: pd.DataFrame) -> pd.Series:
    """A D&A do trimestre: a diferenca entre dois acumulados do mesmo exercicio.

    No primeiro trimestre do exercicio o acumulado JA e o trimestre, e por isso
    a diferenca so vale a partir do segundo -- `diff` deixa o primeiro como
    esta, que e o comportamento certo aqui.
    """
    ordenado = acumulados.sort_values(["cd_cvm", "dt_ini", "dt_fim"])
    anterior = ordenado.groupby(["cd_cvm", "dt_ini"])["depreciacao_amortizacao"].shift(1)
    return (ordenado["depreciacao_amortizacao"] - anterior.fillna(0)).reindex(acumulados.index)


def trimestres(
    resultados: pd.DataFrame, balancos: pd.DataFrame, documentos: pd.DataFrame
) -> pd.DataFrame:
    """Uma linha por empresa e trimestre, com os numeros que a ficha usa.

    `resultados`, `balancos` e `documentos` sao as tabelas da fase 1, inteiras.
    """
    if resultados.empty or documentos.empty:
        return pd.DataFrame(columns=COLUNAS)

    emparelhado = _fim_do_periodo(resultados)
    acumulados = emparelhado.rename(
        columns={
            "dt_ini_acum": "dt_ini",
            "dt_fim_acum": "dt_fim",
            "receita_acum": "receita",
            "ebit_acum": "ebit",
            "lucro_controladores_acum": "lucro_controladores",
            "depreciacao_amortizacao_acum": "depreciacao_amortizacao",
        }
    )[
        [
            "cd_cvm",
            "tipo",
            "dt_refer",
            "dt_ini",
            "dt_fim",
            "receita",
            "ebit",
            "lucro_controladores",
            "depreciacao_amortizacao",
        ]
    ]
    acumulados["depreciacao_tri"] = _depreciacao_do_trimestre(acumulados)

    # ITR: o proprio dado traz a linha do trimestre, que e mais exata do que a
    # diferenca de acumulados (a CVM arredonda em milhares).
    do_itr = emparelhado[emparelhado["tipo"] == "ITR"].rename(
        columns={
            "dt_fim_tri": "dt_fim",
            "receita_tri": "receita",
            "ebit_tri": "ebit",
            "lucro_controladores_tri": "lucro_controladores",
        }
    )[["cd_cvm", "tipo", "dt_refer", "dt_fim", "receita", "ebit", "lucro_controladores"]]
    do_itr = do_itr.assign(origem="ITR")

    do_dfp = _quarto_trimestre(acumulados)[
        ["cd_cvm", "tipo", "dt_refer", "dt_fim", "receita", "ebit", "lucro_controladores", "origem"]
    ]

    # Empresa que mudou de exercicio social chega a ter ITR e DFP terminando no
    # mesmo dia. Vale o trimestre reportado: derivar e sempre o plano B.
    fluxos = pd.concat([do_itr, do_dfp], ignore_index=True)
    fluxos = (
        fluxos.assign(_prioridade=(fluxos["origem"] == "derivado").astype(int))
        .sort_values(["cd_cvm", "dt_fim", "_prioridade"])
        .drop_duplicates(subset=["cd_cvm", "dt_fim"], keep="first")
        .drop(columns="_prioridade")
    )
    fluxos = fluxos.merge(
        acumulados[["cd_cvm", "tipo", "dt_refer", "depreciacao_tri"]],
        on=["cd_cvm", "tipo", "dt_refer"],
        how="left",
    )

    # EBITDA = EBIT + depreciacao e amortizacao. Na DVA a D&A vem negativa,
    # entao o sinal e invertido aqui, uma vez so.
    fluxos["ebitda_tri"] = fluxos["ebit"] + fluxos["depreciacao_tri"].abs()
    fluxos = fluxos.rename(columns={"receita": "receita_tri", "lucro_controladores": "lucro_tri"})

    fluxos = fluxos.sort_values(["cd_cvm", "dt_fim"]).reset_index(drop=True)
    _somar_doze_meses(fluxos)

    saldos = _saldos(balancos)
    docs = documentos.rename(columns={"dt_refer": "dt_fim"})[
        ["cd_cvm", "tipo", "dt_fim", "publicado_em", "layout"]
    ]

    completo = fluxos.merge(saldos, on=["cd_cvm", "tipo", "dt_refer"], how="left")
    completo = completo.merge(docs, on=["cd_cvm", "tipo", "dt_fim"], how="left")
    completo["rotulo"] = _rotulo(completo["dt_fim"])

    # Banco nao tem EBITDA nem os saldos de capital de giro no sentido usual.
    financeiro = completo["layout"] == "financeiro"
    for campo in (
        "ebitda_tri",
        "ebitda_12m",
        "divida_liquida",
        "divida_liquida_sem_arrendamento",
        "liquidez_corrente",
    ):
        completo.loc[financeiro, campo] = pd.NA

    return completo.loc[:, COLUNAS].reset_index(drop=True)


def _somar_doze_meses(fluxos: pd.DataFrame) -> None:
    """Acumula quatro trimestres seguidos, e so quando os quatro existem."""
    por_empresa = fluxos.groupby("cd_cvm")
    dias = (
        pd.to_datetime(fluxos["dt_fim"]) - pd.to_datetime(por_empresa["dt_fim"].shift(3))
    ).dt.days
    completo = dias.between(*_DIAS_ENTRE_QUATRO_TRIMESTRES)
    for campo in ("receita", "ebitda", "lucro"):
        soma = por_empresa[f"{campo}_tri"].rolling(4, min_periods=4).sum()
        fluxos[f"{campo}_12m"] = soma.reset_index(level=0, drop=True).where(completo)


def _saldos(balancos: pd.DataFrame) -> pd.DataFrame:
    """Os numeros do balanco que a ficha usa, ja derivados."""
    if balancos.empty:
        return pd.DataFrame(
            columns=[
                "cd_cvm",
                "tipo",
                "dt_refer",
                "patrimonio_liquido",
                "ativo_total",
                "divida_liquida",
                "divida_liquida_sem_arrendamento",
                "liquidez_corrente",
                "acoes_em_circulacao",
            ]
        )

    saldos = balancos.copy()
    # Patrimonio dos controladores: e sobre ele que o ROE e o P/VP fazem
    # sentido para quem compra a acao. O total inclui socios de controladas.
    saldos["patrimonio_liquido"] = saldos["patrimonio_liquido"] - saldos[
        "pl_nao_controladores"
    ].fillna(0)

    bruta = saldos["emprestimos_cp"].fillna(0) + saldos["emprestimos_lp"].fillna(0)
    arrendamento = saldos["arrendamento_cp"].fillna(0) + saldos["arrendamento_lp"].fillna(0)
    caixa = saldos["caixa"].fillna(0) + saldos["aplicacoes_financeiras"].fillna(0)
    sem_divida = saldos["emprestimos_cp"].isna() & saldos["emprestimos_lp"].isna()
    saldos["divida_liquida"] = (bruta - caixa).where(~sem_divida)
    # A CVM reporta o arrendamento dentro de "emprestimos e financiamentos".
    # Na Petrobras ele e a maior parte do numero, entao a diferenca importa.
    saldos["divida_liquida_sem_arrendamento"] = (bruta - arrendamento - caixa).where(~sem_divida)

    circulante = saldos["passivo_circulante"].replace(0, pd.NA)
    saldos["liquidez_corrente"] = saldos["ativo_circulante"] / circulante

    acoes = saldos["acoes_on"].fillna(0) + saldos["acoes_pn"].fillna(0)
    tesouraria = saldos["tesouraria_on"].fillna(0) + saldos["tesouraria_pn"].fillna(0)
    sem_acoes = saldos["acoes_on"].isna() & saldos["acoes_pn"].isna()
    saldos["acoes_em_circulacao"] = (acoes - tesouraria).where(~sem_acoes)

    return saldos[
        [
            "cd_cvm",
            "tipo",
            "dt_refer",
            "patrimonio_liquido",
            "ativo_total",
            "divida_liquida",
            "divida_liquida_sem_arrendamento",
            "liquidez_corrente",
            "acoes_em_circulacao",
        ]
    ]


def _rotulo(dt_fim: pd.Series) -> pd.Series:
    """ "2T26", como o mercado chama. Pelo trimestre civil do fim do periodo."""
    datas = pd.to_datetime(dt_fim)
    return datas.dt.quarter.astype(str) + "T" + datas.dt.strftime("%y")
