# main_pgvector.py

# Imports
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from langchain_community.embeddings.ollama import OllamaEmbeddings
from langchain_community.vectorstores import PGVector

from minio import Minio
from minio.error import S3Error
from pypdf import PdfReader

import argparse
import io
import psycopg2

# Configurações MinIO
MINIO_SETTINGS = {
    "endpoint": "localhost:9000",
    "access_key": "admin",
    "secret_key": "admin123",
    "secure": False,
    "bucket": "unstructured",
}

# Configurações PostgreSQL
DB_SETTINGS = {
    "host": "localhost",
    "port": 5433,
    "database": "projeto_db",
    "user": "projeto_utilizador",
    "password": "projeto",
}

TABLE_NAME = "documents"

# Função de embeddings
def get_embedding_function():
    return OllamaEmbeddings(model="mxbai-embed-large")

# Diagnóstico MinIO
def diagnose_minio():
    print("\n A verificar ligação ao MinIO...")
    try:
        client = Minio(
            MINIO_SETTINGS["endpoint"],
            access_key=MINIO_SETTINGS["access_key"],
            secret_key=MINIO_SETTINGS["secret_key"],
            secure=MINIO_SETTINGS["secure"],
        )

        # Listar todos os buckets
        buckets = client.list_buckets()
        print(f" Ligação OK. Buckets encontrados: {[b.name for b in buckets]}")

        bucket = MINIO_SETTINGS["bucket"]

        if not client.bucket_exists(bucket):
            print(f" Bucket '{bucket}' NÃO existe!")
            return False

        print(f" Bucket '{bucket}' existe.")

        # Listar TODOS os objetos (com e sem recursive)
        print(f"\n Objetos no bucket '{bucket}' (recursive=True):")
        count = 0
        for obj in client.list_objects(bucket, recursive=True):
            print(f"   - {obj.object_name}  ({obj.size} bytes)")
            count += 1

        if count == 0:
            print("     Bucket está vazio!")
        else:
            print(f"   Total: {count} objetos")

        return count > 0

    except S3Error as e:
        print(f" Erro S3: {e}")
        return False
    except Exception as e:
        print(f" Erro de ligação: {e}")
        return False

# 🔹 Carregar PDFs do MinIO
def load_documents_from_minio() -> list[Document]:
    client = Minio(
        MINIO_SETTINGS["endpoint"],
        access_key=MINIO_SETTINGS["access_key"],
        secret_key=MINIO_SETTINGS["secret_key"],
        secure=MINIO_SETTINGS["secure"],
    )

    documents = []
    bucket = MINIO_SETTINGS["bucket"]
    objects = list(client.list_objects(bucket, recursive=True))

    print(f"\n Total de objetos encontrados: {len(objects)}")

    for obj in objects:
        name = obj.object_name
        print(f"   → {name} | é PDF: {name.lower().endswith('.pdf')}")

        if not name.lower().endswith(".pdf"):
            continue

        print(f" A carregar: {name}")

        try:
            response = client.get_object(bucket, name)
            pdf_bytes = io.BytesIO(response.read())
            response.close()
            response.release_conn()

            reader = PdfReader(pdf_bytes)
            print(f"   Páginas: {len(reader.pages)}")

            for page_num, page in enumerate(reader.pages):
                text = page.extract_text() or ""
                if text.strip():
                    documents.append(Document(
                        page_content=text,
                        metadata={
                            "source": name,
                            "page": page_num,
                        }
                    ))
                else:
                    print(f"     Página {page_num} sem texto extraível (pode ser imagem/scan)")

        except Exception as e:
            print(f"  Erro ao processar {name}: {e}")

    print(f"\n {len(documents)} páginas com texto carregadas do MinIO")
    return documents

#  Dividir documentos em chunks
def split_documents(documents: list[Document]) -> list[Document]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50,
        length_function=len,
        is_separator_regex=False,
    )

    chunks = splitter.split_documents(documents)

    for chunk in chunks:
        if len(chunk.page_content) > 1000:
            chunk.page_content = chunk.page_content[:1000]

    return chunks

#  Gerar IDs únicos para cada chunk
def calculate_chunk_ids(chunks: list[Document]) -> list[Document]:
    last_page_id = None
    current_chunk_index = 0

    for chunk in chunks:
        source = chunk.metadata.get("source")
        page = chunk.metadata.get("page")
        current_page_id = f"{source}:{page}"

        if current_page_id == last_page_id:
            current_chunk_index += 1
        else:
            current_chunk_index = 0

        chunk.metadata["id"] = f"{current_page_id}:{current_chunk_index}"
        last_page_id = current_page_id

    return chunks

#  Limpar tabela no PostgreSQL
def clear_pgvector():
    conn = psycopg2.connect(
        host=DB_SETTINGS["host"],
        port=DB_SETTINGS["port"],
        dbname=DB_SETTINGS["database"],
        user=DB_SETTINGS["user"],
        password=DB_SETTINGS["password"],
    )
    cur = conn.cursor()
    cur.execute(f"DROP TABLE IF EXISTS {TABLE_NAME} CASCADE;")
    conn.commit()
    cur.close()
    conn.close()
    print(f" Tabela '{TABLE_NAME}' apagada")

#  Inserir chunks no pgvector
def add_to_pgvector(chunks: list[Document]):
    chunks_with_ids = calculate_chunk_ids(chunks)

    connection_string = (
        f"postgresql://{DB_SETTINGS['user']}:{DB_SETTINGS['password']}"
        f"@{DB_SETTINGS['host']}:{DB_SETTINGS['port']}/{DB_SETTINGS['database']}"
    )

    PGVector.from_documents(
        documents=chunks_with_ids,
        embedding=get_embedding_function(),
        connection_string=connection_string,
        collection_name=TABLE_NAME,
        pre_delete_collection=False,
    )

    print(f" {len(chunks_with_ids)} chunks inseridos na tabela '{TABLE_NAME}'")

#  Main
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="Apaga e recria a tabela antes de inserir.")
    args = parser.parse_args()

    if args.reset:
        clear_pgvector()

    # Diagnóstico primeiro
    ok = diagnose_minio()
    if not ok:
        print("\n Corrige os problemas acima antes de continuar.")
        return

    documents = load_documents_from_minio()

    if not documents:
        print("\n  Nenhum documento com texto encontrado.")
        print("   Causas possíveis:")
        print("   1. Os PDFs são scans/imagens (precisas de OCR)")
        print("   2. Os ficheiros não têm extensão .pdf")
        print("   3. Os PDFs estão em subpastas não listadas")
        return

    chunks = split_documents(documents)
    add_to_pgvector(chunks)

if __name__ == "__main__":
    main()