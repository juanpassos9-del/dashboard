"""
fetch_financial_juice.py — Busca notícias do Financial Juice e as traduz em tempo real usando IA.
Possui cache persistente para evitar chamadas excessivas de API e fallback heurístico de termos financeiros.
Parte da Camada 3 (Execução).
"""

import os
import re
import json
import warnings
import feedparser
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
import google.generativeai as genai
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from execution.logger_setup import setup_logger

warnings.filterwarnings("ignore")

# Configura o logger
logger = setup_logger("financial_juice")

# Carrega variáveis de ambiente
load_dotenv()

# Caminho do cache local
CACHE_DIR = ".tmp"
CACHE_FILE = os.path.join(CACHE_DIR, "financial_juice_cache.json")

# RSS Feed URL do Financial Juice
RSS_URL = "https://www.financialjuice.com/feed.ashx?xy=rss"

# Mapeamento heurístico avançado para tradução rápida de fallback
HEURISTIC_DICT = {
    r"\bFed's ([A-Z][A-Za-z]+):": r"\1, do Federal Reserve:",
    r"\bProductivity shifts are hard to spot in real time\b": "Mudanças de produtividade são difíceis de identificar em tempo real",
    r"\bHigher productivity growth raises real rates over the long run\b": "Maior crescimento da produtividade eleva os juros reais no longo prazo",
    r"\bFundamental shifts in productivity are difficult to identify in real time\b": "Mudanças fundamentais de produtividade são difíceis de identificar em tempo real",
    r"\bPolicy response to productivity growth depends on the duration of the shift\b": "A resposta de política monetária ao crescimento da produtividade depende da duração da mudança",
    r"\bImpact also depends on how quickly the public recognizes the productivity change\b": "O impacto também depende da rapidez com que o público reconhece a mudança de produtividade",
    r"\bNew York Fed President John Williams made the comments in prepared remarks\b": "O presidente do Fed de Nova York, John Williams, fez os comentários em discurso preparado",
    r"\bprepared remarks\b": "discurso preparado",
    r"\bproductivity\b": "produtividade",
    r"\bshifts\b": "mudanças",
    r"\bshift\b": "mudança",
    r"\bhard to spot\b": "difícil de identificar",
    r"\bin real time\b": "em tempo real",
    r"\breal time\b": "tempo real",
    r"\bgrowth\b": "crescimento",
    r"\braises\b": "eleva",
    r"\breal rates\b": "juros reais",
    r"\bover the long run\b": "no longo prazo",
    r"\blong run\b": "longo prazo",
    r"\bfundamental\b": "fundamental",
    r"\bdifficult to identify\b": "difícil de identificar",
    r"\bidentify\b": "identificar",
    r"\bresponse\b": "resposta",
    r"\bduration\b": "duração",
    r"\bpublic recognizes\b": "público reconhece",
    r"\brecognizes\b": "reconhece",
    r"\bcomments\b": "comentários",
    r"\bSecured overnight financing rate\b": "Taxa de Financiamento Fechado de um Dia para o Outro (SOFR)",
    r"\bbuilding permits\b": "licenças de construção",
    r"\bBuilding Permits\b": "Licenças de Construção",
    r"\bannual rate\b": "taxa anual",
    r"\bECB Accounts\b": "Ata da Reunião do BCE",
    r"\bECB accounts\b": "ata da reunião do BCE",
    r"\bECB\b": "BCE (Banco Central Europeu)",
    r"\bFed\b": "Fed (Federal Reserve)",
    r"\bFOMC\b": "FOMC (Comitê de Política Monetária dos EUA)",
    r"\bBOE\b": "BoE (Banco da Inglaterra)",
    r"\bBOJ\b": "BoJ (Banco do Japão)",
    r"\bBCB\b": "BCB (Banco Central do Brasil)",
    r"\bCopom\b": "Copom",
    r"\brate cut(s)?\b": "corte de juros",
    r"\brate hike(s)?\b": "alta de juros",
    r"\binterest rate(s)?\b": "taxa de juros",
    r"\byield(s)?\b": "retornos (yields)",
    r"\bTreasury\b": "Tesouro americano",
    r"\btreasuries\b": "títulos do Tesouro dos EUA",
    r"\binflation\b": "inflação",
    r"\bCPI\b": "CPI (inflação ao consumidor)",
    r"\bPCE\b": "PCE (inflação de consumo)",
    r"\bPPI\b": "PPI (inflação ao produtor)",
    r"\bGDP\b": "PIB",
    r"\bunemployment\b": "desemprego",
    r"\bjobless claims\b": "pedidos de auxílio-desemprego",
    r"\bnon-farm payrolls?\b": "non-farm payrolls (dados de emprego nos EUA)",
    r"\bcrude\b": "petróleo bruto",
    r"\boil\b": "petróleo",
    r"\bgold\b": "ouro",
    r"\bsilver\b": "prata",
    r"\bdollar\b": "dólar",
    r"\bgreenback\b": "dólar",
    r"\bBRL\b": "Real",
    r"\bforex\b": "câmbio",
    r"\bshares\b": "ações",
    r"\bstocks\b": "ações",
    r"\bsecurities\b": "títulos",
    r"\bpolicymaker(s)?\b": "dirigentes de política monetária",
    r"\bcentral bank(s)?\b": "banco central",
    r"\bmonetary policy\b": "política monetária",
    r"\bhawkish\b": "rigoroso contra inflação (hawkish)",
    r"\bdovish\b": "flexível com inflação (dovish)",
    r"\bBreaking\b": "URGENTE",
    r"\bbreaking\b": "urgente",
    r"\bFJElite\b": "Exclusivo FinancialJuice",
}

