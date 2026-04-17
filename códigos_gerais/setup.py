import sys
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CREATE_DIR = os.path.join(BASE_DIR, "create")

sys.path.append(CREATE_DIR)

# 📥 imports
import create_minio_buckets
import create_dm
import create_etl_data
import create_etl_logs
import create_opdb
import create_vector_db
import create_view


def run_all():
    print("🚀 A iniciar setup do sistema...\n")

    create_minio_buckets.main()
    print("✅ MinIO buckets criados")

    create_dm.main()
    print("✅ Data Warehouse criado")

    create_etl_data.main()
    print("✅ ETL data criado")

    create_etl_logs.main()
    print("✅ ETL logs criado")

    create_opdb.main()
    print("✅ Operational DB criado")

    create_vector_db.main()
    print("✅ Vector DB criado")

    create_view.main()
    print("✅ Views criadas")

    print("\n🎉 SETUP COMPLETO COM SUCESSO!")

if __name__ == "__main__":
    run_all()