# Chess

Plataforma de estatísticas e probabilidades de xadrez, no espírito dos grandes sites de
estatísticas desportivas (futebol, basquetebol), para comentadores, streamers e quem
acompanha xadrez com olhar analítico. Mostra probabilidades e estatísticas; **não mostra odds**.

> Estado: **Fase 1 em curso**. Já existem a importação da lista da FIDE, a ligação a contas da
> Lichess e a primeira página (a ficha do jogador). Ainda não há tempo real. Ver o
> [roadmap](#roadmap), [docs/DECISOES.md](docs/DECISOES.md) e [docs/AUDITORIA.md](docs/AUDITORIA.md).

## Stack

- Python 3.12 ou superior (CI e desenvolvimento em 3.14), Django 5.2
- PostgreSQL (psycopg 3), configuração por variáveis de ambiente (django-environ)
- Qualidade: ruff (lint e formatação), testes do Django, CI no GitHub Actions
- Planeado: Django REST Framework, Celery + Redis, WebSockets (Channels) e um front-end
  separado em React/Next.js

## Arrancar em local

### 1. Código e ambiente Python

```bash
git clone git@github.com:Alassana-Djigo/Chess.git
cd Chess

python3 -m venv venv
source venv/bin/activate           # Windows (PowerShell): venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt

cp .env.example .env               # Windows: copy .env.example .env
```

Edita o `.env` e define uma `SECRET_KEY` (o comando para a gerar está no próprio ficheiro).

### 2. Base de dados (escolhe uma opção)

**Opção A, Docker.** Os valores do `.env.example` já combinam com o `docker-compose.yml`:

```bash
docker compose up -d               # PostgreSQL e Redis em segundo plano
```

**Opção B, PostgreSQL instalado (Ubuntu/WSL):**

```bash
sudo apt install -y postgresql
sudo service postgresql start      # no WSL tens de o arrancar em cada sessão
sudo -u postgres psql
```

Dentro do `psql`, usa uma senha sem símbolos e põe-na no `DATABASE_URL` do `.env`:

```sql
CREATE ROLE chess LOGIN CREATEDB PASSWORD 'uma-senha-sem-simbolos';
CREATE DATABASE chess OWNER chess;
```

O `CREATEDB` é necessário porque o Django cria uma base temporária para os testes.

### 3. Arrancar

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver         # http://127.0.0.1:8000/admin/
```

## O site

Depois de importar jogadores (e, se quiseres, de ligar uma conta da Lichess), arranca o servidor
com `python manage.py runserver` e abre http://127.0.0.1:8000/:

| Página | Endereço | O que mostra |
| ------ | -------- | ------------ |
| Início | `/` | Os melhores ratings clássicos da FIDE, na lista mais recente importada. |
| Pesquisa | `/players/?q=carlsen` | Jogadores por nome (em qualquer ordem) ou por FIDE ID. |
| Ficha do jogador | `/players/<id>/` | Ratings por fonte e ritmo com gráfico, resultados (total, por cor e por ritmo), forma recente, aberturas mais jogadas e partidas recentes. |

O gráfico escolhe-se pelos separadores de rating (`?source=lichess&category=blitz`). As páginas são
geradas pelo Django, sem JavaScript, e seguem o modo claro ou escuro do sistema.

## Importar jogadores da FIDE

A FIDE publica todos os meses a lista de ratings (um ZIP com um XML grande). O comando lê-a em
fluxo, sem a carregar toda para a memória, e grava os jogadores e os ratings clássico, rápido
e blitz:

    python manage.py import_fide_players --min-rating 2500
    python manage.py import_fide_players --file lista.zip --period 2026-10

| Opção | Efeito |
| ----- | ------ |
| `--file` | ZIP ou XML local. Sem ela, descarrega a lista actual para `data/` (pasta ignorada pelo Git). |
| `--period` | Mês a que a lista pertence, como `2026-10`. Por defeito, o mês actual. |
| `--min-rating` | Só importa jogadores com pelo menos um rating igual ou superior. |
| `--limit` | Pára depois de importar este número de jogadores (para testes rápidos). |

É seguro repetir o comando: não duplica nada e actualiza o que mudou, e cada mês fica com o seu
próprio histórico de ratings. O mês não vem dentro do ficheiro, por isso o comando usa o mês
actual ou o `--period` que indicares. Se o download falhar, descarrega o ficheiro em
https://ratings.fide.com/download_lists.phtml e usa `--file`.

## Ligar contas da Lichess

O comando liga uma conta da Lichess a um jogador e importa os ratings e as partidas recentes:

    python manage.py sync_lichess NomeNaLichess --fide-id 5000001
    python manage.py sync_lichess NomeNaLichess
    python manage.py sync_lichess NomeNaLichess --create

Para saber a que jogador a conta pertence, o comando usa, por esta ordem: a conta já ligada, o
jogador indicado com `--fide-id` ou `--player-id`, o FIDE ID que o próprio utilizador publicou
na Lichess (se esse jogador já foi importado da FIDE) e, só com `--create`, um jogador novo.

| Opção | Efeito |
| ----- | ------ |
| `--fide-id`, `--player-id` | Liga ao jogador com esse FIDE ID ou id da base de dados. |
| `--create` | Cria o jogador se não encontrar nenhum. |
| `--max-games` | Quantas partidas recentes importar (por defeito, 30). |
| `--no-games`, `--no-ratings` | Salta as partidas ou os ratings. |

Entram as partidas classificadas de xadrez standard em bullet, blitz, rapid e clássico. Ficam de
fora as partidas contra o computador ou contra anónimos, as variantes, o ultra-bullet e o jogo por
correspondência. Os adversários que ainda não existem ficam como jogadores mínimos, com o nome de
utilizador da Lichess, para se poderem juntar a uma pessoa real mais tarde. É seguro repetir o
comando.

Sem autenticação, a Lichess devolve uma cópia em cache do histórico de ratings, ou nada. Para o
histórico completo, cria um token pessoal (Preferences, API access tokens) e põe-no no `.env` como
`LICHESS_API_TOKEN`. Sem histórico, o rating actual de cada categoria é gravado na mesma, com a
data de hoje. Se a Lichess responder com um limite de pedidos (429), o comando espera um minuto
e tenta outra vez.

## Qualidade

```bash
ruff check .                       # lint
ruff format .                      # formatar
python manage.py test              # testes
python manage.py makemigrations --check --dry-run   # migrações em dia com os models
```

O CI corre exactamente isto, contra um PostgreSQL, em cada pull request e em cada push ao `main`.

## Estrutura

| App               | Responsabilidade                                      |
| ----------------- | ----------------------------------------------------- |
| `config`          | Configuração do projecto (settings, urls, wsgi/asgi)  |
| `core`            | Partes comuns (ex.: ritmos de jogo)                   |
| `player`          | Jogadores e importação da lista FIDE                  |
| `matches`         | Partidas                                              |
| `tournaments`     | Torneios                                              |
| `history_rating`  | Histórico de ratings                                  |
| `providers`       | Clientes das fontes externas (Lichess); pacote simples, sem models |
| `web`             | Páginas do site: início, pesquisa e ficha do jogador  |

## Roadmap

0. **Fundação** (feito): limpeza, ambiente reprodutível, testes, CI, auditoria dos models.
1. **Dados** (em curso): esquema unificado, importação da lista FIDE, ligação a contas da
   Lichess e ficha do jogador (feitos); falta a Chess.com.
2. **Estatísticas**: head-to-head, aberturas, replay animado de partidas.
3. **Tempo real**: Lichess TV e Broadcasts, WebSocket, tabuleiro animado com barra de avaliação.
4. **Torneios e probabilidades**: classificações, previsões, comparador.
5. **Produto**: contas, alertas, cache, deploy.

## Fontes de dados

- **Lichess**: partidas, Broadcasts (torneios presenciais), TV, explorador de aberturas, tablebase.
- **Chess.com (PubAPI)**: perfis, ratings e arquivos de partidas. Não é tempo real e
  pede pedidos em série.
- **FIDE**: listas mensais de ratings em XML (não há API REST oficial conhecida).

Antes de qualquer uso comercial, rever os termos de cada fonte. A Chess.com, por exemplo,
exige que as ferramentas se distingam claramente dos produtos dela em aspecto e nome.

## Segredos

O `.env` nunca vai para o Git (está no `.gitignore`). Só o `.env.example`, com valores de
exemplo, é versionado.
