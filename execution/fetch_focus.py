"""
fetch_focus.py
Script para extrair dados do Boletim Focus do Banco Central (BCB Olinda).
Indicadores: IPCA, Selic, PIB Total, Câmbio.
"""
import os
import sys
import json
import requests
from datetime import datetime

# Adiciona o diretório deste script ao path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

OUTPUT_FILE = "focus_bcb.json"

def fetch_focus_bcb():
    print("[*] Buscando dados do Boletim Focus na API BCB Olinda...")
    
    url = (
        "https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/ExpectativasMercadoAnuais"
        "?$filter=Indicador eq 'IPCA' or Indicador eq 'Selic' or Indicador eq 'PIB Total' or Indicador eq 'Câmbio'"
        "&$orderby=Data desc"
        "&$top=1500"
        "&$format=json"
    )
    
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        if "value" not in data or not data["value"]:
            print("[!] Nenhum dado retornado pela API do BCB.")
            return None
            
        records = data["value"]
        
        datas_distintas = []
        for item in records:
            if item["Data"] not in datas_distintas:
                datas_distintas.append(item["Data"])
        
        if len(datas_distintas) < 25:
            print("[!] Histórico insuficiente para 4 semanas.")
            return None
            
        hoje_str = datas_distintas[0]
        hoje_dt = datetime.strptime(hoje_str, "%Y-%m-%d")
        
        # Encontra datas "Há 1 Semana" (aprox 7 dias) e "Há 4 Semanas" (aprox 28 dias)
        ha_1_sem_str = None
        ha_4_sem_str = None
        
        for d in datas_distintas:
            dt = datetime.strptime(d, "%Y-%m-%d")
            delta = (hoje_dt - dt).days
            if ha_1_sem_str is None and delta >= 7:
                ha_1_sem_str = d
            if ha_4_sem_str is None and delta >= 28:
                ha_4_sem_str = d
                break
                
        # Fallbacks just in case
        if not ha_1_sem_str: ha_1_sem_str = datas_distintas[5] if len(datas_distintas) > 5 else datas_distintas[-1]
        if not ha_4_sem_str: ha_4_sem_str = datas_distintas[-1]
        
        focus_data = {}
        current_year = datetime.now().year
        
        for item in records:
            dt = item["Data"]
            if dt not in [hoje_str, ha_1_sem_str, ha_4_sem_str]:
                continue
                
            ref_year = item["DataReferencia"]
            # Foco nos próximos 3 anos
            if int(ref_year) < current_year or int(ref_year) > current_year + 2:
                continue
                
            indicador = item["Indicador"]
            if indicador == "PIB Total": indicador = "PIB"
            if indicador == "Câmbio": indicador = "Cambio"
            
            mediana = item["Mediana"]
            
            if ref_year not in focus_data:
                focus_data[ref_year] = {}
            if indicador not in focus_data[ref_year]:
                focus_data[ref_year][indicador] = {"hoje": None, "1_sem": None, "4_sem": None}
                
            if dt == hoje_str:
                focus_data[ref_year][indicador]["hoje"] = mediana
            elif dt == ha_1_sem_str:
                focus_data[ref_year][indicador]["1_sem"] = mediana
            elif dt == ha_4_sem_str:
                focus_data[ref_year][indicador]["4_sem"] = mediana
                
        output = {
            "updated_at": datetime.now().isoformat(),
            "publish_date": hoje_str,
            "date_1_sem": ha_1_sem_str,
            "date_4_sem": ha_4_sem_str,
            "source": "Banco Central do Brasil (BCB)",
            "years": focus_data
        }
        
        return output
        
    except Exception as e:
        print(f"[!] Erro ao buscar Focus: {e}")
        return None

def save_focus_data(data, filepath=None):
    if filepath is None:
        filepath = OUTPUT_FILE
        
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"[*] Dados do Focus salvos em {filepath}")
    return data

if __name__ == "__main__":
    data = fetch_focus_bcb()
    if data:
        save_focus_data(data)
        print("\n=== RESUMO BOLETIM FOCUS ===")
        print(f"Data Base BCB: {data['publish_date']}")
        for year, values in data['years'].items():
            print(f"\n[{year}]")
            for k, v in values.items():
                print(f"  - {k}: {v}")
