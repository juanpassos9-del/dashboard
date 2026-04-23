import win32com.client
import time
import os
import sys

class RTDGateway:
    def __init__(self, workbook_name=None, sheet_name=None):
        self.excel = None
        self.workbook = None
        self.sheet = None
        self.workbook_name = workbook_name
        self.sheet_name = sheet_name

    def connect(self):
        """Conecta-se a uma instância aberta do Excel."""
        try:
            # Tenta capturar a instância do Excel que já está aberta
            self.excel = win32com.client.GetActiveObject("Excel.Application")
            
            if self.workbook_name:
                try:
                    self.workbook = self.excel.Workbooks(self.workbook_name)
                except:
                    try:
                        self.workbook = self.excel.Workbooks(self.workbook_name + ".xlsx")
                    except:
                        self.workbook = self.excel.Workbooks(self.workbook_name + ".xlsm")
            else:
                self.workbook = self.excel.ActiveWorkbook
            
            if self.sheet_name:
                self.sheet = self.workbook.Sheets(self.sheet_name)
            else:
                self.sheet = self.workbook.ActiveSheet
                
            print(f"[*] Conectado com sucesso ao Excel: {self.workbook.Name} -> {self.sheet.Name}")
            return True
        except Exception as e:
            print(f"[!] Erro ao conectar ao Excel: {e}")
            return False

    def read_data(self, range_address):
        """Lê um range de células (ex: 'A1:C10')."""
        try:
            if not self.sheet:
                if not self.connect():
                    return None
            
            data = self.sheet.Range(range_address).Value
            return data
        except Exception as e:
            print(f"[!] Erro ao ler dados: {e}")
            self.sheet = None # Força reconexão na próxima tentativa
            return None

    def format_to_dict(self, raw_data, mapping):
        """
        Converte os dados brutos do Excel em uma lista de dicionários.
        mapping: {'Symbol': 0, 'Price': 1, 'Change': 2} (índices das colunas)
        """
        formatted = []
        if not raw_data:
            return formatted

        for row in raw_data:
            if row[mapping['Symbol']] is None:
                continue
                
            item = {
                "symbol": str(row[mapping['Symbol']]),
                "last_price": float(row[mapping['Price']]) if row[mapping['Price']] else 0.0,
                "change_percent": float(row[mapping['Change']]) if row[mapping['Change']] else 0.0
            }
            formatted.append(item)
        return formatted

if __name__ == "__main__":
    # Exemplo de uso local para teste
    gateway = RTDGateway()
    if gateway.connect():
        while True:
            # Supondo que seus dados estejam de A2 até C10
            raw = gateway.read_data("A2:C10")
            mapping = {'Symbol': 0, 'Price': 1, 'Change': 2}
            data = gateway.format_to_dict(raw, mapping)
            
            print(f"\r[*] Dados Atuais: {data}", end="")
            time.sleep(1)
