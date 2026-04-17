import requests
import psycopg2
import boto3

def main():

    print("A correr ingest_raw...")

    # Conexão MinIO
    s3 = boto3.client(
        's3',
        endpoint_url='http://localhost:9000',
        aws_access_key_id='admin',
        aws_secret_access_key='admin123'
    )

    # Conexão Postgres
    conn = psycopg2.connect(
        host="localhost",
        port=5433,
        dbname="projeto_db",
        user="projeto_utilizador",
        password="projeto"
    )

    cur = conn.cursor()

    # ── 1. Obter last_run ────────────────────────────────────────────────────
    cur.execute("""
        SELECT last_run
        FROM etl_data
        WHERE process_name = 'etl_main';
    """)
    last_run = cur.fetchone()[0]

    # ── 2. Buscar apenas novos registos desde last_run ───────────────────────
    cur.execute("""
        SELECT file_id, file_name, file_url, file_type
        FROM op_data
        WHERE created_at > %s;
    """, (last_run,))

    rows = cur.fetchall()

    session = requests.Session() # Cria a sessão antes do loop
    
    # ── 3. Processar cada ficheiro ───────────────────────────────────────────
    for file_id, file_name, file_url, file_type in rows:
        try:
            response = session.get(file_url, timeout=30)
            response.raise_for_status()

            s3.put_object(
                Bucket="raw",
                Key=file_name,
                Body=response.content,
                Metadata={
                    "file_id": str(file_id),
                    "file_type": file_type or "unknown",
                    "source_url": file_url
                }
            )

            cur.execute("""
                INSERT INTO etl_logs (file_name, step, status, error_message)
                VALUES (%s, %s, %s, %s)
            """, (file_name, 'ingest_raw', 'success', None))

            print(f"[OK]    {file_name}")

        except Exception as e:
            cur.execute("""
                INSERT INTO etl_logs (file_id, file_name, step, status, error_message)
                VALUES (%s, %s, %s, %s, %s)
            """, (file_id, file_name, 'ingest_raw', 'error', str(e)))

            print(f"[ERRO]  {file_name} → {e}")

    conn.commit()
    cur.close()
    conn.close()

if __name__ == "__main__":
    main()