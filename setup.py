import subprocess
import sys
import time
import os

# ===============================
# CONFIGURAÇÕES
# ===============================

POSTGRES_CONFIG = {
    "host": "localhost",
    "port": 5433,
    "dbname": "projeto_db",
    "user": "projeto_utilizador",
    "password": "projeto",
}

MINIO_CONFIG = {
    "endpoint": "localhost:9000",
    "access_key": "admin",
    "secret_key": "admin123",
    "secure": False,
}

MINIO_BUCKETS = ["raw", "unstructured", "transformed"]

# Scripts de criação (ordem importa)
CREATE_SCRIPTS = [
    "create/create_etl_data.py",
    "create/create_etl_logs.py",
    "create/create_opdb.py",
    "create/create_dm.py",
    "create/create_vector_db.py",
]

POPULATE_SCRIPT = "populate/populate_opdb_csv.py"

ETL_SCRIPT = "etl/etl.py"


# ===============================
# HELPERS DE OUTPUT
# ===============================

def step(msg):
    print(f"\n{'='*60}")
    print(f"  {msg}")
    print(f"{'='*60}")

def ok(msg):
    print(f"  {msg}")

def warn(msg):
    print(f"  {msg}")

def err(msg):
    print(f"  {msg}")

def info(msg):
    print(f"  {msg}")


# ===============================
# VERIFICAR DEPENDÊNCIAS
# ===============================

def check_dependencies():
    step("A verificar dependências do sistema")

    # Verificar Docker
    result = subprocess.run(["docker", "--version"], capture_output=True, text=True)
    if result.returncode != 0:
        err("Docker não encontrado. Instala o Docker e tenta novamente.")
        sys.exit(1)
    ok(f"Docker: {result.stdout.strip()}")

    # Verificar Docker Compose
    result = subprocess.run(["docker", "compose", "version"], capture_output=True, text=True)
    if result.returncode != 0:
        # tentar versão antiga
        result = subprocess.run(["docker-compose", "--version"], capture_output=True, text=True)
        if result.returncode != 0:
            err("Docker Compose não encontrado.")
            sys.exit(1)
    ok(f"Docker Compose: {result.stdout.strip()}")

    # Verificar ficheiro docker-compose.yml
    if not os.path.exists("docker/docker-compose.yml"):
        err("Ficheiro docker/docker-compose.yml não encontrado.")
        sys.exit(1)
    ok("docker/docker-compose.yml encontrado")

    # Verificar dependências Python
    required_packages = {
        "psycopg2": "psycopg2-binary",
        "boto3": "boto3",
        "minio": "minio",
        "requests": "requests",
        "pandas": "pandas",
        "pyarrow": "pyarrow",
    }

    missing = []
    for pkg, install_name in required_packages.items():
        try:
            __import__(pkg)
            ok(f"Python package '{pkg}' disponível")
        except ImportError:
            warn(f"Python package '{pkg}' em falta — será instalado")
            missing.append(install_name)

    if missing:
        info(f"A instalar: {', '.join(missing)}")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install"] + missing,
            capture_output=True, text=True
        )
        if result.returncode != 0:
            err(f"Erro ao instalar dependências:\n{result.stderr}")
            sys.exit(1)
        ok("Dependências instaladas com sucesso")


# ===============================
# DOCKER COMPOSE
# ===============================

def start_docker():
    step("A iniciar serviços Docker")

    # Determinar comando correto
    compose_cmd = _get_compose_cmd()

    info("A executar docker compose up -d ...")
    result = subprocess.run(
        compose_cmd + ["up", "-d"],
        capture_output=True, text=True
    )

    if result.returncode != 0:
        err(f"Erro ao iniciar Docker:\n{result.stderr}")
        sys.exit(1)

    ok("Serviços Docker iniciados")
    print(result.stdout)


def _get_compose_cmd():
    result = subprocess.run(["docker", "compose", "version"], capture_output=True)
    if result.returncode == 0:
        return ["docker", "compose", "-f", "docker/docker-compose.yml"]
    return ["docker-compose", "-f", "docker/docker-compose.yml"]


