# Fixtures da CVM

CSVs reais, recortados dos zips baixados de `dados.cvm.gov.br` em 17/09/2026:
`itr_cia_aberta_2026.zip`, `dfp_cia_aberta_2025.zip` e `cad_cia_aberta.csv`.
Mesma codificacao do original (`latin-1`, separador `;`), so com as linhas
necessarias aos testes.

Como foi feito: cada CSV do zip foi lido com `csv.DictReader` e filtrado por
`CNPJ_CIA` (ou `CD_CVM`, no cadastro) das quatro empresas abaixo, mais o codigo
de conta (`CD_CONTA`) de cada campo que `cvm.py` extrai. O cabecalho e a ordem
das colunas sao os do arquivo original.

Empresas no recorte:

- **Unipar** (CNPJ `33.958.695/0001-78`, CD_CVM 11592): layout geral,
  consolidado. ITR 2026-03-31, ITR 2026-06-30 e DFP 2025-12-31. E a empresa do
  teste de aceite (secao 7 da spec) -- os valores batem com a tabela la.
- **Itau Unibanco Holding** (CNPJ `60.872.504/0001-23`, CD_CVM 19348): layout
  financeiro (a DRE traz "Receitas da Intermediacao Financeira" em 3.01). ITR
  2026-06-30. So a PL (2.08), lucro (3.09) e caixa (1.01, que no layout
  financeiro faz o papel do circulante) -- os campos "geral:" ficam de fora de
  proposito.
- **Armac Locacao** (CNPJ `00.242.184/0001-04`, CD_CVM 26069): o documento com
  **2 versoes** no indice do ITR 2026-06-30 (v1 recebida 2026-08-11, v2
  2026-08-12). So os campos minimos (receita, ativo total, passivo circulante,
  PL) para o documento aparecer em `documentos`/`resultados`/`balancos`.
- **Concessionaria Rota de Santa Maria** (CNPJ `41.886.692/0001-02`, CD_CVM
  27294): so tem ITR **individual** (nao aparece em nenhum arquivo `_con_`
  desta data) e o lucro (conta 3.11) nao tem conta filha com "controladora" na
  descricao -- e o caso de `lucro_controladores == lucro_liquido`.

Cada arquivo de contas (DRE/DVA/BPA/BPP) so tem `ORDEM_EXERC` igual a
`ÚLTIMO`; a excecao e a Unipar na DRE, onde uma linha `PENÚLTIMO` (o
comparativo do ano anterior) foi mantida de proposito, para o teste que
confere que ela e ignorada.

O caso de `ESCALA_MOEDA == 'UNIDADE'` (que nao multiplica por 1000) nao esta
aqui: nenhuma empresa do recorte reporta em unidade, entao o teste
correspondente fabrica a linha na hora, dentro do proprio arquivo de teste.
