"""Candles gatilho: candle + suporte + volume + contexto.

Lente separada do alerta de volume. Nao alimenta a regra de 6 sigma da secao 4 do
plano e nao muda nada nela. Cada camada e uma regra mecanica com nome, que o
usuario confere no grafico:

- `matrizes`: barras longas viram matrizes pregao x papel, com desdobramento e
  grupamento ajustados;
- `candles`: martelo, doji libelula, engolfo, piercing, estrela da manha e
  candle de forca;
- `contexto`: queda recente, tendencia de baixa, correcao em alta e volume;
- `niveis`: suporte e resistencia -- preco onde o preco bateu varias vezes e
  nao fechou alem, ate fechar alem.

Nada aqui olha o futuro: o estado de um dia so usa o que se sabia no fechamento
daquele dia.
"""