# ===============================
# AGUARDAR POSTGRES
# ===============================

def wait_for_postgres(retries=30, delay=3):
    step("A aguardar PostgreSQL ficar disponível")

    try:
        import psycopg2
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "psycopg2-binary"], check=True)
        import psycopg2

    for attempt in range(1, retries + 1):
        try:
            conn = psycopg2.connect(**POSTGRES_CONFIG)
            conn.close()
            ok(f"PostgreSQL disponível (tentativa {attempt}/{retries})")
            return
        except Exception as e:
            info(f"Tentativa {attempt}/{retries} — ainda não disponível ({e})")
            time.sleep(delay)

    err(f"PostgreSQL não ficou disponível após {retries} tentativas.")
    sys.exit(1)


# ===============================
# AGUARDAR MINIO
# ===============================

def wait_for_minio(retries=20, delay=3):
    step("A aguardar MinIO ficar disponível")

    try:
        import requests
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "requests"], check=True)
        import requests

    url = f"http://{MINIO_CONFIG['endpoint']}/minio/health/live"

    for attempt in range(1, retries + 1):
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                ok(f"MinIO disponível (tentativa {attempt}/{retries})")
                return
        except Exception as e:
            info(f"Tentativa {attempt}/{retries} — ainda não disponível ({e})")
        time.sleep(delay)

    err(f"MinIO não ficou disponível após {retries} tentativas.")
    sys.exit(1)


# ===============================
# CRIAR BUCKETS MINIO
# ===============================

def create_minio_buckets():
    step("A criar buckets MinIO")

    try:
        from minio import Minio
        from minio.error import S3Error
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "minio"], check=True)
        from minio import Minio
        from minio.error import S3Error

    client = Minio(
        MINIO_CONFIG["endpoint"],
        access_key=MINIO_CONFIG["access_key"],
        secret_key=MINIO_CONFIG["secret_key"],
        secure=MINIO_CONFIG["secure"],
    )

    for bucket in MINIO_BUCKETS:
        try:
            if client.bucket_exists(bucket):
                warn(f"Bucket '{bucket}' já existe — ignorado")
            else:
                client.make_bucket(bucket)
                ok(f"Bucket '{bucket}' criado")
        except S3Error as e:
            err(f"Erro ao criar bucket '{bucket}': {e}")
            sys.exit(1)


# ===============================
# CRIAR TABELAS (SCRIPTS CREATE)
# ===============================

def create_database_tables():
    step("A criar tabelas na base de dados")

    for script in CREATE_SCRIPTS:
        if not os.path.exists(script):
            warn(f"Script não encontrado: {script} — a ignorar")
            continue

        info(f"A executar: {script}")
        result = subprocess.run(
            [sys.executable, script],
            capture_output=True, text=True
        )

        if result.returncode != 0:
            err(f"Erro em {script}:\n{result.stderr}")
            sys.exit(1)

        ok(f"{script} concluído")
        if result.stdout.strip():
            for line in result.stdout.strip().splitlines():
                print(f"     {line}")


# ===============================
# POPULAR BASE OPERACIONAL
# ===============================

def populate_operational_db():
    step("A popular base de dados operacional (CSV)")

    # Verificar se os CSVs existem
    csv_report = os.path.join("populate", "csv", "op_report.csv")
    csv_data   = os.path.join("populate", "csv", "op_data.csv")

    if not os.path.exists(csv_report) or not os.path.exists(csv_data):
        warn("Ficheiros CSV não encontrados em populate/csv/op_report.csv e populate/csv/op_data.csv")
        warn("A ignorar o passo de populamento. Podes executar populate_opdb_csv.py manualmente mais tarde.")
        return

    if not os.path.exists(POPULATE_SCRIPT):
        warn(f"Script {POPULATE_SCRIPT} não encontrado — a ignorar")
        return

    info(f"A executar: {POPULATE_SCRIPT}")
    result = subprocess.run(
        [sys.executable, POPULATE_SCRIPT],
        capture_output=True, text=True
    )

    if result.returncode != 0:
        err(f"Erro em {POPULATE_SCRIPT}:\n{result.stderr}")
        sys.exit(1)

    ok(f"{POPULATE_SCRIPT} concluído")
    if result.stdout.strip():
        for line in result.stdout.strip().splitlines():
            print(f"     {line}")

