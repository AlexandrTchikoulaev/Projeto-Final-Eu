import psycopg2
import boto3


# =========================
# 🗄️ POSTGRES RESET
# =========================
def drop_postgres_objects():
    conn = psycopg2.connect(
        host="localhost",
        port=5433,
        dbname="projeto_db",
        user="projeto_utilizador",
        password="projeto"
    )

    cur = conn.cursor()

    print("🧨 A apagar tabelas e views no PostgreSQL...")

    # 🔥 DROP VIEWS (se existirem)
    cur.execute("""
        DO $$ 
        DECLARE r RECORD;
        BEGIN
            FOR r IN (SELECT viewname FROM pg_views WHERE schemaname = 'public') LOOP
                EXECUTE 'DROP VIEW IF EXISTS ' || quote_ident(r.viewname) || ' CASCADE';
            END LOOP;
        END $$;
    """)

    # 🔥 DROP TABLES
    cur.execute("""
        DO $$
        DECLARE r RECORD;
        BEGIN
            FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') LOOP
                EXECUTE 'DROP TABLE IF EXISTS ' || quote_ident(r.tablename) || ' CASCADE';
            END LOOP;
        END $$;
    """)

    conn.commit()
    cur.close()
    conn.close()

    print("✅ PostgreSQL limpo")


# =========================
# 🪣 MINIO RESET
# =========================
def clear_minio():
    s3 = boto3.client(
        's3',
        endpoint_url='http://localhost:9000',
        aws_access_key_id='admin',
        aws_secret_access_key='admin123'
    )

    buckets = ['raw', 'unstructured', 'transformed']

    print("🧨 A apagar buckets MinIO...")

    for bucket in buckets:

        # apagar todos os objetos
        try:
            paginator = s3.get_paginator('list_objects_v2')

            for page in paginator.paginate(Bucket=bucket):
                if 'Contents' in page:
                    objects = [{'Key': obj['Key']} for obj in page['Contents']]

                    s3.delete_objects(
                        Bucket=bucket,
                        Delete={'Objects': objects}
                    )

            # apagar bucket
            s3.delete_bucket(Bucket=bucket)

            print(f"🗑️ Bucket eliminado: {bucket}")

        except Exception as e:
            print(f"⚠️ Erro no bucket {bucket}: {e}")


# =========================
# 🚀 MAIN
# =========================
def run_reset():
    print("\n🚨 INICIAR RESET TOTAL DO SISTEMA 🚨\n")

    drop_postgres_objects()
    clear_minio()

    print("\n🎉 RESET COMPLETO - sistema limpo!")


if __name__ == "__main__":
    run_reset()