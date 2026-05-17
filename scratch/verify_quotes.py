from dotenv import load_dotenv
import os
from supabase import create_client
load_dotenv()

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")

try:
    print("Iniciando conexão com Supabase...")
    supabase = create_client(url, key)
    print("Conexão estabelecida.")

    print("Buscando dados_mercado...")
    response = supabase.table("app_state").select("value").eq("key", "dados_mercado").execute()
    if response.data:
        val = response.data[0]['value']
        if isinstance(val, list) and len(val) > 0:
            print(f"Ativo Local: {val[0].get('symbol')} | Último: {val[0].get('last_price')} | Atualizado em: {val[0].get('updated_at')}")
        else:
            print(f"Ativo Local: {val.get('symbol')} | Atualizado em: {val.get('updated_at')}")
    else:
        print("Nenhum dado encontrado para dados_mercado.")

    print("Buscando mercados_globais...")
    response_g = supabase.table("app_state").select("value").eq("key", "mercados_globais").execute()
    if response_g.data:
        val_g = response_g.data[0]['value']
        meta = val_g.get('metadata', {})
        print(f"Mercados Globais (DB): {meta.get('last_updated')} | Timestamp: {meta.get('full_timestamp')}")
    else:
        print("Nenhum dado encontrado para mercados_globais.")

except Exception as e:
    print(f"ERRO CRÍTICO: {e}")
    sys.exit(1)