# ===============================
# CORRER ETL
# ===============================

def execute_etl():
    step("A executar etl")

    if not os.path.exists(ETL_SCRIPT):
        warn(f"Script não encontrado: {ETL_SCRIPT} — a ignorar")
        return

    info(f"A executar: {ETL_SCRIPT}\n")
    
    # Ao retirar o capture_output, o output vai direto para o teu terminal em tempo real
    result = subprocess.run(
        [sys.executable, "etl.py"],
        cwd="etl"
    )

    if result.returncode != 0:
        err(f"Erro ao executar {ETL_SCRIPT}! (Verifica o erro detalhado acima nas linhas do terminal)")
        sys.exit(1)

    ok(f"{ETL_SCRIPT} concluído")

# ===============================
# VERIFICAÇÃO FINAL
# ===============================

def verify_setup():
    step("A verificar setup final")

    import psycopg2

    try:
        conn = psycopg2.connect(**POSTGRES_CONFIG)
        cur = conn.cursor()

        tabelas_esperadas = [
            "etl_data", "etl_logs",
            "op_report", "op_data",
            "dim_source", "dim_indicator", "dim_location",
            "dim_location_hierarchy", "dim_date", "dim_report",
            "fact_values", "documents"
        ]

        cur.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
        """)

        tabelas_existentes = {row[0] for row in cur.fetchall()}

        todas_ok = True
        for tabela in tabelas_esperadas:
            if tabela in tabelas_existentes:
                ok(f"Tabela '{tabela}' existe")
            else:
                warn(f"Tabela '{tabela}' NÃO encontrada")
                todas_ok = False

        # Verificar last_run em etl_data
        cur.execute("SELECT last_run FROM etl_data WHERE process_name = 'etl_main'")
        row = cur.fetchone()
        if row:
            ok(f"etl_data.last_run = {row[0]}")
        else:
            warn("Registo etl_main não encontrado em etl_data")
            todas_ok = False

        # Verificar populamento das tabelas operacionais
        for tabela in ["op_report", "op_data"]:
            cur.execute(f"SELECT COUNT(*) FROM {tabela}")
            count = cur.fetchone()[0]
            if count > 0:
                ok(f"Tabela '{tabela}' populada ({count} registos)")
            else:
                warn(f"Tabela '{tabela}' está vazia — verifica os CSVs em populate/csv/")
                todas_ok = False

        cur.close()
        conn.close()

        return todas_ok

    except Exception as e:
        err(f"Erro na verificação: {e}")
        return False


# ===============================
# SUMÁRIO FINAL
# ===============================

def print_summary():
    print(f"\n{'='*60}")
    print("  SETUP CONCLUÍDO COM SUCESSO")
    print(f"{'='*60}")
    print()
    print("  Serviços disponíveis:")
    print(f"  • PostgreSQL  → localhost:5433")
    print(f"  • MinIO API   → http://localhost:9000")
    print(f"  • MinIO UI    → http://localhost:9001")
    print(f"  • pgAdmin     → http://localhost:5051")
    print()
    print("  Próximos passos:")
    print("     (Opcional) Ingestão vetorial:")
    print("     python etl/ingesttt.py")
    print(f"\n{'='*60}\n")


# ===============================
# MAIN
# ===============================

def main():
    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║         SETUP — Pipeline de Dados                        ║")
    print("╚══════════════════════════════════════════════════════════╝")

    check_dependencies()
    start_docker()
    wait_for_postgres()
    wait_for_minio()
    create_minio_buckets()
    create_database_tables()
    populate_operational_db()
    execute_etl()
    all_ok = verify_setup()

    if all_ok:
        print_summary()
    else:
        print()
        warn("Setup concluído com alguns avisos. Verifica as mensagens acima.")
        print()


if __name__ == "__main__":
    main()