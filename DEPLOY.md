# StayKey — Guia Completo de Deploy

## Índice
1. [Estrutura do Projeto](#estrutura)
2. [Setup Local (Desenvolvimento)](#local)
3. [Deploy VPS Ubuntu](#vps)
4. [Deploy Docker](#docker)
5. [Deploy Render](#render)
6. [Deploy Railway](#railway)
7. [Variáveis de Ambiente](#variaveis)
8. [Migrations de Banco de Dados](#migrations)
9. [Melhorias Implementadas](#melhorias)

---

## 1. Estrutura do Projeto <a name="estrutura"></a>

```
staykey/
├── app/
│   ├── __init__.py            # Application Factory
│   ├── extensions.py          # SQLAlchemy, Migrate, CSRF, OAuth
│   ├── models/
│   │   ├── __init__.py
│   │   ├── base.py            # TimestampMixin (created_at, updated_at)
│   │   ├── user.py
│   │   ├── imovel.py          # Imovel + Grupo
│   │   └── reserva.py         # Reserva + Estadia
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── auth.py            # Login, OAuth, Cadastro, Recuperação de senha
│   │   ├── main.py            # Dashboard, Configurações, Finanças
│   │   ├── usuario.py         # Perfil + Excluir conta
│   │   ├── imoveis.py         # CRUD Imóveis e Grupos
│   │   └── reservas.py        # Reservas + Estadias
│   ├── services/
│   │   └── email_service.py   # Envio de e-mails isolado
│   ├── utils/
│   │   ├── auth.py            # Decorators de autenticação
│   │   ├── upload.py          # Upload seguro de arquivos
│   │   └── helpers.py         # Funções auxiliares
│   ├── templates/             # Seus HTMLs (não alterados)
│   └── static/                # CSS, JS, uploads
├── config/
│   ├── __init__.py
│   └── settings.py            # Dev / Prod / Test configs
├── migrations/                # Gerado pelo Flask-Migrate
├── logs/                      # Logs de produção
├── wsgi.py                    # Entry point Gunicorn
├── gunicorn.conf.py           # Config do Gunicorn
├── Dockerfile
├── docker-compose.yml
├── nginx.conf
├── Procfile                   # Render / Railway / Heroku
├── requirements.txt
├── .env.example
├── .gitignore
└── DEPLOY.md
```

---

## 2. Setup Local (Desenvolvimento) <a name="local"></a>

### Pré-requisitos
- Python 3.12+
- PostgreSQL rodando localmente (ou usar SQLite apenas para dev)

### Passo a passo

```bash
# 1. Clone o repositório
git clone https://github.com/seu_usuario/staykey.git
cd staykey

# 2. Crie e ative o ambiente virtual
python -m venv venv
source venv/bin/activate       # Linux/Mac
venv\Scripts\activate          # Windows

# 3. Instale as dependências
pip install -r requirements.txt

# 4. Configure as variáveis de ambiente
cp .env.example .env
# Edite o .env com seus dados reais

# 5. Inicialize as migrations
flask db init                  # apenas na primeira vez (cria a pasta migrations/)
flask db migrate -m "Initial migration"
flask db upgrade

# 6. Rode em desenvolvimento
flask run --debug
# Acesse: http://localhost:5000
```

---

## 3. Deploy VPS Ubuntu <a name="vps"></a>

### 3.1 — Preparar o servidor

```bash
# Conecte via SSH
ssh root@IP_DO_SEU_VPS

# Atualize o sistema
apt update && apt upgrade -y

# Instale dependências
apt install -y python3.12 python3.12-venv python3-pip \
               postgresql postgresql-contrib \
               nginx git curl

# Crie usuário dedicado (não rode como root!)
adduser staykey
usermod -aG sudo staykey
su - staykey
```

### 3.2 — Configurar PostgreSQL

```bash
# Crie o banco e usuário
sudo -u postgres psql <<EOF
CREATE USER staykey_user WITH PASSWORD 'senha_muito_segura_aqui';
CREATE DATABASE staykey_db OWNER staykey_user;
GRANT ALL PRIVILEGES ON DATABASE staykey_db TO staykey_user;
EOF
```

### 3.3 — Deploy da aplicação

```bash
# Clone o projeto
cd /home/staykey
git clone https://github.com/seu_usuario/staykey.git
cd staykey

# Ambiente virtual
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Variáveis de ambiente
cp .env.example .env
nano .env   # Preencha todos os valores

# Migrations
flask db upgrade

# Teste antes de configurar serviços
gunicorn wsgi:app -c gunicorn.conf.py
# Ctrl+C para parar
```

### 3.4 — Configurar systemd (manter rodando 24h)

```bash
# Crie o arquivo de serviço
sudo nano /etc/systemd/system/staykey.service
```

Conteúdo do arquivo:

```ini
[Unit]
Description=StayKey Flask App
After=network.target postgresql.service

[Service]
User=staykey
WorkingDirectory=/home/staykey/staykey
EnvironmentFile=/home/staykey/staykey/.env
ExecStart=/home/staykey/staykey/venv/bin/gunicorn wsgi:app -c gunicorn.conf.py
Restart=always
RestartSec=10

# Logs via journald
StandardOutput=journal
StandardError=journal
SyslogIdentifier=staykey

[Install]
WantedBy=multi-user.target
```

```bash
# Ative e inicie
sudo systemctl daemon-reload
sudo systemctl enable staykey
sudo systemctl start staykey
sudo systemctl status staykey   # Verifique se está "active (running)"
```

### 3.5 — Configurar Nginx

```bash
# Copie a config
sudo cp /home/staykey/staykey/nginx.conf /etc/nginx/sites-available/staykey

# Edite e substitua "server_name _" pelo seu domínio
sudo nano /etc/nginx/sites-available/staykey

# Ative o site
sudo ln -s /etc/nginx/sites-available/staykey /etc/nginx/sites-enabled/
sudo nginx -t               # Valide a config
sudo systemctl reload nginx
```

### 3.6 — SSL com Certbot (HTTPS gratuito)

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d seudominio.com -d www.seudominio.com
# Certbot edita o nginx.conf automaticamente

# Renovação automática (já configurada pelo certbot)
sudo certbot renew --dry-run
```

### 3.7 — Atualizar a aplicação no futuro

```bash
cd /home/staykey/staykey
git pull origin main
source venv/bin/activate
pip install -r requirements.txt     # Se dependências mudaram
flask db upgrade                    # Se há novas migrations
sudo systemctl restart staykey
```

---

## 4. Deploy Docker <a name="docker"></a>

```bash
# 1. Configure o .env
cp .env.example .env
# Edite com seus valores

# 2. Suba todos os serviços
docker compose up --build -d

# 3. Verifique
docker compose ps
docker compose logs web

# 4. Parar
docker compose down

# Atualizar após mudanças
docker compose up --build -d --force-recreate
```

---

## 5. Deploy Render <a name="render"></a>

1. Faça push do código para o GitHub
2. Acesse https://render.com → "New Web Service"
3. Conecte o repositório
4. Configurações:
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn wsgi:app -c gunicorn.conf.py`
5. Crie um **PostgreSQL** no Render e copie a `DATABASE_URL`
6. Em "Environment Variables", adicione todas as variáveis do `.env.example`
7. Clique em Deploy

O `Procfile` contém `release: flask db upgrade` — o Render executa isso automaticamente antes de iniciar o servidor.

---

## 6. Deploy Railway <a name="railway"></a>

```bash
# Instale o CLI
npm install -g @railway/cli
railway login

# Na raiz do projeto
railway init
railway add postgresql     # Adiciona banco automático

# Deploy
railway up

# Variáveis de ambiente
railway variables set SECRET_KEY=valor GOOGLE_CLIENT_ID=valor ...
```

---

## 7. Variáveis de Ambiente <a name="variaveis"></a>

| Variável | Obrigatória | Descrição |
|---|---|---|
| `SECRET_KEY` | ✅ | Chave secreta Flask (gere com `python -c "import secrets; print(secrets.token_hex(32))"`) |
| `DATABASE_URL` | ✅ | `postgresql://user:pass@host:5432/db` |
| `FLASK_ENV` | ✅ | `production` ou `development` |
| `GOOGLE_CLIENT_ID` | ✅ | ID do app Google OAuth |
| `GOOGLE_CLIENT_SECRET` | ✅ | Secret do app Google OAuth |
| `EMAIL_REMETENTE` | ✅ | E-mail Gmail remetente |
| `EMAIL_SENHA` | ✅ | Senha de app Gmail (não a senha normal) |
| `SESSION_COOKIE_SECURE` | — | `True` em produção com HTTPS |
| `MAX_CONTENT_LENGTH` | — | Tamanho máximo upload em bytes (padrão: 5MB) |

### Gerar SECRET_KEY segura

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### Criar senha de app Gmail
1. Ative verificação em 2 etapas na conta Google
2. Acesse: https://myaccount.google.com/apppasswords
3. Crie uma senha para "Outro aplicativo"
4. Use essa senha em `EMAIL_SENHA`

---

## 8. Migrations de Banco de Dados <a name="migrations"></a>

```bash
# Inicializar (apenas uma vez, na criação do projeto)
flask db init

# Criar migration após alterar modelos
flask db migrate -m "Descreva a mudança aqui"

# Aplicar migrations
flask db upgrade

# Ver histórico
flask db history

# Reverter última migration
flask db downgrade
```

---

## 9. Melhorias Implementadas <a name="melhorias"></a>

### Arquitetura
- **Application Factory** — app criado via `create_app()`, permite múltiplas instâncias e testes isolados
- **Blueprints** — rotas separadas por domínio (`auth`, `main`, `usuario`, `imoveis`, `reservas`)
- **Separação de responsabilidades** — models / routes / services / utils completamente isolados

### Segurança
- ❌ **Nenhuma credencial hardcoded** — todas em variáveis de ambiente
- **CSRF protection** via Flask-WTF em todos os formulários POST
- **Hashing de senha** com Werkzeug (senha nunca exposta, setter com hash automático)
- **Upload validado** — extensão verificada, nome sanitizado, prefixo aleatório (evita colisão e adivinhação)
- **Cabeçalhos de segurança** — `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`
- **Session segura** — `SESSION_COOKIE_SECURE=True` em produção (HTTPS only)

### Banco de Dados
- **PostgreSQL** no lugar de SQLite — pronto para múltiplos usuários simultâneos
- **Flask-Migrate/Alembic** — versionamento do schema, zero downtime em updates
- **Índices** em todas as FK e campos de busca frequente
- **TimestampMixin** — `created_at` e `updated_at` automáticos em todos os modelos
- **Pool de conexões** — `pool_pre_ping`, `pool_recycle`, `pool_size` configurados
- **CASCADE correto** — deleção em cascata configurada tanto no SQLAlchemy quanto no PostgreSQL

### Performance
- **Gunicorn** com fórmula de workers `(2 × CPUs) + 1`
- **Nginx** servindo arquivos estáticos diretamente (sem passar pelo Python)
- **preload_app=True** no Gunicorn — app carregado uma vez, workers via fork
- **Logs rotativos** — `RotatingFileHandler` evita disco cheio em produção

### Deploy
- **Dockerfile** multi-stage com usuário não-root
- **docker-compose.yml** com PostgreSQL + Nginx + healthchecks
- **Procfile** para Render/Railway com `release: flask db upgrade`
- **systemd service** para VPS Ubuntu com restart automático
- **Certbot/Let's Encrypt** para HTTPS gratuito