# Inicializa a API do Gemini se disponível
api_key = os.getenv("GOOGLE_API_KEY")
gemini_available = False

if api_key:
    try:
        genai.configure(api_key=api_key)
        # Testa a inicialização do modelo
        _ = genai.GenerativeModel('gemini-2.0-flash')
        gemini_available = True
        logger.info("Integração com Gemini AI configurada com sucesso para tradução.")
    except Exception as e:
        logger.warning(f"Erro ao configurar Gemini AI: {e}. Usando tradução heurística como padrão.")
else:
    logger.warning("GOOGLE_API_KEY não encontrada no ambiente. Usando tradução heurística.")


def load_cache():
    """Carrega o cache local de notícias traduzidas."""
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)
        
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Erro ao carregar cache: {e}")
            return {}
    return {}


def save_cache(cache_data):
    """Salva as notícias traduzidas no cache local."""
    try:
        # Mantém apenas as últimas 500 notícias para evitar crescimento indefinido do cache
        if len(cache_data) > 500:
            # Ordena por timestamp para apagar os mais antigos
            sorted_keys = sorted(cache_data.keys(), key=lambda k: cache_data[k].get("timestamp", 0))
            for k in sorted_keys[:-500]:
                cache_data.pop(k, None)
                
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Erro ao salvar cache: {e}")


def translate_headline_heuristic(text):
    """Traduz a manchete de forma heurística substituindo termos financeiros chaves."""
    translated = text
    
    # Remove prefixos
    translated = re.sub(r"^FinancialJuice:\s*", "", translated)
    translated = re.sub(r"^Financial Juice:\s*", "", translated)
    
    # Aplica substituições do dicionário
    for en_pattern, pt_val in HEURISTIC_DICT.items():
        translated = re.compile(en_pattern, re.IGNORECASE).sub(pt_val, translated)
        
    # Limpa espaços adicionais
    translated = re.sub(r"\s+", " ", translated).strip()
    return translated


def ensure_portuguese_fields(item):
    """Garante campos em pt-BR para exibição, com fallback heurístico sem custo de API."""
    title_en = item.get("title_en", "")
    summary = item.get("summary", "") or title_en

    if not item.get("title_pt"):
        item["title_pt"] = translate_headline_heuristic(title_en)

    if not item.get("summary_pt"):
        if summary.strip() == title_en.strip():
            item["summary_pt"] = item["title_pt"]
        else:
            item["summary_pt"] = translate_headline_heuristic(summary)

    return item


ENGLISH_MARKERS = {
    "the", "and", "are", "is", "was", "were", "will", "with", "from", "after",
    "before", "over", "under", "growth", "rates", "yields", "stocks", "dollar",
    "productivity", "shift", "shifts", "hard", "spot", "real", "time", "depends",
    "comments", "prepared", "remarks", "policy", "response", "raises",
}


