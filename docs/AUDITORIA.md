# Auditoria do repositório (Fase 0)

Estado analisado: branch `main`, 9 commits, ~490 linhas de Python em 5 apps Django.
Verificado com o código a correr: o projecto arranca, as migrações estavam em dia com os
models e `manage.py check` não reportava problemas.

## 1. Segurança

| # | Problema | Gravidade | Estado |
| - | -------- | --------- | ------ |
| S1 | Uma palavra-passe real de PostgreSQL foi commitada em `.env.example` (commit `feacd56`) e só substituída no commit `9626ed3`. **Continua visível no histórico do repositório público.** | Alta | Acção do autor: confirmar que essa palavra-passe foi mudada em todos os sítios onde foi usada. Apagar o ficheiro não adianta, porque o histórico é público. |

Reescrever o histórico (`git filter-repo`) é opcional e só esconde o rasto: a palavra-passe
deve ser considerada comprometida de qualquer forma. O `.env` real nunca foi commitado.

## 2. Bugs (corrigidos na Fase 0)

| # | Problema | Correcção |
| - | -------- | --------- |
| B1 | `HistoryRatingAdmin.search_fields = ['player', 'rating']`: pesquisar no admin dava `FieldError` (uma FK não aceita `icontains`). | `['player__name', 'player__id_fide']`. Teste de regressão incluído. |
| B2 | `TournamentAdmin.list_filter = ['name', ...]`: filtrar por nome gera um filtro com um valor por torneio. | `['formate', 'start_date']`. |

## 3. Higiene (corrigida na Fase 0)

| # | Problema | Correcção |
| - | -------- | --------- |
| H1 | Dois ficheiros de dependências: `requeirements.txt` (com gralha, o completo, com `requests`) e `requirements.txt` (incompleto). | Um só `requirements.txt` completo, mais `requirements-dev.txt`. |
| H2 | `.gitignore` com barras invertidas e quase vazio. | Reescrito (Python, Django, segredos, editores, dados locais). |
| H3 | README vazio. | README com arranque, qualidade, roadmap e fontes de dados. |
| H4 | `ALLOWED_HOSTS = []` fixo: impossível fazer deploy sem editar código. | `ALLOWED_HOSTS` e `CSRF_TRUSTED_ORIGINS` vêm do ambiente. |
| H5 | `.env.example` com `SECRET_KEY=123` e utilizador de uma máquina pessoal. | Valores de exemplo seguros, alinhados com o `docker-compose.yml`. |
| H6 | Sem testes, sem CI, sem lint, sem ambiente reprodutível. | Testes, ruff, GitHub Actions e `docker-compose.yml`. |

## 4. Desenho dos models (decisões para a Fase 1)

Não alterei estes pontos na Fase 0 de propósito: mudam a estrutura da base de dados e devem
ser decididos em conjunto. Como só existe a migração `0001` por app, **agora é o momento
mais barato para os corrigir**.

| # | Problema | Porque importa | Proposta |
| - | -------- | -------------- | -------- |
| M1 | `Jogador.date_birth` é um `DateField` obrigatório. | A lista da FIDE traz só o ano de nascimento: importar obrigaria a inventar dias e meses. | `birth_year` (inteiro, opcional). |
| M2 | `federation` com 80 caracteres. | A FIDE usa códigos de 3 letras. | Guardar o código; o nome do país vem de uma tabela. |
| M3 | Um só campo `title`. | A FIDE tem título aberto e título feminino separados; um GM pode ser também WGM. | `title` e `women_title`. |
| M4 | Nomes misturados: `Jogador` (PT) com `Match`, `Tournament` (EN); `formate`, `local`, `Rhythm`. | Confunde quem lê e quem escreve a API. | `Player`, `format`, `venue`, `TimeControl`. |
| M5 | Não há onde guardar contas de Lichess ou Chess.com. | É o núcleo do produto: o mesmo jogador tem várias identidades. | Modelo `PlayerAccount(player, plataforma, username, id_externo)`. |
| M6 | `HistoryRating` sem `source` nem restrição de unicidade. | Rating FIDE, Lichess e Chess.com são escalas diferentes: sem `source` um gráfico mistura-as. Sem unicidade, reimportar duplica linhas. | Campo `source` e `unique(player, source, time_control, rating_date)`. |
| M7 | `Match` sem lances (PGN), abertura, ratings no momento da partida, ronda, mesa, estado nem origem. | Sem isto não há estatísticas, tempo real nem forma de evitar duplicados ao importar. | `pgn`, `eco`, `white_elo`, `black_elo`, `round`, `status`, `source` + `external_id` (único). |
| M8 | `outcome` não tem "em curso". | O tempo real precisa de `*`. | Acrescentar `*` ou um campo `status`. |
| M9 | Só 4 ritmos (`B`, `R`, `C`, `BL`), data sem hora. | Um 3+2 e um 5+0 são ambos "blitz", e a ordem das partidas no dia perde-se. | Guardar base e incremento, e data e hora de início. |
| M10 | `Tournament` sem origem, rondas, estado, `end_date` opcional. | Torneios em curso ainda não têm data de fim. | `source`/`external_id`, `status`, `end_date` opcional. |
| M11 | Sem `CheckConstraint` (branco diferente de preto) nem índices. | Dados inválidos entram; consultas por data e jogador ficam lentas. | Constraint e índices em `date`, `tournament`, `player`. |
| M12 | `name` com 50 caracteres. | Curto para nomes completos. | 100 ou mais. |

