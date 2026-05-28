import time
import json
import os
from dotenv import load_dotenv
from supabase import create_client, Client
from execution.rtd_gateway import RTDGateway
from execution.fetch_global_markets import fetch_global_data
from execution.ai_analyst import generate_macro_insight
from execution.fetch_calendar import fetch_economic_calendar
from execution.market_report import generate_market_report
from execution.logger_setup import setup_logger
from execution.fetch_financial_juice import fetch_financial_juice_news

# Configura Logger
logger = setup_logger("TerminalBridge")

# Carrega variáveis de ambiente
load_dotenv()

class TerminalBridge:
    def __init__(self):
        try:
            # Configuração Supabase
            url: str = os.environ.get("SUPABASE_URL")
            key: str = os.environ.get("SUPABASE_SERVICE_ROLE")
            if not url or not key:
                logger.error("Credenciais Supabase ausentes no .env")
                raise ValueError("Credenciais ausentes")
                
            self.supabase: Client = create_client(url, key)
            logger.info("Conectado ao Supabase com sucesso.")
        except Exception as e:
            logger.critical(f"Falha na inicialização do Supabase: {e}")
            self.supabase = None
        
        self.gateway = RTDGateway(workbook_name="dashboard_trade_bloomberg_semaforo", sheet_name="Dashboard")
        self.file_path = "dados_mercado.json"
        self.last_global_fetch = 0
        self.last_ai_fetch = 0
        self.last_calendar_fetch = 0
        self.last_report_fetch = 0
        self.last_reconnect_attempt = 0
        self.last_news_fetch = 0
        
    def sync_to_app_state(self, key: str, value: dict | list):
        """Salva o JSON completo na tabela app_state com retentativa."""
        if not self.supabase: return
        for attempt in range(3):
            try:
                data = {
                    "key": key,
                    "value": value,
                    "updated_at": "now()"
                }
                self.supabase.table("app_state").upsert(data).execute()
                return # Sucesso
            except Exception as e:
                logger.warning(f"Erro ao sincronizar {key} (Tentativa {attempt+1}): {e}")
                time.sleep(1)
        logger.error(f"Falha definitiva ao sincronizar {key} após 3 tentativas.")

    def run_task(self, name, func, *args):
        """Executa uma tarefa de forma isolada para não travar o loop principal."""
        try:
            logger.info(f"Executando tarefa: {name}")
            return func(*args)
        except Exception as e:
            logger.error(f"Falha na tarefa {name}: {e}")
            return None

    def sync_data(self):
        logger.info("Iniciando Terminal Bridge (Profit -> Supabase)...")
        
        if not self.gateway.connect():
            logger.warning("[!] Excel 'dashboard_trade_bloomberg_semaforo' não detectado. Iniciando em modo offline para o RTD. O restante do dashboard continuará atualizando normalmente.")

        while True:
            try:
                current_time = time.time()
                
                # 1. Busca dados globais (1 min)
                if current_time - self.last_global_fetch > 60:
                    self.run_task("Mercados Globais", fetch_global_data)
                    if os.path.exists("mercados_globais.json"):
                        with open("mercados_globais.json", "r") as f:
                            self.sync_to_app_state("mercados_globais", json.load(f))
                    self.last_global_fetch = current_time

                # 2. Busca IA (5 min)
                if current_time - self.last_ai_fetch > 300:
                    self.run_task("IA Analista", generate_macro_insight)
                    if os.path.exists("ai_insight.json"):
                        with open("ai_insight.json", "r", encoding="utf-8") as f:
                            new_insight = json.load(f)
                            self.sync_to_app_state("ai_insight", new_insight)
                            
                            # Mantém histórico dos últimos 5
                            try:
                                response = self.supabase.table("app_state").select("value").eq("key", "ai_insight_history").execute()
                                history = response.data[0]["value"] if response.data else []
                                if not isinstance(history, list): history = []
                                
                                history.append({
                                    "sentiment": new_insight.get("sentiment", "NEUTRO"),
                                    "updated_at": new_insight.get("updated_at", ""),
                                    "id": int(time.time())
                                })
                                history = history[-5:]
                                self.sync_to_app_state("ai_insight_history", history)
                            except Exception as e:
                                logger.error(f"Erro ao atualizar histórico IA: {e}")
                                
                    self.last_ai_fetch = current_time

                # 3. Market Report (30 min)
                if current_time - self.last_report_fetch > 1800:
                    self.run_task("Market Report", generate_market_report)
                    if os.path.exists("market_report.json"):
                        with open("market_report.json", "r", encoding="utf-8") as f:
                            self.sync_to_app_state("market_report", json.load(f))
                    self.last_report_fetch = current_time

                # 4. Busca Calendário (1 hora)
                if current_time - self.last_calendar_fetch > 3600:
                    self.run_task("Calendário Econômico", fetch_economic_calendar)
                    if os.path.exists("calendario_economico.json"):
                        with open("calendario_economico.json", "r", encoding="utf-8") as f:
                            self.sync_to_app_state("calendario_economico", json.load(f))
                    self.last_calendar_fetch = current_time

                # 6. Busca noticias do Financial Juice (45 segundos)
                if current_time - self.last_news_fetch > 45:
                    news_list = self.run_task("Financial Juice News", fetch_financial_juice_news, 50)
                    if news_list:
                        self.sync_to_app_state("financial_juice_news", news_list)
                    self.last_news_fetch = current_time

                # 5. Dados RTD (Tempo Real - 1s)
                sheet = None
                try:
                    sheet = self.gateway.sheet
                except Exception:
                    self.gateway.sheet = None
                    
                # Se não estiver conectado ao Excel, tenta reconectar a cada 10 segundos
                if not sheet:
                    if current_time - self.last_reconnect_attempt > 10:
                        logger.info("Excel offline ou desconectado. Tentando reconectar...")
                        self.last_reconnect_attempt = current_time
                        if self.gateway.connect():
                            sheet = self.gateway.sheet
                            logger.info("Reconectado ao Excel com sucesso!")
                    
                if sheet:
                    try:
                        symbol = sheet.Range("L3").Value
                        if symbol:
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
                                "saldo_agressao": sheet.Range("J6").Value,
                                "correlacoes": sheet.Range("A46:E49").Value,
                                "acoes_peso": sheet.Range("A55:G59").Value,
                                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")
                            }
                            
                            # Salva backup local
                            try:
                                with open(self.file_path, "w") as f:
                                    json.dump([data], f)
                                self.sync_to_app_state("dados_mercado", [data])
                                print(f"\r[*] {symbol} sincronizado: {data['updated_at']}", end="")
                            except Exception as e:
                                logger.error(f"Erro ao salvar dados RTD: {e}")
                    except Exception as e:
                        # Se houver erro de leitura do Excel (ex: Excel fechado no meio da operação), trata e limpa para tentar reconexão
                        logger.warning(f"Erro de comunicação COM com o Excel: {e}. Tratando para reconexão suave...")
                        self.gateway.sheet = None
                
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"Erro no loop principal: {e}")
                time.sleep(5) # Espera um pouco mais se houver erro crítico

if __name__ == "__main__":
    bridge = TerminalBridge()
    bridge.sync_data()
