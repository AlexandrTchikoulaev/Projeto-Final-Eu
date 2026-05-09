"""
Orquestrador do pipeline de dados não estruturados (PDFs).
Executa sequencialmente:
  1. validate_op_report        — valida registos em op_report antes de ingerir
  2. bronze                    — descarrega PDFs para o bucket bronze-unstructured
  3. validate_bronze_unstructured — valida PDFs no bucket bronze-unstructured
  4. silver                    — processa PDFs e indexa embeddings na BD vetorial
"""
import sys
import os
import psycopg2
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DB_CONFIG = {
    "host": "localhost",
    "port": 5433,
    "dbname": "pipeline_db",
    "user": "projeto_utilizador",
    "password": "projeto",
}

PROCESS_NAME = "etl_pdfs"


def update_timestamp():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute("""
        UPDATE etl_data SET last_run = CURRENT_TIMESTAMP
        WHERE process_name = %s
    """, (PROCESS_NAME,))
    conn.commit()
    cur.close()
    conn.close()
    print("Timestamp etl_pdfs atualizado.")


def run_step(label: str, fn):
    print(f"\n{'='*50}")
    print(f" {label}")
    print(f"{'='*50}")
    try:
        result = fn()
        print(f"[OK] {label} concluído.")
        return result
    except Exception as e:
        print(f"[ERRO] {label} falhou: {e}")
        raise


def get_prev_last_run():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute("SELECT last_run FROM etl_data WHERE process_name = %s", (PROCESS_NAME,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        return row[0] if row else None
    except Exception:
        return None


def run_pipeline():
    import validate_op_report
    import bronze
    import validate_bronze_unstructured
    import silver

    run_start     = datetime.now()
    prev_last_run = get_prev_last_run()

    print("\n PIPELINE DE PDFs INICIADO")
    print(f" {run_start.strftime('%Y-%m-%d %H:%M:%S')}\n")

    # 1. Validar op_report antes de ingerir
    run_step("1/4 — validate_op_report", validate_op_report.validate)

    # 2. Descarregar PDFs para bronze-unstructured
    run_step("2/4 — bronze", bronze.main)

    # 3. Validar PDFs no bucket bronze-unstructured
    run_step("3/4 — validate_bronze_unstructured", validate_bronze_unstructured.validate)

    # 4. Indexar embeddings na BD vetorial
    run_step("4/4 — silver", silver.main)

    # Atualizar timestamp
    update_timestamp()

    print("\n PIPELINE DE PDFs CONCLUÍDO COM SUCESSO")


if __name__ == "__main__":
    run_pipeline()
