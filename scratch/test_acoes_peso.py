import win32com.client
import sys

# Garante saída UTF-8 no terminal
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

def test_read():
    try:
        excel = win32com.client.GetActiveObject("Excel.Application")
        wb = None
        for w in excel.Workbooks:
            if "dashboard_trade_bloomberg_semaforo" in w.Name:
                wb = w
                break
        
        if not wb:
            print("Planilha 'dashboard_trade_bloomberg_semaforo' não encontrada aberta.")
            return
            
        sheet = wb.ActiveSheet
        print(f"Lendo planilha ativa: {sheet.Name}")
        
        print("\n--- Lendo Ações de Maior Peso (A55:G59) ---")
        vals = sheet.Range("A55:G59").Value
        for row in vals:
            # Substitui caracteres especiais para printar sem erro
            safe_row = [str(x).replace('▲', '[UP]').replace('▼', '[DOWN]') for x in row]
            print(" | ".join(safe_row))
            
    except Exception as e:
        print(f"Erro: {e}")

if __name__ == "__main__":
    test_read()
