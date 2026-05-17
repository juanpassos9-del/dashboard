import os
import subprocess
import signal

try:
    # Utiliza o tasklist do Windows para encontrar processos Python
    cmd = 'wmic process where "name=\'python.exe\'" get ProcessID, CommandLine'
    output = subprocess.check_output(cmd, shell=True).decode('utf-8', errors='ignore')
    
    lines = output.strip().split('\n')
    killed = False
    for line in lines[1:]:
        if not line.strip():
            continue
        parts = line.strip().split()
        pid = parts[-1]
        cmdline = " ".join(parts[:-1])
        
        if "dashboard_bridge.py" in cmdline:
            print(f"Encontrado dashboard_bridge.py rodando no PID: {pid}. Finalizando...")
            os.kill(int(pid), signal.SIGTERM)
            killed = True
            
    if not killed:
        print("Nenhum processo antigo do dashboard_bridge.py rodando em background.")
except Exception as e:
    print(f"Erro ao finalizar bridge: {e}")
