# Filial 16

Projeto Django + PostgreSQL para gerenciar fila dinâmica de carregamentos (integração com n8n e Power Automate).

## Funcionalidades

- **Fila de carregamento**: template com abas por fluxo de XML (Pedágio, Harsco, Bemisa-Usiminas, etc.), cards de resumo e detalhe do item.
- **Model de XML**: campos padrão da NFe + `extras` (JSONField) para campos imprevisíveis vindos do XML.
- **Tema claro/escuro**: botão no header (ícones sol/lua) com preferência salva em `localStorage`.

## Requisitos

- Python 3.12+
- PostgreSQL 16 (ou use Docker)

## Variáveis de ambiente e produção

Todas as credenciais e configurações sensíveis vêm de variáveis de ambiente. O Django carrega o arquivo **`.env`** na raiz do projeto (via `python-dotenv`).

1. **Copie o exemplo e preencha com os valores reais:**
   ```bash
   cp .env.example .env
   ```
2. **Edite `.env`** e defina pelo menos:
   - `DJANGO_SECRET_KEY` – chave longa e aleatória (em produção use `openssl rand -base64 48` ou similar)
   - `DJANGO_DEBUG=0` em produção
   - `ALLOWED_HOSTS` e `CSRF_TRUSTED_ORIGINS` com seu domínio
   - `POSTGRES_*` e `MINIO_*` conforme seu ambiente
3. **Nunca commite `.env`** (já está no `.gitignore`). O `.env.example` pode ser commitado como modelo.

Em produção, use senhas fortes e um `SECRET_KEY` único.

## Desenvolvimento local

```bash
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
cp .env.example .env
# Ajuste .env (POSTGRES_HOST=localhost, etc.)
```

Depois:

```bash
python manage.py migrate
python manage.py runserver
```

## Docker (rede própria)

Rede `filial16` é criada automaticamente; os serviços `web` e `db` se comunicam por ela.

**Desenvolvimento (sem .env):**
```bash
docker compose up -d
```

**Produção (com .env):** crie `.env` a partir de `.env.example`, preencha e rode:
```bash
docker compose --env-file .env up -d
```

- App: http://localhost:8000  
- Admin: http://localhost:8000/admin/ (crie um superusuário com `python manage.py createsuperuser` dentro do container ou local)
- **MinIO** (armazenamento de arquivos/XMLs): API em http://localhost:9000, console em http://localhost:9001 (usuário `filial16`, senha `filial16minio`). O bucket `filial16` é usado pelo Django (`DEFAULT_FILE_STORAGE`); XMLs das NFe ficam no MinIO e o botão 📥 no card faz o download.

### MinIO na rede doméstica (n8n em outro PC)

O MinIO está exposto em `0.0.0.0:9000` e `0.0.0.0:9001`, então qualquer máquina na mesma rede pode acessar.

1. **Descubra o IP do PC onde roda o Docker** (ex.: `ipconfig` no Windows; use o IPv4 da rede local, ex. `192.168.1.100`).

2. **No n8n**, use como endpoint do MinIO:
   - **API (S3):** `http://IP:9000` (ex.: `http://192.168.1.100:9000`)
   - **Console (opcional):** `http://IP:9001` no navegador para criar o bucket e testar.
   - **Credenciais:** Access Key `filial16`, Secret Key `filial16minio`.

3. **Bucket e convenção para XML:**
   - Bucket: `filial16` (crie no console se não existir; o Django também pode criar automaticamente).
   - Para o download no card funcionar, suba o XML com a chave: **`carregamentos/{chave_acesso}-nfe.xml`**
   - Ex.: se a NFe tem `chave_acesso` = `35250612345678000199550010001234561123456789`, o objeto no MinIO deve ser `carregamentos/35250612345678000199550010001234561123456789-nfe.xml`.
   - Se o n8n usar outro path, envie no payload do carregamento o extra `xml_key` (ou `xml_minio_key` / `xml_path`) com o caminho exato no bucket.

4. **Firewall (Windows):** se outro PC não conseguir conectar, libere as portas 9000 e 9001 para entrada no firewall do host.

## Model Carregamento (XML)

Campos fixos: `chave_acesso`, `serie_nfe`, `nota_fiscal`, `datahora_emissao`, `emit_nome`, `emit_cnpj`, `dest_nome`, `dest_cnpj`, `xProd_produto`, `cfop`, `qCom_peso`, `vProd_valor`, `modFrete_tomador`, `nome_cnpj`, `transp_cnpj`.

- **extras** (JSONField): aceita qualquer estrutura; use para campos adicionais do XML (ex: `numero_lacre`, `codigo_balanca`, `campo_maluco_novo`).
- **fluxo**: identifica o fluxo de carregamento (aba).
- **arquivado**: para itens arquivados.

Exemplo de uso de `extras` no código:

```python
nota.extras = {
    "numero_lacre": "ABC123",
    "codigo_balanca": "007",
    "campo_maluco_novo": "qualquer coisa"
}
nota.save()
```

## Estrutura

- `filial16/` – settings, urls, WSGI
- `fila/` – app da fila (models, views, templates)
- `templates/base.html` – layout base com header e alternância de tema
- `static/fila/` – CSS e JS do tema

## GitHub

Projeto pronto para push: `.gitignore` e este README já estão configurados.
