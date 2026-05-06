import logging
import os
from datetime import datetime

def setup_logger(name, log_file=None):
    """Configura um logger que escreve no console e opcionalmente em um arquivo."""
    if not log_file:
        if not os.path.exists(".tmp"):
            os.makedirs(".tmp")
        log_file = f".tmp/{name}_{datetime.now().strftime('%Y%m%d')}.log"
        
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    # Formato do log
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Handler para Console
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # Handler para Arquivo
    try:
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        print(f"Erro ao configurar log em arquivo: {e}")
        
    return logger
