import subprocess
import sys
import psycopg2
from datetime import datetime
import os

def update_etl_timestamp():
    conn = psycopg2.connect(
        host="localhost",
        port=5433,
        dbname="projeto_db",
        user="projeto_utilizador",
        password="projeto"
    )
    cur = conn.cursor()

    cur.execute("""
    UPDATE etl_data
    SET last_run = CURRENT_TIMESTAMP
    WHERE process_name = 'etl_main';
    """)

    conn.commit()
    cur.close()
    conn.close()

    print("ETL timestamp atualizado")
    
def run_script(script_name):

    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

    script_path = os.path.join(BASE_DIR, script_name)

    print(f"\n A correr: {script_name}")

    # Remover o capture_output para os prints do ficheiro (ex: load.py) aparecerem na hora
    result = subprocess.run(
        [sys.executable, script_path],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print(f"Erro em {script_name}")
        print(result.stderr)
        exit(1)

    print(f"✅ Concluído: {script_name}")


def run_pipeline():
    run_script("ingest_raw.py")
    #run_script("ingest_unstructured.py")
    run_script("transform.py")
    run_script("load.py")

    # atualizar timestamp no fim
    update_etl_timestamp()

    print("\n ETL COMPLETO COM SUCESSO")


if __name__ == "__main__":
    run_pipeline()