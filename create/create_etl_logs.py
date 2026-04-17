import psycopg2


def main():
    # -------------------------
    # Conexão
    # -------------------------
    conn = psycopg2.connect(
        host="localhost",
        port=5433,
        dbname="projeto_db",
        user="projeto_utilizador",
        password="projeto"
    )
    cur = conn.cursor()

    # -------------------------
    # Create Table
    # -------------------------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS etl_logs (
        id SERIAL PRIMARY KEY,
        file_name VARCHAR,
        step VARCHAR,
        status VARCHAR,
        error_message TEXT,
        log_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    conn.commit()

    # -------------------------
    # Close Connection
    # -------------------------
    cur.close()
    conn.close()

    print("ETL logs control table created successfully")


# -------------------------
# Entry point
# -------------------------
if __name__ == "__main__":
    main()