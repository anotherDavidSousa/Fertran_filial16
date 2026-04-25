# Pesseus — Gerenciador de Fila de Carregamentos

Aplicação web para gestão de fila dinâmica de carregamentos em operação logística industrial, com ingestão e parsing de XML de NF-e via integrações por webhook.

## Visão Geral

O sistema recebe payloads de NF-e (Nota Fiscal Eletrônica) enviados por ferramentas de automação, processa os campos do XML e organiza os carregamentos em filas por fluxo de trabalho, exibidas em um dashboard com abas.

## Stack

| Camada | Tecnologia |
|---|---|
| Backend | Python 3.12 · Django 5 |
| Banco de dados | PostgreSQL 16 |
| Armazenamento | MinIO (compatível com S3) |
| Containerização | Docker · Docker Compose |
| Integração | n8n · Power Automate (webhooks) |
| Frontend | Django Templates · JavaScript |

## Funcionalidades

- **Dashboard por fluxo** — abas separadas por tipo de carregamento, com cards de resumo e visualização de detalhes
- **Modelo flexível de NF-e** — campos fixos para dados padrão da nota + coluna `JSONField` para acomodar variações de XML sem alterar o schema
- **Armazenamento de arquivos** — XMLs armazenados em object storage; botão de download direto no card
- **Tema claro/escuro** — alternância no header com preferência salva no navegador
- **Ingestão via webhook** — ferramentas externas de automação enviam os dados; a aplicação valida e enfileira

## Destaques Técnicos

- Modelo de dados híbrido: campos normalizados para consultas + `JSONField` para estruturas imprevisíveis, mantendo o schema estável independente das variações dos fornecedores.
- Todas as credenciais e configurações sensíveis são injetadas por variáveis de ambiente — nenhum segredo no código.
- Ambiente completo orquestrado via Docker Compose, incluindo banco de dados e object storage.