def looks_untranslated(text, original=""):
    """Detecta texto ainda em inglês para evitar exibir cache antigo sem tradução."""
    text = (text or "").strip()
    original = (original or "").strip()
    if not text:
        return True
    if original and text.lower() == original.lower():
        return True

    words = re.findall(r"[A-Za-zÀ-ÿ']+", text.lower())
    if not words:
        return False

    english_hits = sum(1 for word in words if word in ENGLISH_MARKERS)
    portuguese_hits = sum(1 for word in words if word in {
        "de", "do", "da", "dos", "das", "em", "no", "na", "nos", "nas",
        "com", "para", "após", "antes", "juros", "ações", "mercado",
        "inflação", "dólar", "títulos", "rendimentos",
    })
    return english_hits >= 2 and english_hits >= portuguese_hits


def translate_text_google(text):
    """Fallback via endpoint público do Google Translate quando Gemini não estiver disponível."""
    text = (text or "").strip()
    if not text:
        return text

    try:
        response = requests.get(
            "https://translate.googleapis.com/translate_a/single",
            params={
                "client": "gtx",
                "sl": "en",
                "tl": "pt",
                "dt": "t",
                "q": text,
            },
            timeout=8,
        )
        response.raise_for_status()
        data = response.json()
        translated = "".join(part[0] for part in data[0] if part and part[0])
        return translated.strip() or translate_headline_heuristic(text)
    except Exception as e:
        logger.warning(f"Fallback Google Translate falhou: {e}")
        return translate_headline_heuristic(text)


def translate_batch_fallback(texts):
    return {text: translate_text_google(text) for text in texts}


def normalize_news_translations(news_list, cache=None):
    """Garante title_pt e summary_pt em pt-BR, traduzindo novamente cache antigo quando necessário."""
    cache = cache if isinstance(cache, dict) else {}
    texts_to_translate = []

    for item in news_list:
        title_en = item.get("title_en", "")
        summary = item.get("summary", "") or title_en

        if title_en and looks_untranslated(item.get("title_pt", ""), title_en):
            texts_to_translate.append(title_en)
        if summary and summary != title_en and looks_untranslated(item.get("summary_pt", ""), summary):
            texts_to_translate.append(summary)

    translations = {}
    if texts_to_translate:
        unique_texts = list(dict.fromkeys(texts_to_translate))
        batch_size = 10
        for i in range(0, len(unique_texts), batch_size):
            batch = unique_texts[i:i + batch_size]
            translations.update(translate_batch_with_gemini(batch))

    changed = False
    for item in news_list:
        title_en = item.get("title_en", "")
        summary = item.get("summary", "") or title_en

        if title_en and looks_untranslated(item.get("title_pt", ""), title_en):
            item["title_pt"] = translations.get(title_en, translate_headline_heuristic(title_en))
            changed = True

        if summary and summary != title_en and looks_untranslated(item.get("summary_pt", ""), summary):
            item["summary_pt"] = translations.get(summary, item.get("title_pt", ""))
            changed = True

        ensure_portuguese_fields(item)
        item_id = item.get("id")
        if item_id:
            cache[item_id] = item

    if changed and cache:
        save_cache(cache)

    return news_list


def translate_batch_with_gemini(headlines):
    """Traduz uma lista de manchetes em lote usando a API do Gemini."""
    if not gemini_available or not headlines:
        return translate_batch_fallback(headlines)

    prompt = (
        "Você é um tradutor especializado em mercado financeiro global e macroeconomia.\n"
        "Sua tarefa é traduzir a lista de manchetes abaixo do inglês para o português do Brasil.\n"
        "Regras cruciais:\n"
        "1. Faça uma tradução direta, natural e profissional adequada para jornalismo financeiro em português.\n"
        "2. Preserve siglas e jargões financeiros padrão quando apropriado (ex: Fed, BCE, BOJ, SOFR, payroll, Treasuries, copom, etc.).\n"
        "3. Remova qualquer prefixo como 'FinancialJuice:' ou 'Financial Juice:'.\n"
        "4. Retorne APENAS um objeto JSON válido contendo um dicionário onde a chave é a manchete original em inglês e o valor é a tradução em português. Não inclua blocos de código markdown como ```json ou qualquer outro texto explicativo, apenas o JSON bruto.\n\n"
        f"Manchetes a traduzir:\n{json.dumps(headlines, ensure_ascii=False)}"
    )

    try:
        model = genai.GenerativeModel('gemini-2.0-flash')
        response = model.generate_content(prompt)
        
        text_response = response.text.strip()
        # Remove tags markdown do JSON se o modelo as incluir
        if text_response.startswith("```"):
            text_response = re.sub(r"^```(?:json)?\n", "", text_response)
            text_response = re.sub(r"\n```$", "", text_response)
            
        translated_dict = json.loads(text_response.strip())
        logger.info(f"Traduzidas com sucesso {len(headlines)} notícias via Gemini em lote.")
        return translated_dict
    except Exception as e:
        logger.error(f"Erro ao traduzir em lote com Gemini: {e}. Usando tradução heurística.")
        # Retorna heurística como fallback
        return translate_batch_fallback(headlines)


