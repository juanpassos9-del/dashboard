from dotenv import load_dotenv
import os
from supabase import create_client
load_dotenv()

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_SERVICE_ROLE") # SERVICE ROLE
supabase = create_client(url, key)

def check_db():
    try:
        print("Buscando chaves com SERVICE_ROLE...")
        response = supabase.table("app_state").select("key, updated_at").execute()
        for row in response.data:
            print(f"Chave: {row['key']} | Atualizada em: {row['updated_at']}")
            
        print("\nDetalhes dos dados:")
        # dados_mercado
        response = supabase.table("app_state").select("value").eq("key", "dados_mercado").execute()
        if response.data:
            val = response.data[0]['value']
            if isinstance(val, list) and len(val) > 0:
                print(f"WIN/WDO: {val[0].get('symbol')} | {val[0].get('last_price')} | {val[0].get('updated_at')}")
        
        # mercados_globais
        response = supabase.table("app_state").select("value").eq("key", "mercados_globais").execute()
        if response.data:
            val = response.data[0]['value']
            meta = val.get('metadata', {})
            print(f"Global: {meta.get('last_updated')} ({meta.get('full_timestamp')})")
            
    except Exception as e:
        print(f"Erro: {e}")

check_db()
