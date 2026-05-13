"""
Corre este script UMA VEZ para criar o atalho no ambiente de trabalho.
    python criar_atalho.py
"""
import os
import sys
import subprocess

script_dir = os.path.dirname(os.path.abspath(__file__))
start_script = os.path.join(script_dir, "start.py")
pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")

desktop = os.path.join(os.path.expanduser("~"), "Desktop")
shortcut_path = os.path.join(desktop, "OP Report Manager.lnk")

ps = f"""
$ws = New-Object -ComObject WScript.Shell
$s  = $ws.CreateShortcut('{shortcut_path}')
$s.TargetPath       = '{pythonw}'
$s.Arguments        = '"{start_script}"'
$s.WorkingDirectory = '{script_dir}'
$s.Description      = 'Inicia o OP Report Manager'
$s.Save()
"""

subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)
print(f"Atalho criado: {shortcut_path}")
print("Agora podes fechar isto. O ícone está no ambiente de trabalho.")
