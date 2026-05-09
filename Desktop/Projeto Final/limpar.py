from pathlib import Path

def limpar_pasta(pasta, substring="na", dry_run=True):
    pasta = Path(pasta)

    if not pasta.exists():
        print(f"Pasta não existe: {pasta}")
        return

    for ficheiro in pasta.iterdir():
        if ficheiro.is_file():
            if substring not in ficheiro.name:
                if dry_run:
                    print(f"[DRY-RUN] Apagaria: {ficheiro.name}")
                else:
                    print(f"Apagado: {ficheiro.name}")
                    ficheiro.unlink()

# TUA PASTA
pasta_x = r"C:\Users\optil\Desktop\Projeto Final\Dados\Dados\EPI"

# primeiro simulação (recomendado)
limpar_pasta(pasta_x, substring="na", dry_run=True)

# quando tiveres a certeza:
limpar_pasta(pasta_x, substring="na", dry_run=False)