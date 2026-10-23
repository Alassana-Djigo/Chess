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
