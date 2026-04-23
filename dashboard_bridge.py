import time
import json
import os
from dotenv import load_dotenv
from supabase import create_client, Client
from execution.rtd_gateway import RTDGateway
from execution.fetch_global_markets import fetch_global_data
from execution.ai_analyst import generate_macro_insight
from execution.fetch_calendar import fetch_economic_calendar

# Carrega variáveis de ambiente
load_dotenv()

class TerminalBridge:
    def __init__(self):
        # Configuração Supabase
        url: str = os.environ.get("SUPABASE_URL")
        key: str = os.environ.get("SUPABASE_SERVICE_ROLE")
        self.supabase: Client = create_client(url, key)
        
        self.gateway = RTDGateway(workbook_name="dashboard_trade_bloomberg_semaforo")
        self.file_path = "dados_mercado.json"
        self.last_global_fetch = 0
        self.last_ai_fetch = 0
        self.last_calendar_fetch = 0
        
    def sync_to_app_state(self, key: str, value: dict | list):
        """Salva o JSON completo na tabela app_state."""
        try:
            data = {
                "key": key,
                "value": value,
                "updated_at": "now()"
            }
            self.supabase.table("app_state").upsert(data).execute()
        except Exception as e:
            print(f"\n[!] Erro Supabase (app_state - {key}): {e}")

    def sync_data(self):
        print("[*] Iniciando Terminal Bridge (Profit -> Supabase)...")
        
        if not self.gateway.connect():
            print("[!] Erro: Abra o Excel 'dashboard_trade_bloomberg_semaforo'")
            return

        while True:
            try:
                current_time = time.time()
                
                # 1. Busca dados globais (1 min)
                if current_time - self.last_global_fetch > 60:
                    print("\n[*] Atualizando Mercados Globais...")
                    fetch_global_data()
                    if os.path.exists("mercados_globais.json"):
                        with open("mercados_globais.json", "r") as f:
                            self.sync_to_app_state("mercados_globais", json.load(f))
                    self.last_global_fetch = current_time

                # 2. Busca IA (5 min)
                if current_time - self.last_ai_fetch > 300:
                    print("\n[*] Atualizando IA...")
                    generate_macro_insight()
                    if os.path.exists("ai_insight.json"):
                        with open("ai_insight.json", "r", encoding="utf-8") as f:
                            self.sync_to_app_state("ai_insight", json.load(f))
                    self.last_ai_fetch = current_time

                # 3. Busca Calendário (1 hora)
                if current_time - self.last_calendar_fetch > 3600:
                    print("\n[*] Atualizando Calendário...")
                    fetch_economic_calendar()
                    if os.path.exists("calendario_economico.json"):
                        with open("calendario_economico.json", "r", encoding="utf-8") as f:
                            self.sync_to_app_state("calendario_economico", json.load(f))
                    self.last_calendar_fetch = current_time

                sheet = self.gateway.sheet
                symbol = sheet.Range("L3").Value
                
                if symbol:
                    # 4. Compila dados RTD Completos
                    data = {
                        "symbol": symbol,
                        "last_price": sheet.Range("L4").Value,
                        "vwap": sheet.Range("L5").Value,
                        "adjustment": sheet.Range("L6").Value,
                        "change_percent": sheet.Range("L12").Value,
                        "status": sheet.Range("L16").Value,
                        "bias": sheet.Range("L15").Value,
                        "escada": sheet.Range("A14:D24").Value,
                        "semaforo": {
                            "direcao": str(sheet.Range("G9").Value).split("|")[-1].strip() if sheet.Range("G9").Value else "---",
                            "correlacao_rtd": str(sheet.Range("G10").Value).split("|")[-1].strip() if sheet.Range("G10").Value else "---",
                            "correlacao_interna": str(sheet.Range("G11").Value).split("|")[-1].strip() if sheet.Range("G11").Value else "---"
                        },
                        "correlacoes": sheet.Range("A46:E49").Value,
                        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")
                    }
                    
                    # Salva localmente (backup) e envia para Nuvem (app_state)
                    with open(self.file_path, "w") as f:
                        json.dump([data], f)
                    
                    self.sync_to_app_state("dados_mercado", [data])
                            
                    print(f"\r[*] {symbol} sincronizado na Nuvem.", end="")
                
                time.sleep(1) # Atualiza a cada 1 segundo
                
            except Exception as e:
                print(f"\n[!] Erro na leitura: {e}")
                time.sleep(2)


if __name__ == "__main__":
    bridge = TerminalBridge()
    bridge.sync_data()