def fetch_financial_juice_news(limit=50, min_network_interval=60, fast_mode=False):
    """Busca as notícias do Financial Juice, traduz os novos registros e os retorna com network throttle."""
    cache = load_cache()
    now = datetime.now().timestamp()
    last_fetch = cache.get("last_network_fetch", 0)
    
    # Se o último fetch de rede foi há menos de 60 segundos, usa o cache local para evitar 429
    if now - last_fetch < min_network_interval:
        logger.info("Mecanismo de throttling ativo. Carregando noticias do cache local para evitar erro 429.")
        news_list = [v for k, v in cache.items() if k != "last_network_fetch"]
        # Filtra dicionários válidos (em caso de lixo no cache)
        news_list = [n for n in news_list if isinstance(n, dict) and "timestamp" in n]
        if fast_mode:
            for item in news_list:
                ensure_portuguese_fields(item)
        else:
            news_list = normalize_news_translations(news_list, cache)
        news_list.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
        return news_list[:limit]
        
    logger.info("Buscando notícias frescas do Financial Juice via rede...")
    
    try:
        # Faz parse do RSS de forma resiliente
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }
        feed = None
        network_success = False
        try:
            res = requests.get(RSS_URL, headers=headers, timeout=5 if fast_mode else 10)
            if res.status_code == 200:
                feed = feedparser.parse(res.content)
                logger.info(f"Feed RSS baixado via requests com sucesso. Status: {res.status_code}")
                network_success = True
            else:
                logger.warning(f"Erro HTTP {res.status_code} ao buscar feed. Tentando feedparser direto.")
        except Exception as req_err:
            logger.warning(f"Falha na requisicao do feed via requests: {req_err}. Tentando feedparser direto.")
            
        if not feed or not feed.entries:
            feed = feedparser.parse(RSS_URL)
            if feed.entries:
                network_success = True
                
        # Atualiza a marcação do tempo do último fetch de rede no cache
        if network_success:
            cache["last_network_fetch"] = now
        else:
            # Em caso de falha, definimos um cooldown curto (30s) antes de tentar de novo
            cache["last_network_fetch"] = now - 30
            save_cache(cache)
            
        if not feed or not feed.entries:
            logger.warning("Nenhuma notícia nova encontrada via rede. Retornando cache local.")
            # Se falhar o RSS, retornamos o que temos no cache ordenado por tempo
            cached_news = [v for k, v in cache.items() if k != "last_network_fetch"]
            cached_news = [n for n in cached_news if isinstance(n, dict) and "timestamp" in n]
            if fast_mode:
                for item in cached_news:
                    ensure_portuguese_fields(item)
            else:
                cached_news = normalize_news_translations(cached_news, cache)
            cached_news.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
            return cached_news[:limit]
            
        entries_to_process = feed.entries[:limit]
        
        # Identifica notícias não traduzidas
        untranslated_headlines = []
        news_list = []
        
        for entry in entries_to_process:
            title = entry.get("title", "")
            clean_title = re.sub(r"^(FinancialJuice|Financial Juice):\s*", "", title).strip()
            
            # Gera um ID único
            link = entry.get("link", "")
            news_id = re.search(r"News/(\d+)/", link)
            news_id = news_id.group(1) if news_id else clean_title
            
            pub_date_parsed = entry.get("published_parsed")
            if pub_date_parsed:
                pub_date = datetime(*pub_date_parsed[:6])
            else:
                pub_date = datetime.now()
                
            # Ajusta fuso horário se necessário (normalmente GMT para o RSS do Financial Juice)
            # Vamos manter datetime e formatar
            pub_date_str = pub_date.strftime("%H:%M:%S")
            
            news_item = {
                "id": news_id,
                "title_en": clean_title,
                "title_pt": "",
                "link": link,
                "published_str": pub_date_str,
                "timestamp": pub_date.timestamp(),
                "summary": entry.get("description", "").strip() or clean_title,
            }
            
            news_list.append(news_item)
            
            # Se não está no cache, adiciona para tradução
            if news_id not in cache:
                untranslated_headlines.append(clean_title)
                
        # Traduz as novas manchetes
        if untranslated_headlines:
            logger.info(f"Encontradas {len(untranslated_headlines)} novas notícias para tradução.")
            for item in news_list:
                if item["id"] not in cache:
                    summary = item.get("summary", "").strip()
                    if summary and summary != item.get("title_en", "").strip():
                        untranslated_headlines.append(summary)

            # Remove duplicatas
            untranslated_headlines = list(set(untranslated_headlines))
            
            # Divide em lotes de no máximo 15 para não estourar tokens do modelo
            batch_size = 15
            translations = {}
            if not fast_mode:
                for i in range(0, len(untranslated_headlines), batch_size):
                    batch = untranslated_headlines[i:i+batch_size]
                    batch_translations = translate_batch_with_gemini(batch)
                    translations.update(batch_translations)
                
            # Salva no cache
            for item in news_list:
                item_id = item["id"]
                if item_id not in cache:
                    original = item["title_en"]
                    translated = translations.get(original, translate_headline_heuristic(original))
                    item["title_pt"] = translated
                    summary = item.get("summary", "").strip()
                    if summary and summary != original:
                        item["summary_pt"] = translations.get(summary, item["title_pt"])
                    ensure_portuguese_fields(item)
                    # Salva no cache com metadados completos
                    cache[item_id] = item
                else:
                    # Carrega a tradução que já estava no cache
                    item["title_pt"] = cache[item_id]["title_pt"]
                    item["summary_pt"] = cache[item_id].get("summary_pt", "")
                    # Preserva timestamps originais para consistência
                    item["timestamp"] = cache[item_id]["timestamp"]
                    ensure_portuguese_fields(item)
                    cache[item_id] = item
            
            save_cache(cache)
        else:
            # Todas estão no cache, apenas carrega as traduções
            for item in news_list:
                item_id = item["id"]
                if item_id in cache:
                    item["title_pt"] = cache[item_id]["title_pt"]
                    item["summary_pt"] = cache[item_id].get("summary_pt", "")
                    item["timestamp"] = cache[item_id]["timestamp"]
                    ensure_portuguese_fields(item)
                    cache[item_id] = item
                else:
                    item["title_pt"] = translate_headline_heuristic(item["title_en"])
                    ensure_portuguese_fields(item)
                    cache[item_id] = item
                    
        # Ordena por timestamp de publicação decrescente
            save_cache(cache)

        if fast_mode:
            for item in news_list:
                ensure_portuguese_fields(item)
        else:
            news_list = normalize_news_translations(news_list, cache)
        news_list.sort(key=lambda x: x["timestamp"], reverse=True)
        return news_list
        
    except Exception as e:
        logger.error(f"Erro ao buscar notícias do Financial Juice: {e}")
        # Retorna o cache local como fallback de emergência
        cached_news = [v for k, v in cache.items() if k != "last_network_fetch"]
        cached_news = [n for n in cached_news if isinstance(n, dict) and "timestamp" in n]
        if fast_mode:
            for item in cached_news:
                ensure_portuguese_fields(item)
        else:
            cached_news = normalize_news_translations(cached_news, cache)
        cached_news.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
        return cached_news[:limit]


if __name__ == "__main__":
    print("Testando busca e tradução de notícias do Financial Juice...")
    news = fetch_financial_juice_news(limit=5)
    for i, item in enumerate(news, 1):
        print(f"\n{i}. [{item['published_str']}] {item['title_en']}")
        print(f"   Tradução: {item['title_pt']}")
