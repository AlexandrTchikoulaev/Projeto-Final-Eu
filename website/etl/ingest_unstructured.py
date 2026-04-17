import psycopg2
import requests
import boto3

# ===============================
# CONFIG DB
# ===============================
conn = psycopg2.connect(
    host="localhost",
    port=5433,
    dbname="projeto_db",
    user="projeto_utilizador",
    password="projeto"
)
cur = conn.cursor()

# ===============================
# CONFIG MINIO
# ===============================
s3 = boto3.client(
    's3',
    endpoint_url='http://localhost:9000',
    aws_access_key_id='admin',
    aws_secret_access_key='admin123'
)

BUCKET_NAME = "unstructured"

# ===============================
# ETL CONTROL
# ===============================
cur.execute("""
SELECT last_run
FROM etl_data
WHERE process_name = 'etl_main';
""")

last_run = cur.fetchone()[0]

# ===============================
# DOWNLOAD + UPLOAD PDFs
# ===============================
def ingest_pdfs():
    
    # criar bucket se não existir
    try:
        s3.head_bucket(Bucket=BUCKET_NAME)
    except:
        s3.create_bucket(Bucket=BUCKET_NAME)

    # 🔹 apenas novos reports
    cur.execute("""
        SELECT report_id, file_name, report_url
        FROM op_report
        WHERE created_at > %s
    """, (last_run,))

    rows = cur.fetchall()

    if not rows:
        print("Sem novos PDFs para ingestão.")
        return

    session = requests.Session()
    
    for report_id, file_name, report_url in rows:

        try:
            print(f"A descarregar: {report_url}")

            response = session.get(report_url, timeout=30)

            if response.status_code != 200:
                print(f"Erro ao descarregar {report_url}")
                continue

            s3.put_object(
                Bucket=BUCKET_NAME,
                Key=file_name,
                Body=response.content,
                ContentType="application/pdf"
            )

            print(f"Upload feito: {file_name}")

        except Exception as e:
            print(f"Erro com {file_name}: {e}")

    print("Ingestão concluída")


# ===============================
# EXECUÇÃO
# ===============================
if __name__ == "__main__":
    try:
        ingest_pdfs()
    finally:
        cur.close()
        conn.close()