# main_pgvector.py

# Imports
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from langchain_community.embeddings.ollama import OllamaEmbeddings
from langchain_community.vectorstores import PGVector

from minio import Minio
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

# Carregar PDFs do MinIO
def load_documents_from_minio() -> list[Document]:
    client = Minio(
        MINIO_SETTINGS["endpoint"],
        access_key=MINIO_SETTINGS["access_key"],
        secret_key=MINIO_SETTINGS["secret_key"],
        secure=MINIO_SETTINGS["secure"],
    )

    documents = []
    objects = client.list_objects(MINIO_SETTINGS["bucket"], recursive=True)

    for obj in objects:

        print(f" A carregar: {obj.object_name}")

        response = client.get_object(MINIO_SETTINGS["bucket"], obj.object_name)
        pdf_bytes = io.BytesIO(response.read())
        response.close()
        response.release_conn()

        try:
            reader = PdfReader(pdf_bytes)
            for page_num, page in enumerate(reader.pages):
                text = page.extract_text() or ""
                if text.strip():
                    documents.append(Document(
                        page_content=text,
                        metadata={
                            "source": obj.object_name,
                            "page": page_num,
                        }
                    ))
        except Exception as e:
            print(f"  Erro ao processar {obj.object_name}: {e}")

    print(f" {len(documents)} páginas carregadas do MinIO")
    return documents

# Dividir documentos em chunks
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

# Gerar IDs únicos para cada chunk
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

# Limpar tabela no PostgreSQL
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

# Inserir chunks no pgvector
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

# Main
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="Apaga e recria a tabela antes de inserir.")
    args = parser.parse_args()

    if args.reset:
        clear_pgvector()

    documents = load_documents_from_minio()

    if not documents:
        print(" Nenhum documento encontrado no bucket.")
        return

    chunks = split_documents(documents)
    add_to_pgvector(chunks)

if __name__ == "__main__":
    main()