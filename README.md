# Chess

Plataforma de estatísticas e probabilidades de xadrez, no espírito dos grandes sites de
estatísticas desportivas (futebol, basquetebol), para comentadores, streamers e quem
acompanha xadrez com olhar analítico. Mostra probabilidades e estatísticas; **não mostra odds**.

> Estado: **Fase 0 concluída** (fundação do projecto). Ainda não há páginas públicas nem
> integrações com APIs. Ver o [roadmap](#roadmap), [docs/DECISOES.md](docs/DECISOES.md) e [docs/AUDITORIA.md](docs/AUDITORIA.md).

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

## Roadmap

0. **Fundação** (feito): limpeza, ambiente reprodutível, testes, CI, auditoria dos models.
1. **Dados**: esquema unificado, identidade do jogador (FIDE + Lichess + Chess.com),
   importação da lista FIDE, primeiro adaptador de API, página de um jogador.
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
