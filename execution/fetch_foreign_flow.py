"""
fetch_foreign_flow.py
Script para extrair dados de fluxo de investidores estrangeiros na B3.
Fonte: https://www.dadosdemercado.com.br/fluxo

Extrai o JSON embutido no HTML da página com o histórico diário
de fluxo por tipo de investidor (estrangeiro, institucional, PF, etc.).
"""
import os
import sys
import json
import re
import requests
from datetime import datetime

# Adiciona o diretório deste script ao path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.dadosdemercado.com.br/",
}

URL = "https://www.dadosdemercado.com.br/fluxo"
OUTPUT_FILE = "fluxo_estrangeiro.json"


def fetch_foreign_flow():
    """
    Faz scraping da página de fluxo do Dados de Mercado e extrai
    o JSON embutido com dados históricos de fluxo de investidores.
    
    Retorna:
        list[dict]: Lista de registros com campos:
            - date (str): Data no formato YYYY-MM-DD
            - foreigners (float): Saldo estrangeiro (R$ mil)
            - individuals (float): Saldo pessoa física (R$ mil)
            - institutional (float): Saldo institucional (R$ mil)
            - financial_institutions (float): Saldo inst. financeiras (R$ mil)
            - other (float): Saldo outros (R$ mil)
    """
    print(f"[*] Buscando dados de fluxo estrangeiro em {URL}...")
    
    try:
        response = requests.get(URL, headers=HEADERS, timeout=20)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"[!] Erro ao acessar {URL}: {e}")
        return []
    
    html = response.text
    
    # Estratégia 1: Buscar o bloco "const data = [...]" no HTML
    pattern = r'const\s+data\s*=\s*(\[.*?\]);'
    match = re.search(pattern, html, re.DOTALL)
    
    if not match:
        # Estratégia 2: Buscar qualquer array JSON com "foreigners"
        pattern2 = r'(\[\s*\{[^]]*?"foreigners"[^]]*?\}[^]]*?\])'
        match = re.search(pattern2, html, re.DOTALL)
    
    if not match:
        print("[!] Não foi possível encontrar dados de fluxo no HTML.")
        return []
    
    raw_json = match.group(1)
    
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as e:
        print(f"[!] Erro ao parsear JSON: {e}")
        # Tenta limpar o JSON
        raw_json = raw_json.replace("'", '"')
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError:
            print("[!] Falha definitiva ao parsear JSON.")
            return []
    
    if not isinstance(data, list):
        print("[!] Dados extraídos não são uma lista.")
        return []
    
    # Filtra e normaliza os registros
    records = []
    for item in data:
        if not isinstance(item, dict) or "date" not in item:
            continue
        
        record = {
            "date": item.get("date", ""),
            "foreigners": item.get("foreigners") or 0,
            "individuals": item.get("individuals") or 0,
            "institutional": item.get("institutional") or 0,
            "financial_institutions": item.get("financial_institutions") or 0,
            "other": item.get("other") or 0,
            "clubs": item.get("clubs") or 0,
            "companies": item.get("companies") or 0,
        }
        records.append(record)
    
    # Ordena por data (mais recente primeiro)
    records.sort(key=lambda x: x["date"], reverse=True)
    
    print(f"[*] {len(records)} registros de fluxo extraídos com sucesso.")
    if records:
        print(f"    Período: {records[-1]['date']} até {records[0]['date']}")
        print(f"    Último saldo estrangeiro: R$ {records[0]['foreigners']:,.0f} mil")
    
    return records


def save_flow_data(records, filepath=None):
    """Salva os dados de fluxo em arquivo JSON."""
    if filepath is None:
        filepath = OUTPUT_FILE
    
    output = {
        "updated_at": datetime.now().isoformat(),
        "source": "dadosdemercado.com.br",
        "records": records,
        "total_records": len(records),
    }
    
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"[*] Dados salvos em {filepath}")
    return output


if __name__ == "__main__":
    records = fetch_foreign_flow()
    
    if records:
        output = save_flow_data(records)
        
        # Preview dos últimos 10 dias
        print(f"\n{'='*60}")
        print("FLUXO ESTRANGEIRO B3 - Últimos 10 dias úteis")
        print(f"{'='*60}")
        print(f"{'Data':<12} {'Estrangeiro':>15} {'PF':>15} {'Institucional':>15}")
        print("-" * 60)
        for r in records[:10]:
            print(f"{r['date']:<12} {r['foreigners']:>15,.0f} {r['individuals']:>15,.0f} {r['institutional']:>15,.0f}")
        
        # Calcula acumulado
        acum = sum(r["foreigners"] for r in records)
        print(f"\n{'Acumulado':.<12} {acum:>15,.0f}")
    else:
        print("[!] Nenhum dado extraído.")
