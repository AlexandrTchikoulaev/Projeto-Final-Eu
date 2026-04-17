import psycopg2

conn = psycopg2.connect(
    host="localhost",
    port="5433",
    dbname="projeto_db",
    user="projeto_utilizador",
    password="projeto"
)

cur = conn.cursor()

try:
    print("⚠️ A apagar todas as tabelas...")

    # Vai buscar todas as tabelas do schema público
    cur.execute("""
        SELECT tablename
        FROM pg_tables
        WHERE schemaname = 'public';
    """)

    tables = cur.fetchall()

    for table in tables:
        table_name = table[0]
        print(f"🗑️ A apagar tabela: {table_name}")
        cur.execute(f'DROP TABLE IF EXISTS "{table_name}" CASCADE;')

    conn.commit()
    print("✅ Todas as tabelas foram apagadas!")

except Exception as e:
    conn.rollback()
    print("❌ Erro:", e)

finally:
    cur.close()
    conn.close()