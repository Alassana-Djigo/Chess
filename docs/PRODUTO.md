# Produto: enciclopédia de estatísticas de xadrez

Decisões de Outubro de 2026. Num chat novo, pede para ler este ficheiro no GitHub.

## Âmbito
- Jogadores **activos** em destaque. Inactivos e históricos (Fischer, Kasparov) ficam numa secção própria, "Todos os tempos", e não aparecem nas listas principais.
- Presencial: rating FIDE clássico, rápido e blitz, e partidas presenciais.
- Online (Chess.com e Lichess): só rápido e blitz. O clássico online não se joga. O bullet fica guardado, fora das vistas principais (a decidir).
- Filtros em todo o lado: ritmo (clássico, rápido, blitz) × modo (presencial, online) × jogador × período.
- Recordes e curiosidades (lista aberta): partidas mais rápidas e mais longas do mundo, maior rating de sempre, vitórias, empates e derrotas entre dois jogadores, e mais.

## Visual
- Transmissão desportiva, paleta Marfim e ébano, retratos, peças a mover, animações com razão de ser.
- Confronto (VS) entre dois jogadores como ecrã-modelo, com carregamento por cavalo a saltar.

## Limites dos dados
- Chess.com: cache de até 12 h, por isso nada de tempo real. Tempo real vem da Lichess e dos torneios presenciais.
- Titled Tuesday: a API pode não o listar pelo nome. Verificar na primeira chamada real.

## Trabalho técnico que isto exige
- (feito) Guardar o estado activo/inactivo da FIDE (o campo `flag`).
- Jogadores históricos que já não constam das listas actuais (Fischer, Kasparov): fonte a escolher. A OlimpBase tem listas desde os anos 70; ver os termos de uso antes.
- (feito) Ecrã de confronto entre dois jogadores (`/confronto/`), com o visual aprovado. Falta o carregamento com progresso real e as fotografias.
- Guardar o número de lances de cada partida, para os recordes de duração.
- Escolher a fonte das partidas presenciais e dos jogadores históricos.