## 5. O que fica para depois

- Comando `import_fide_players`: hoje é um esqueleto que só escreve uma mensagem. Implementa-se
  na Fase 1, depois de fechar M1 a M3.
- Django REST Framework, Celery, Redis, Channels e o front-end: Fases 1 a 3.

## 6. Resolução (Fase 1, passo 1)

| # | Estado | O que foi feito |
| - | ------ | --------------- |
| M1 | Feito | `birth_year` opcional, validado entre 1900 e 2100. |
| M2 | Parcial | `federation` guarda o código de 3 letras, validado. A tabela com os nomes dos países fica para mais tarde. |
| M3 | Feito | `title` e `women_title`; vazio significa sem título. |
| M4 | Feito | `Player`, `fide_id`, `format`, `venue`, `TimeCategory`. |
| M5 | Feito | `PlayerAccount` (plataforma + username, único sem distinguir maiúsculas de minúsculas). |
| M6 | Feito | `HistoryRating.source` e unicidade por (jogador, origem, categoria, data). |
| M7 | Feito | `pgn`, `eco`, `opening`, `white_elo`, `black_elo`, `round`, `board`, `source` e `external_id` (único por origem). |
| M8 | Feito | `outcome` aceita `*` (em curso), que passa a ser o valor por defeito. |
| M9 | Feito | `time_base` e `time_increment` (segundos) mais `time_category`; `date` e `started_at`. |
| M10 | Feito | `Tournament` com `source`, `external_id`, `status`, `rounds` e `end_date` opcional. |
| M11 | Feito | Constraints (jogadores diferentes, fim não anterior ao início) e índices por data e jogador. |
| M12 | Feito | `name` com 150 caracteres. |

Notas:

- `Tournament.prize` passou a ser opcional (desconhecido é diferente de zero) e não regista a moeda.
- `Match.location` passou a `Match.venue` e já não aceita NULL.
- `core.timecontrol.categorize_time_control` classifica um relógio pela convenção da Lichess
  (duração estimada = base + 40 x incremento; limites de 180, 480 e 1500 segundos). A Chess.com e a
  FIDE traçam as fronteiras de forma diferente, por isso os importadores devem preferir a
  categoria que a própria fonte indica.
- Corrigido o plural no admin ("Matchs" passa a "Matches").

## 7. Resolução (Fase 1, passo 2)

O comando `import_fide_players` deixou de ser um esqueleto. Lê a lista mensal da FIDE (ZIP ou XML,
descarregada ou local) e grava os jogadores (`fide_id`, nome, federação, ano de nascimento e
títulos) e os ratings clássico, rápido e blitz em `HistoryRating`, com origem `fide`.

- Leitura em fluxo: a memória não cresce com o tamanho do ficheiro (cerca de 70 MB num teste
  sintético com 300 000 jogadores).
- Repetível: correr duas vezes com os mesmos dados não cria nada de novo.
- Os campos `sex` e `flag` (inactivo) da FIDE não são guardados, porque o modelo ainda não tem
  onde os pôr.
- O mês da lista não vem dentro do ficheiro: usa-se `--period` ou o mês actual.

## 8. Resolução (Fase 1, passo 3)

O comando `sync_lichess` liga uma conta da Lichess a um jogador (por FIDE ID, por id da base de
dados, pelo FIDE ID que o utilizador publicou na Lichess, ou criando o jogador) e importa os
ratings e as partidas recentes.

- Os adversários que ainda não existem na base ficam como jogadores mínimos (nome igual ao
  utilizador da Lichess) com a respectiva conta, para se poderem juntar a uma pessoa real mais tarde.
- Só entram partidas classificadas de xadrez standard em bullet, blitz, rapid e clássico. Ficam de
  fora as partidas contra o computador ou anónimos, as variantes, o ultra-bullet e o jogo por
  correspondência.
- Sem token, a Lichess devolve o histórico de ratings em cache ou vazio. O rating actual de cada
  categoria é sempre gravado com a data de hoje.
- Para a fase do tempo real: os endpoints de Broadcasts (torneios presenciais) exigem um token com
  a permissão `study:read`.

## 9. Resolução (Fase 1, passo 4)

A ficha do jogador (`/players/<id>/`), a pesquisa e a página inicial são as primeiras páginas do
site. A lógica de consulta (`web/services.py`) está separada das vistas e do gráfico
(`web/charts.py`), e tem testes próprios.

- O número de consultas à base de dados da ficha não cresce com o número de partidas (há um teste
  que o garante).
- Os adversários criados pela importação da Lichess aparecem como jogadores com o nome de
  utilizador, até serem ligados a uma pessoa real.
- `Player.display_name` mostra «Magnus Carlsen» para o nome «Carlsen, Magnus» da FIDE; o nome
  guardado não muda.
