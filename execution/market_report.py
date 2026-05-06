import google.generativeai as genai
import json
import os
from dotenv import load_dotenv
from datetime import datetime
from execution.fetch_news import fetch_all_news

load_dotenv()

def generate_market_report():
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("[!] Erro: GOOGLE_API_KEY não encontrada.")
        return
    
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-flash-latest')
    
    try:
        # 1. Carrega Dados de Mercado
        local_data = {}
        if os.path.exists("dados_mercado.json"):
            with open("dados_mercado.json", "r") as f:
                local_data = json.load(f)[0]
        
        global_data = {}
        if os.path.exists("mercados_globais.json"):
            with open("mercados_globais.json", "r") as f:
                global_data = json.load(f)
                
        # 2. Busca Notícias Frescas
        print("[*] Coletando notícias para o relatório...")
        news = fetch_all_news(max_results=15, max_age_hours=12)
        news_context = "\n".join([f"- [{n['source']}] {n['title']}: {n['summary']}" for n in news])
            
        # 3. Prompt para o Market Report
        prompt = f"""
Você é um Estrategista-Chefe de uma Mesa de Operações Institucional.
Seu trabalho é criar o "MARKET REPORT" - um resumo narrativo, ácido e preciso do que está movendo o mercado AGORA.

CONTEXTO DE MERCADO:
- LOCAL (WIN/WDO): {json.dumps(local_data)}
- GLOBAL: {json.dumps(global_data)}

PRINCIPAIS NOTÍCIAS DO MOMENTO:
{news_context}

INSTRUÇÕES:
1. Conecte as notícias aos movimentos que estamos vendo nos preços.
2. Seja direto. Não use "clichês" de jornalismo. Fale como um trader para outros traders.
3. Se uma notícia da Bloomberg/Reuters justifica a queda do Petróleo ou a alta do Dólar, explique essa conexão.
4. Divida em 3 seções curtas:
   - ⚡ DRIVERS DO MOMENTO (O que está mandando no jogo)
   - 🌍 CENÁRIO GLOBAL VS BRASIL (A conexão entre o que sai lá fora e o que acontece aqui)
   - 🛡️ RISCOS RADAR (O que pode azedar o clima nas próximas horas)

FORMATO DE SAÍDA:
- Use Markdown.
- Use emojis para destacar pontos chave.
- Mantenha o texto compacto e de alto impacto.

Mantenha o tom profissional, institucional e focado em fluxo.
"""
        
        print("[*] Gerando relatório via IA...")
        response = model.generate_content(prompt)
        report_text = response.text
        
        updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        output = {
            "report": report_text,
            "updated_at": updated_at
        }
        
        with open("market_report.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False)
            
        print("[+] Market Report gerado com sucesso.")
        return output
        
    except Exception as e:
        print(f"[!] Erro ao gerar Market Report: {e}")
        return None

if __name__ == "__main__":
    generate_market_report()
