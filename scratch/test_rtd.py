import win32com.client

try:
    excel = win32com.client.GetActiveObject("Excel.Application")
    wb = excel.ActiveWorkbook
    sheet = excel.ActiveSheet
    print(f"Workbook ativo: {wb.Name}")
    print(f"Sheet ativa: {sheet.Name}")
    
    # Lista valores de células próximas para diagnóstico
    cells = ["I5", "I6", "I7", "H6", "J6", "L3", "L4", "L5", "L6"]
    for c in cells:
        val = sheet.Range(c).Value
        print(f"Célula {c}: {val} (Tipo: {type(val)})")
        
except Exception as e:
    print(f"Erro ao conectar ao Excel: {e}")
