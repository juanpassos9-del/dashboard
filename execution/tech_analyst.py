import google.generativeai as genai
import yfinance as yf
import os
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

def get_technical_analysis(symbol_name, ticker_symbol):
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return "Configure a GOOGLE_API_KEY no arquivo .env para ativar a análise técnica via IA."
        
    try:
        # Busca dados dos últimos 30 dias para pegar contexto, com intervalo diário
        df = yf.download(ticker_symbol, period="30d", interval="1d", progress=False)
        if df.empty:
            return f"Não foi possível obter os dados históricos para o ativo {symbol_name} ({ticker_symbol}). Verifique o ticker."
            
        # Pega as últimas 15 sessões de fechamento para não exceder limites de prompt e ir direto ao ponto
        recent_data = df.tail(15) 
        
        # Formata os dados para o prompt
        price_history = recent_data.to_string()
        
        prompt = f"""
Você é um Analista Técnico de Elite Institucional focado em análise gráfica e price action quantitativo.
Seu objetivo é ler os dados numéricos históricos de preços (OHLC - Open, High, Low, Close) e Volume de {symbol_name} ({ticker_symbol}) e fornecer um relatório técnico imediato.

DADOS HISTÓRICOS (Últimos 15 dias de negociação):
{price_history}

Com base nestes números absolutos, gere uma análise técnica concisa que inclua:
1. **Tendência atual**: Análise de topos e fundos nos últimos 15 dias (tendência de curto prazo) e variação percentual.
2. **Níveis Chave**: Identifique pelo menos 1 suporte forte e 1 resistência forte baseados nos pontos de mínima e máxima recentes.
3. **Price Action / Momentum**: Avalie se o momento recente é de exaustão, consolidação ou rompimento direcional (analise os preços de abertura vs fechamento e o tamanho dos pavios/sombras).
4. **Veredito Técnico**: Direção sugerida no curto prazo (COMPRA, VENDA ou NEUTRO).

FORMATO DA RESPOSTA:
- Use tópicos curtos e diretos.
- Seja objetivo e escreva como um trader.
- Destaque os níveis de preço em negrito.
"""
        try:
            genai.configure(api_key=api_key)
            # Usando o modelo Pro ou Flash
            model = genai.GenerativeModel('gemini-flash-latest') 
            response = model.generate_content(prompt)
            return response.text
        except Exception as gemini_e:
            err_str = str(gemini_e).lower()
            if "429" in err_str or "quota" in err_str or "exhausted" in err_str:
                # Fallback para OpenAI
                openai_key = os.getenv("OPENAI_API_KEY")
                if openai_key:
                    from openai import OpenAI
                    client = OpenAI(api_key=openai_key)
                    completion = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[
                            {"role": "system", "content": "Você é um analista financeiro institucional rigoroso e focado em price action numérico."},
                            {"role": "user", "content": prompt}
                        ]
                    )
                    return f"**[Fallback IA: OpenAI GPT-4o]**\n\n" + completion.choices[0].message.content
                else:
                    return f"Erro de Limite no Gemini e chave da OpenAI ausente: {gemini_e}"
            else:
                return f"Erro interno do modelo Gemini: {gemini_e}"
        
    except Exception as e:
        return f"Erro na análise técnica: {e}"

if __name__ == "__main__":
    # Teste rápido
    print(get_technical_analysis("S&P 500", "^GSPC"))
