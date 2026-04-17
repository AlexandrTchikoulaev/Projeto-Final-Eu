import json
import pandas as pd
import boto3
import io
import psycopg2
from sqlalchemy import create_engine

# ===============================
# MinIO (S3)
# ===============================
s3 = boto3.client(
    's3',
    endpoint_url='http://localhost:9000',
    aws_access_key_id='admin',
    aws_secret_access_key='admin123'
)

# ===============================
# PostgreSQL
# ===============================
engine = create_engine(
    "postgresql+psycopg2://projeto_utilizador:projeto@localhost:5433/projeto_db"
)

conn = psycopg2.connect(
    host="localhost",
    port=5433,
    dbname="projeto_db",
    user="projeto_utilizador",
    password="projeto"
)

cur = conn.cursor()

def log_etl(file_name, step, status, error_message=None):
    cur.execute("""
        INSERT INTO etl_logs (file_name, step, status, error_message)
        VALUES (%s, %s, %s, %s)
    """, (file_name, step, status, error_message))

# ===============================
# Funções de transformação
# ===============================

def funcao_imf_indicadores(data):
    items = data.get("indicators", {})

    codigos, nomes = [], []

    for codigo, info in items.items():
        codigos.append(codigo)
        nomes.append(info.get("label"))

    return pd.DataFrame({
        "code": codigos,
        "name": nomes
    })


def funcao_imf_countries(data):
    items = data.get("countries", {})

    codigos, nomes = [], []

    for codigo, info in items.items():
        codigos.append(codigo)
        nomes.append(info.get("label"))

    return pd.DataFrame({
        "code": codigos,
        "name": nomes
    })


def funcao_imf_regions(data):
    items = data.get("regions", {})

    codigos, nomes = [], []

    for codigo, info in items.items():
        codigos.append(codigo)
        nomes.append(info.get("label"))

    return pd.DataFrame({
        "code": codigos,
        "name": nomes
    })


def funcao_imf_groups(data):
    items = data.get("groups", {})

    codigos, nomes = [], []

    for codigo, info in items.items():
        codigos.append(codigo)
        nomes.append(info.get("label"))

    return pd.DataFrame({
        "code": codigos,
        "name": nomes
    })


def funcao_imf_values(data):
    values = data.get("values", {})

    lista = [
        {
            "location_code": location_code,
            "indicator_code": indicator_code,
            "year": int(year),
            "value": float(value) if value is not None else None,
            "value_type": "value"
        }
        for indicator_code, locations in values.items()
        for location_code, years in locations.items()
        for year, value in years.items()
    ]

    return pd.DataFrame(lista)


# ===============================
# Obter last_run
# ===============================
cur.execute("""
SELECT last_run
FROM etl_data
WHERE process_name = 'etl_main';
""")

last_run = cur.fetchone()[0]

# ===============================
# Mapping incremental
# ===============================
cur.execute("""
SELECT file_name, extract_function
FROM op_data
WHERE created_at > %s;
""", (last_run,))

mapping_funcoes = {
    file_name: extract_function
    for file_name, extract_function in cur.fetchall()
}

# ===============================
# Pipeline de transformação
# ===============================
def transformar():

    if not mapping_funcoes:
        print("Sem novos ficheiros para transformar.")
        return

    for ficheiro, nome_funcao in mapping_funcoes.items():

        print(f"A processar: {ficheiro}")

        if nome_funcao not in globals():
            print(f"Função não existe: {nome_funcao}")
            log_etl(ficheiro, 'transform', 'error', f"Função não existe: {nome_funcao}")
            continue

        funcao_extracao = globals()[nome_funcao]

        try:
            response = s3.get_object(Bucket="raw", Key=ficheiro)
            dados = json.load(response['Body'])
        except Exception as e:
            print(f"Erro ao ler {ficheiro}: {e}")
            log_etl(ficheiro, 'transform', 'error', str(e))
            continue

        df = funcao_extracao(dados)

        if df is None or df.empty:
            print(f"DataFrame vazio: {ficheiro}")
            log_etl(ficheiro, 'transform', 'error', "DataFrame vazio")
            continue

        buffer = io.BytesIO()
        df.to_parquet(buffer, index=False)
        buffer.seek(0)

        nome_parquet = ficheiro.rsplit(".", 1)[0] + ".parquet"

        s3.put_object(
            Bucket="transformed",
            Key=nome_parquet,
            Body=buffer
        )

        print(f"Transformado: {ficheiro} -> {nome_parquet}")


# ===============================
# EXECUÇÃO
# ===============================
if __name__ == "__main__":
    try:
        transformar()
    finally:
        cur.close()
        conn.close()