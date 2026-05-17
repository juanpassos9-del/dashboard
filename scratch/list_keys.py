import os
from supabase import create_client
import json

url = "https://iqnmagdwpsvvzgcvpood.supabase.co"
key = "sb_publishable_ALRON08xndTwGlsSoR3YIw_Vs-oh31K"
supabase = create_client(url, key)

try:
    response = supabase.table("app_state").select("key").execute()
    print("Chaves encontradas no banco:")
    for row in response.data:
        print(f"- {row['key']}")
except Exception as e:
    print(f"Erro: {e}")
