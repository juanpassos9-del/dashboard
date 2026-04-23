# Configuração do Frontend (SOP)

Este documento descreve como criar a interface web premium para o Dashboard Financeiro.

## 1. Pré-requisitos
- Node.js instalado (versão 18 ou superior).
- Terminal (PowerShell ou Bash).

## 2. Inicialização do Projeto
Para criar um dashboard moderno e rápido, utilizaremos o **Vite** com **React**.

### Comando:
```powershell
npx create-vite@latest DASHBOARD --template react
```

## 3. Design System (Premium Aesthetics)
Seguindo as diretrizes de design, utilizaremos:
- **Tailwind CSS**: Para estilização rápida e flexível.
- **Lucide React**: Para ícones modernos.
- **Recharts**: Para visualização de dados financeiros (gráficos de linha, área e velas).
- **Framer Motion**: Para animações suaves e micro-interações.

### Instalação de Dependências Base:
```powershell
cd DASHBOARD
npm install
npm install lucide-react recharts framer-motion tailwindcss postcss autoprefixer
npx tailwindcss init -p
```

## 4. Conexão com Dados
O frontend deve se conectar ao Supabase (configurado em `commercial_setup.md`) para receber atualizações em tempo real vindas do `dashboard_bridge.py`.

> [!TIP]
> Use WebSockets ou o Realtime SDK do Supabase para garantir que as cotações se movam sem a necessidade de recarregar a página.
