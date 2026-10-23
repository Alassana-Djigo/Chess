# Decisões de produto e de arquitectura

Registo curto do que ficou decidido, para não se perder em conversas.

## Produto

| # | Decisão | Notas |
| - | ------- | ----- |
| D1 | **Tempo real com o mesmo peso** para torneios presenciais e partidas online. | Presencial: Broadcasts da Lichess. Online: Lichess TV e streaming de partidas. A PubAPI da Chess.com não é tempo real, por isso serve perfis, ratings e histórico. |
| D2 | **Sem odds.** Só estatísticas e probabilidades. | Mostrar sempre três números: vitória, empate e derrota. Em clássico o empate pesa muito. Base: expectativa de pontuação pelo Elo, avaliação do motor e taxa histórica de empates entre os dois jogadores. |
| D3 | **Identidade visual: paleta A, "Marfim e ébano"**, duas cores como um tabuleiro. | Ver tokens abaixo. |

## Identidade visual (tokens)

| Token | Valor | Uso |
| ----- | ----- | --- |
| `--square-light` | `#EDE6D6` | Casas claras, fundos claros |
| `--square-dark` | `#2B2B30` | Casas escuras, fundos escuros, texto principal |
| `--accent` | `#C8A24A` | Destaque. Reservado ao que está **ao vivo** e ao estado activo |

Não copiar o aspecto da Chess.com (verde e creme) nem o castanho clássico da Lichess: a
Chess.com pede que as ferramentas sejam claramente diferentes em aspecto e nome.

## Arquitectura (proposta, a confirmar na Fase 1)

- Back-end: Django + PostgreSQL, com Django REST Framework.
- Ingestão: Celery + Redis, **uma fila em série por fornecedor** (a Chess.com pede pedidos
  em série e a Lichess um pedido de cada vez por token). O browser nunca chama APIs
  externas, só a nossa API.
- Tempo real: Django Channels (WebSocket).
- Front-end separado: React/Next.js com TypeScript. Confirmar licenças das bibliotecas de
  tabuleiro (a Chessground é GPL).
- Ideia central: **identidade unificada do jogador** (FIDE ID, conta Lichess, conta Chess.com).

## Pendentes

- Nome do produto.
- Idioma da interface (hoje `en-us` por defeito do Django).
- Licença do código.
