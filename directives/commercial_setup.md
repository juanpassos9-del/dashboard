# Configuração do Ambiente Comercial (SOP)

Este documento descreve como preparar a infraestrutura para comercializar o seu Dashboard.

## 1. Configuração do Supabase (Obrigatório)

O Supabase será responsável por:
- Autenticação (Login e Senha dos seus clientes).
- Banco de Dados Real-time (Onde os dados do Profit serão armazenados).

### Passos:
1. Acesse [supabase.com](https://supabase.com/) e crie uma conta gratuita.
2. Crie um novo projeto chamado `ProfitDashboard`.
3. Vá em **Project Settings > API** e copie a `URL` e a `anon key`.
4. Salve essas informações no seu arquivo `.env` local:

```env
SUPABASE_URL=sua_url_aqui
SUPABASE_KEY=sua_chave_aqui
```

## 2. Estrutura do Banco de Dados

Crie uma tabela chamada `market_data` com as seguintes colunas:
- `symbol` (text, primary key): Ex: WINQ24, PETR4.
- `last_price` (float8).
- `change_percent` (float8).
- `updated_at` (timestamptz, default: now()).

## 3. Manutenção do Gateway

Para que o dashboard funcione, o seu computador (ou um servidor Windows) deve estar ligado com o ProfitChart aberto e o script `dashboard_bridge.py` em execução.

> [!WARNING]
> Sem o script local rodando, os dados no dashboard ficarão congelados.
