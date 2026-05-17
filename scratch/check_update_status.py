import os
from supabase import create_client
import json
from datetime import datetime

# Simular st.secrets ou usar env
url = "https://your-supabase-url.supabase.co" # Substituído internamente pelo agente se necessário, mas vou usar o que estiver no .env ou secrets
key = "your-supabase-key"

# Como não tenho acesso direto aos segredos do Streamlit aqui, vou tentar ler do .env se existir
# Ou melhor, vou apenas verificar o arquivo local mercados_globais.json que já vi que está atualizado.

def check_local_json():
    try:
        with open("mercados_globais.json", "r") as f:
            data = json.load(f)
            last_upd = data.get("metadata", {}).get("last_updated", "---")
            print(f"Mercados Globais (JSON): {last_upd}")
    except:
        print("Erro ao ler mercados_globais.json")

check_local_json()
