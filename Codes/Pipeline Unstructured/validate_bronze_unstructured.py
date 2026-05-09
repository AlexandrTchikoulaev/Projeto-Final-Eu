"""
Valida os PDFs presentes no bucket bronze-unstructured.
Verifica metadados e integridade do conteúdo PDF.
Remove objetos inválidos e regista erros em etl_logs_pdfs.
"""
import psycopg2
import boto3

DB_OPERATIONAL = {
    "host": "localhost",
    "port": 5433,
    "dbname": "operational_db",
    "user": "projeto_utilizador",
    "password": "projeto",
}

DB_PIPELINE = {
    "host": "localhost",
    "port": 5433,
    "dbname": "pipeline_db",
    "user": "projeto_utilizador",
    "password": "projeto",
}

MINIO_CONFIG = {
    "endpoint_url": "http://localhost:9002",
    "aws_access_key_id": "admin",
    "aws_secret_access_key": "admin123",
}

BUCKET_UNSTRUCTURED = "bronze-unstructured"


def validate():
    conn_op   = psycopg2.connect(**DB_OPERATIONAL)
    cur_op    = conn_op.cursor()
    conn_pipe = psycopg2.connect(**DB_PIPELINE)
    cur_pipe  = conn_pipe.cursor()
    s3 = boto3.client("s3", **MINIO_CONFIG)

    paginator = s3.get_paginator("list_objects_v2")
    pages = paginator.paginate(Bucket=BUCKET_UNSTRUCTURED)

    ok_count = 0
    err_count = 0

    for page in pages:
        for obj in page.get("Contents", []):
            key = obj["Key"]
            errors = []
            report_id = None

            try:
                head = s3.head_object(Bucket=BUCKET_UNSTRUCTURED, Key=key)
                metadata = head.get("Metadata", {})
            except Exception as e:
                print(f"[ERRO] Não foi possível ler metadata de {key}: {e}")
                err_count += 1
                continue

            report_id_str = metadata.get("report_id", "")
            file_name = metadata.get("file_name", "")

            # Validar report_id na metadata
            try:
                report_id = int(report_id_str)
            except (ValueError, TypeError):
                errors.append(f"report_id inválido na metadata: '{report_id_str}'")

            # Validar file_name na metadata
            if not file_name:
                errors.append("file_name em falta na metadata")

            # Verificar se report_id existe em op_report
            if report_id is not None:
                cur_op.execute("SELECT 1 FROM op_report WHERE report_id = %s", (report_id,))
                if not cur_op.fetchone():
                    errors.append(f"report_id={report_id} não existe em op_report")

            # Verificar integridade do PDF (primeiros 4 bytes = %PDF)
            if not errors:
                try:
                    response = s3.get_object(
                        Bucket=BUCKET_UNSTRUCTURED,
                        Key=key,
                        Range="bytes=0-3",
                    )
                    header = response["Body"].read()
                    if header != b"%PDF":
                        errors.append(f"Conteúdo não é um PDF válido (header: {header})")
                except Exception as e:
                    errors.append(f"Erro ao verificar conteúdo: {e}")

            if errors:
                msg = "; ".join(errors)
                print(f"[INVÁLIDO] {key}: {msg}")
                try:
                    s3.delete_object(Bucket=BUCKET_UNSTRUCTURED, Key=key)
                except Exception as del_e:
                    print(f"  Erro ao apagar {key}: {del_e}")

                cur_pipe.execute("""
                    INSERT INTO etl_logs_pdfs (file_name, step, status, error_message)
                    VALUES (%s, %s, %s, %s)
                """, (key, "validate_bronze_unstructured", "error", msg))
                err_count += 1
            else:
                ok_count += 1

    conn_pipe.commit()
    cur_pipe.close(); conn_pipe.close()
    cur_op.close();   conn_op.close()
    print(f"validate_bronze_unstructured — {ok_count} válidos, {err_count} inválidos/removidos")


if __name__ == "__main__":
    validate()
