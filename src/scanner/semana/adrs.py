"""ADRs de empresas brasileiras -> empresa da CVM, escrito a mao.

NUNCA se liga por prefixo de ticker (o emissor "EMBR" na B3 e a EMBRAST, nao a
Embraer; o ADR da Embraer e EMBJ). A lista saiu da lista de tickers da SEC
(`company_tickers_exchange.json`, NYSE e Nasdaq), levantada em 17/10/2026, e cada
ADR foi ligado a empresa pelo cadastro da CVM (`empresas`) no banco, por CNPJ.
Empresa com ADR que nao esta aqui nao tem balanco "confirmado" (so "provavel").
"""

from __future__ import annotations

from typing import NamedTuple


class Adr(NamedTuple):
    cd_cvm: int
    cnpj: str
    empresa: str


ADRS: dict[str, Adr] = {
    "PBR": Adr(9512, "33000167000101", "Petrobras"),
    "ITUB": Adr(19348, "60872504000123", "Itaú Unibanco"),
    "VALE": Adr(4170, "33592510000154", "Vale"),
    "ABEV": Adr(23264, "07526557000100", "Ambev"),
    "BBD": Adr(906, "60746948000112", "Bradesco"),
    "SBS": Adr(14443, "43776517000180", "Sabesp"),
    "BSBR": Adr(20532, "90400888000142", "Santander Brasil"),
    "VIV": Adr(17671, "02558157000162", "Telefônica Brasil"),
    "EMBJ": Adr(20087, "07689002000189", "Embraer"),
    "SUZ": Adr(13986, "16404287000155", "Suzano"),
    "GGB": Adr(3980, "33611500000119", "Gerdau"),
    "TIMB": Adr(24929, "02421421000111", "TIM"),
    "UGP": Adr(18465, "33256439000139", "Ultrapar"),
    "CIG": Adr(2453, "17155730000164", "Cemig"),
    "SID": Adr(4030, "33042730000104", "CSN"),
    "AZUL": Adr(24112, "09305994000129", "Azul"),
    "BAK": Adr(4820, "42150391000170", "Braskem"),
    "BRBI": Adr(25860, "10739356000103", "BR Partners"),
    "LND": Adr(20036, "07628528000159", "BrasilAgro"),
}
