import google.generativeai as genai
import json
import os
from dotenv import load_dotenv

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
        Você é um Analista Macro Sênior. Sua tarefa é analisar os dados e fornecer um insight estratégico.
        
        FOCO 1: Analise a direção dos Treasuries Americanos (Yields).
        FOCO 2: Analise o CALENDÁRIO ECONÔMICO:
        - Se o valor "ACTUAL" estiver presente: Explique se veio melhor/pior que o esperado e o impacto.
        - Se o valor "ACTUAL" estiver vazio: Analise a EXPECTATIVA (Anterior vs Projeção) para os próximos eventos importantes.
        
        OBRIGATÓRIO: A última linha deve ser apenas: VEREDITO: COMPRA, VENDA ou NEUTRO.
        
        DADOS ATUAIS:
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
        
        # Limpa o texto para não mostrar o "VEREDITO:" no meio do parágrafo se não quiser
        clean_text = full_text.replace("VEREDITO: COMPRA", "").replace("VEREDITO: VENDA", "").replace("VEREDITO: NEUTRO", "").strip()
        
        with open("ai_insight.json", "w", encoding="utf-8") as f:
            json.dump({"insight": clean_text, "sentiment": sentiment}, f, ensure_ascii=False)
            
        return clean_text
        
    except Exception as e:
        print(f"Erro na IA: {e}")
        return f"Erro ao gerar análise: {e}"

if __name__ == "__main__":
    generate_macro_insight()
