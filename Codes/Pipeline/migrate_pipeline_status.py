"""
One-time migration: adiciona pipeline_status e pipeline_error a op_data
e marca DONE os ficheiros já processados com sucesso.
"""
import psycopg2

DB_CONFIG = {
    "host": "localhost", "port": 5433, "dbname": "gestao_db",
    "user": "projeto_utilizador", "password": "projeto",
}

def main():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    print("1. A adicionar colunas...")
    cur.execute("""
        ALTER TABLE op_data
        ADD COLUMN IF NOT EXISTS pipeline_status TEXT NOT NULL DEFAULT 'PENDING'
    """)
    cur.execute("""
        ALTER TABLE op_data
        ADD COLUMN IF NOT EXISTS pipeline_error TEXT
    """)
    conn.commit()
    print("   Colunas adicionadas.")

    print("2. A marcar DONE os ficheiros já processados sem erros...")
    cur.execute("""
        UPDATE op_data
        SET pipeline_status = 'DONE'
        WHERE created_at <= (
            SELECT last_run FROM etl_data WHERE process_name = 'etl_dados'
        )
        AND file_id::text NOT IN (
            SELECT DISTINCT file_id FROM etl_logs_dados WHERE file_id IS NOT NULL
        )
    """)
    done_count = cur.rowcount
    conn.commit()
    print(f"   {done_count} ficheiros marcados como DONE.")

    print("3. Contagens finais:")
    cur.execute("SELECT pipeline_status, COUNT(*) FROM op_data GROUP BY pipeline_status ORDER BY pipeline_status")
    for status, count in cur.fetchall():
        print(f"   {status}: {count}")

    cur.close()
    conn.close()
    print("Migração concluída.")


if __name__ == "__main__":
    main()
