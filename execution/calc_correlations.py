"""
calc_correlations.py — Calcula correlações intermercados e gera interpretações.

Parte da Camada 3 (Execução) do sistema.
Usa retornos diários de 30 dias para construir matriz de correlação de Pearson,
e fornece interpretações automáticas dos pares mais relevantes.
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings

warnings.filterwarnings("ignore")

# Ativos usados na correlação (subset mais relevante para análise intermercados)
CORRELATION_TICKERS = {
    "Petróleo": "CL=F",
    "Ouro": "GC=F",
    "VIX": "^VIX",
    "DXY": "DX-Y.NYB",
    "Euro": "6E=F",
    "S&P 500": "^GSPC",
    "Russell 2000": "^RUT",
    "EWZ": "EWZ",
    "EEM": "EEM",
    "US10Y": "^TNX",
    "US30Y": "^TYX",
    "PBR": "PBR",
    "VALE": "VALE",
    "ITUB": "ITUB",
}

# Interpretações pré-definidas de relações intermercados conhecidas
KNOWN_RELATIONSHIPS = {
    ("Ouro", "DXY"): {
        "negative": "Correlação clássica inversa: dólar fraco favorece ouro como reserva de valor.",
        "positive": "⚠️ Anomalia: ouro e dólar subindo juntos — possível fuga para segurança extrema (risk-off global).",
    },
    ("VIX", "S&P 500"): {
        "negative": "Comportamento normal: VIX sobe quando bolsa cai (medo no mercado).",
        "positive": "⚠️ Anomalia: VIX e S&P subindo juntos — mercado comprando proteção mesmo em alta.",
    },
    ("Petróleo", "EWZ"): {
        "positive": "Brasil como exportador de commodities se beneficia de petróleo em alta.",
        "negative": "Descolamento: EWZ caindo com petróleo em alta — possível risco doméstico/político.",
    },
    ("DXY", "EWZ"): {
        "negative": "Normal: dólar forte pressiona mercados emergentes incluindo Brasil.",
        "positive": "⚠️ Incomum: EWZ subindo com dólar — possível fluxo estrangeiro para Brasil.",
    },
    ("S&P 500", "EWZ"): {
        "positive": "Correlação de risco: mercados globais em sincronia.",
        "negative": "Descolamento Brasil vs. EUA — verificar fatores domésticos.",
    },
    ("DXY", "Ouro"): {
        "negative": "Padrão clássico: dólar e ouro em direções opostas.",
        "positive": "⚠️ Anomalia: ambos subindo — cenário de incerteza extrema.",
    },
    ("US10Y", "S&P 500"): {
        "positive": "Yields e bolsa subindo juntos — economia forte, mas atenção ao aperto monetário.",
        "negative": "Yields subindo e bolsa caindo — mercado precificando aperto monetário agressivo.",
    },
    ("Petróleo", "S&P 500"): {
        "positive": "Economia aquecida: demanda por energia e ações em alta.",
        "negative": "Petróleo subindo com bolsa caindo — pressão inflacionária sobre lucros.",
    },
    ("VIX", "EWZ"): {
        "negative": "Normal: medo global (VIX alto) pressiona emergentes.",
        "positive": "⚠️ Incomum: EWZ subindo com VIX alto — possível resiliência do Brasil.",
    },
    ("Ouro", "US10Y"): {
        "negative": "Yields altos aumentam custo de oportunidade de segurar ouro.",
        "positive": "⚠️ Ouro e yields subindo — mercado precificando inflação persistente.",
    },
    ("PBR", "Petróleo"): {
        "positive": "Correlação esperada: Petrobras acompanha preço do petróleo.",
        "negative": "⚠️ Descolamento: risco empresa-específico na Petrobras.",
    },
    ("VALE", "EWZ"): {
        "positive": "Vale acompanhando o mercado brasileiro.",
        "negative": "Descolamento: verificar setor de mineração vs. mercado geral.",
    },
    ("EWZ", "EEM"): {
        "positive": "Emergentes movendo em bloco — fluxo global de risco.",
        "negative": "Brasil descolando de emergentes — fatores domésticos em jogo.",
    },
}


def fetch_correlation_data(period_days=30):
    """
    Busca dados históricos e calcula retornos diários.
    Retorna DataFrame de retornos diários.
    """
    tickers = list(CORRELATION_TICKERS.values())
    names = list(CORRELATION_TICKERS.keys())

    end_date = datetime.now()
    start_date = end_date - timedelta(days=period_days + 10)  # margem extra

    try:
        data = yf.download(
            tickers,
            start=start_date.strftime("%Y-%m-%d"),
            end=end_date.strftime("%Y-%m-%d"),
            progress=False,
            threads=True,
        )

        if data.empty:
            return pd.DataFrame()

        # Extrai preços de fechamento
        if len(tickers) == 1:
            close_data = data[["Close"]]
            close_data.columns = names
        else:
            close_data = data["Close"] if "Close" in data.columns.get_level_values(0) else data.xs("Close", level=0, axis=1)
            # Renomeia colunas para nomes legíveis
            ticker_to_name = {v: k for k, v in CORRELATION_TICKERS.items()}
            close_data.columns = [ticker_to_name.get(col, col) for col in close_data.columns]

        # Calcula retornos diários
        returns = close_data.pct_change().dropna()

        # Remove colunas com muitos NaN
        returns = returns.dropna(axis=1, thresh=int(len(returns) * 0.7))

        return returns

    except Exception as e:
        print(f"[ERROR] Falha ao buscar dados de correlação: {e}")
        return pd.DataFrame()


def calculate_correlation_matrix(returns):
    """
    Calcula matriz de correlação de Pearson.
    Retorna DataFrame com a matriz.
    """
    if returns.empty:
        return pd.DataFrame()

    corr_matrix = returns.corr()
    return corr_matrix.round(2)


def interpret_correlations(corr_matrix, top_n=8):
    """
    Gera interpretações em português das correlações mais relevantes.
    Retorna lista de dicts com {pair, correlation, interpretation, emoji}.
    """
    if corr_matrix.empty:
        return []

    interpretations = []
    processed_pairs = set()

    # Primeiro: verifica relações conhecidas
    for (asset_a, asset_b), descriptions in KNOWN_RELATIONSHIPS.items():
        if asset_a in corr_matrix.columns and asset_b in corr_matrix.columns:
            corr_value = corr_matrix.loc[asset_a, asset_b]

            if pd.isna(corr_value):
                continue

            pair_key = tuple(sorted([asset_a, asset_b]))
            processed_pairs.add(pair_key)

            direction = "positive" if corr_value >= 0 else "negative"
            interpretation = descriptions[direction]

            # Emoji baseado na força da correlação
            abs_corr = abs(corr_value)
            if abs_corr >= 0.7:
                strength = "🔴 Forte"
            elif abs_corr >= 0.4:
                strength = "🟡 Moderada"
            else:
                strength = "🟢 Fraca"

            interpretations.append({
                "pair": f"{asset_a} × {asset_b}",
                "correlation": corr_value,
                "strength": strength,
                "interpretation": interpretation,
                "abs_corr": abs_corr,
            })

    # Ordena por força absoluta
    interpretations.sort(key=lambda x: x["abs_corr"], reverse=True)

    # Depois: adiciona pares com correlação extrema que não estão nas relações conhecidas
    assets = corr_matrix.columns.tolist()
    for i in range(len(assets)):
        for j in range(i + 1, len(assets)):
            pair_key = tuple(sorted([assets[i], assets[j]]))
            if pair_key in processed_pairs:
                continue

            corr_value = corr_matrix.iloc[i, j]
            if pd.isna(corr_value):
                continue

            abs_corr = abs(corr_value)
            if abs_corr >= 0.6:  # só mostra correlações fortes
                if abs_corr >= 0.7:
                    strength = "🔴 Forte"
                else:
                    strength = "🟡 Moderada"

                direction = "positiva" if corr_value >= 0 else "negativa"
                interpretation = f"Correlação {direction} significativa entre {assets[i]} e {assets[j]}."

                interpretations.append({
                    "pair": f"{assets[i]} × {assets[j]}",
                    "correlation": corr_value,
                    "strength": strength,
                    "interpretation": interpretation,
                    "abs_corr": abs_corr,
                })

    # Ordena tudo e retorna top N
    interpretations.sort(key=lambda x: x["abs_corr"], reverse=True)
    return interpretations[:top_n]


def get_full_correlation_analysis(period_days=30):
    """
    Pipeline completo: busca dados → calcula correlação → interpreta.
    Retorna (corr_matrix, interpretations).
    """
    returns = fetch_correlation_data(period_days)
    corr_matrix = calculate_correlation_matrix(returns)
    interpretations = interpret_correlations(corr_matrix)
    return corr_matrix, interpretations


# ============================================================
# Teste standalone
# ============================================================
if __name__ == "__main__":
    print("Calculando correlações (30 dias)...")
    matrix, insights = get_full_correlation_analysis()

    if not matrix.empty:
        print("\n=== Matriz de Correlação ===")
        print(matrix.to_string())

        print("\n=== Interpretações ===")
        for insight in insights:
            print(f"\n{insight['strength']} | {insight['pair']}: {insight['correlation']:.2f}")
            print(f"  → {insight['interpretation']}")
    else:
        print("Não foi possível calcular correlações.")
