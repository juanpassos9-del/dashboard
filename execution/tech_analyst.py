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
Você é um Analista Técnico de Elite Institucional especializado nas metodologias de Richard Wyckoff, Volume Spread Analysis (VSA) e Smart Money Concepts (SMC).
Seu objetivo é analisar os dados numéricos históricos de preços (OHLC - Open, High, Low, Close) e Volume de {symbol_name} ({ticker_symbol}) e fornecer um relatório técnico profundo e padronizado.

DADOS HISTÓRICOS (Últimos 15 dias de negociação):
{price_history}

Com base nestes dados absolutos (focando puramente no comportamento do Preço e Volume), gere uma análise técnica concisa estruturada no seguinte padrão operacional:

1. **Contexto Wyckoff**: Identifique em qual possível fase do ciclo o ativo se encontra (Acumulação, Mark-up, Distribuição, Mark-down). Procure evidências de *Stopping Volume*, *Springs*, *Upthrusts* ou Absorção Institucional.
2. **Análise de Preço e Volume (VSA)**: Analise a relação entre o *spread* (tamanho dos candles de fechamento a fechamento ou máxima a mínima) e o Volume negociado. Identifique anomalias como "Esforço vs Resultado", "No Demand/No Supply" ou Clímax de Volume.
3. **Smart Money Concepts (SMC)**: 
    - **Estrutura**: Identifique quebras de estrutura (BOS - Break of Structure) ou mudanças de caráter (ChoCh - Change of Character) nos movimentos recentes.
    - **Níveis Institucionais**: Aponte capturas de liquidez (*Liquidity Sweeps*), e identifique zonas prováveis de *Order Blocks* ou *Fair Value Gaps* (Imbalances) onde o dinheiro inteligente pode estar posicionado.
4. **Veredito Institucional**: Viés direcional sugerido para o curto prazo (COMPRA, VENDA ou NEUTRO), embasado na confluência destas 3 leituras.

FORMATO DA RESPOSTA:
- Use bullet points curtos, diretos e profissionais.
- Mantenha a objetividade de um mesa proprietária ou fundo quant.
- Destaque os níveis de preço relevantes (zonas de liquidez, OBs, FVGs) sempre em **negrito**.
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
                            {"role": "system", "content": "Você é um Analista Técnico de Elite Institucional especializado em Wyckoff, VSA e Smart Money Concepts (SMC). Mantenha extremo rigor analítico e foco institucional."},
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
