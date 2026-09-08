# Desenho da interface

Arquivos-fonte do canvas de design. Cada `.dc.html` e uma tela; `canvas.json`
posiciona as telas e guarda as notas. Sao estes arquivos que se editam para
mudar o desenho -- o HTML montado a partir deles nao e versionado.

## Direcao

A referencia que originou o desenho e um dashboard claro e arejado. A secao 6 do
plano manda o oposto: escuro por padrao, densidade de terminal. Onde as duas
brigaram, o plano ganhou -- da referencia veio a estrutura (sidebar, cards de
metrica, painel de detalhe lateral, hierarquia tipografica), nao a paleta.

## Regras de cor

- **Verde e vermelho existem so para direcao de preco.** Nada mais no layout
  pode usar essas cores.
- **Ambar (#ffb020) e a cor de interface**: selecao, z-score, marcador de evento.
- Numerais tabulares em toda coluna numerica, senao as casas decimais dancam
  entre as linhas.
- **Azul (#7d9fe0) e a cor de indicador de grafico** -- so as bandas de
  Bollinger usam. Foi preciso um terceiro tom porque verde e vermelho estao
  presos a direcao e o ambar ao evento.

## Marcacao do evento no grafico

O candle do dia do evento fica inteiro ambar, pareando com a barra de volume
logo abaixo. O par de barras douradas marca o dia sem seta nem rotulo por cima.

O candle perde a cor de direcao nesse dia. Foi troca deliberada: a variacao
aparece no cabecalho e no painel de contexto, com sinal e cor.

## Tipografia

IBM Plex Sans para interface, IBM Plex Mono para numero.

## Dados

Os artboards usam numeros reais do banco: pregao de 14/08/2026, LWSA3 com
z 6,90. O grafico de candles e o historico verdadeiro do papel.
