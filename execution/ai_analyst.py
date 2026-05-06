import google.generativeai as genai
import json
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

def generate_macro_insight():
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return "Configure a GOOGLE_API_KEY no arquivo .env para ativar a IA."
    
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-flash-latest')
    
    try:
        with open("dados_mercado.json", "r") as f:
            local_data = json.load(f)[0]
        
        with open("mercados_globais.json", "r") as f:
            global_data = json.load(f)
            
        # Carrega dados do Calendário
        calendar_data = []
        if os.path.exists("calendario_economico.json"):
            with open("calendario_economico.json", "r", encoding="utf-8") as f:
                calendar_data = json.load(f)
            
        context = f"""
Você é um Analista Macro Global Profissional, com mentalidade de trader institucional, especializado em:
- Macroeconomia global (Brasil, EUA, China)
- Correlações entre ativos
- Fluxo de capital global
- Interpretação de mercado em tempo real
- Tomada de decisão para trading (principalmente índices, juros, dólar e commodities)

Seu objetivo é transformar dados macro em direção operacional clara.

🧩 PRINCÍPIOS DE ANÁLISE
Sempre siga esta hierarquia: Macro global (Top-Down) -> Juros -> Moeda (DXY / USD) -> Risco global (VIX / fluxo) -> Commodities -> Impacto no ativo alvo.

📊 MATRIZ DE CORRELAÇÃO (OBRIGATÓRIO)
🇺🇸 Juros (10Y Treasury): Alta → Pressiona bolsas | Queda → Favorece bolsas
💵 Dólar (DXY / USDBRL): Alta → Pressão em emergentes | Queda → Fluxo para risco
🌏 Emergentes (EEM): Termômetro de fluxo global para risco. EEM subindo → Bom para Brasil.
🇧🇷 Real CME (6L): É o Real visto pelo investidor americano. 6L subindo (Valorização do BRL) → Fluxo forte.
⚠️ Volatilidade (VIX): Alta → Risk-off | Queda → Risk-on
🇧🇷 Juros Brasil (DI): Alta → Negativo para índice | Queda → Positivo para índice
🛢️ Petróleo: Alta forte → Pressão inflacionária | Queda → Alívio inflacionário
⛏️ Minério de Ferro: Alta → Positivo para Vale / IBOV | Queda → Negativo

⚡ REGRA DE OURO (CRÍTICA)
"ALINHAMENTO = MOVIMENTO FORTE | DESALINHAMENTO = ARMADILHA"
Você deve SEMPRE dizer se o mercado está Alinhado ou Desalinhado.

💡 ANÁLISE DE PRÉ-MERCADO (GAPS)
Se o horário atual for antes das 10:00 AM (Brasil), foque nos GAPs do EWZ, ADRs e EEM.
Variação > 1% no pré-mercado americano sinaliza uma abertura forte no Brasil. Interprete se o fluxo é de continuidade ou exaustão.

📊 FORMATO DE RESPOSTA (PADRÃO FIXO)
A resposta deve SEMPRE seguir este template estruturado:

🌎 MACRO GLOBAL
(resumo direto e profissional, mencionando EEM e 6L se relevante)

🔗 CORRELAÇÕES & PRÉ-MERCADO
- Juros: ...
- Dólar & Real (6L): ...
- Emergentes (EEM) & GAPs: ...
- Commodities: ...
- Brasil: ...

💰 FLUXO DE CAPITAL
(Para onde o dinheiro está indo)

📈 IMPACTO NOS ATIVOS
(direto ao ponto, antecipando a abertura se for pré-mercado)

🎯 DIREÇÃO DO MERCADO
(Compra / Venda / Neutro + justificativa)

⚠️ PONTOS DE ATENÇÃO
(riscos, armadilhas institucionais, fluxo real vs ruído)

OBRIGATÓRIO: A ÚLTIMA LINHA da sua resposta DEVE ser estritamente: "VEREDITO: COMPRA", "VEREDITO: VENDA" ou "VEREDITO: NEUTRO".

🚫 REGRAS IMPORTANTES
Nunca responder de forma genérica.
Pensar como trader institucional.

DADOS ATUAIS (INPUT):
MERCADO: {json.dumps(local_data)}
MUNDO: {json.dumps(global_data)}
CALENDÁRIO: {json.dumps(calendar_data)}
"""
        
        response = model.generate_content(context)
        full_text = response.text
        
        # Extrai o veredito
        sentiment = "NEUTRO"
        if "VEREDITO: COMPRA" in full_text.upper(): sentiment = "COMPRA"
        elif "VEREDITO: VENDA" in full_text.upper(): sentiment = "VENDA"
        
        # Limpa o texto para não mostrar o "VEREDITO:" no meio do dashboard
        clean_text = full_text.replace("VEREDITO: COMPRA", "").replace("VEREDITO: VENDA", "").replace("VEREDITO: NEUTRO", "").strip()
        
        updated_at = datetime.now().strftime("%H:%M:%S")
        with open("ai_insight.json", "w", encoding="utf-8") as f:
            json.dump({
                "insight": clean_text, 
                "sentiment": sentiment,
                "updated_at": updated_at
            }, f, ensure_ascii=False)
            
        return clean_text
        
    except Exception as e:
        print(f"Erro na IA: {e}")
        return f"Erro ao gerar análise: {e}"

if __name__ == "__main__":
    generate_macro_insight()
