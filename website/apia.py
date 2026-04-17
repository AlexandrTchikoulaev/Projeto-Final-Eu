from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from datetime import datetime, date
import psycopg2
import psycopg2.extras
import subprocess
import sys
import os
import threading

# ── RAG imports ──────────────────────────────────────────
from langchain_core.prompts import ChatPromptTemplate
from langchain_community.llms.ollama import Ollama
from langchain_community.vectorstores import PGVector
from langchain_community.embeddings.ollama import OllamaEmbeddings

# ── Configurações ─────────────────────────────────────────
DB_SETTINGS = {
    "host": "localhost",
    "port": 5433,
    "database": "projeto_db",
    "user": "projeto_utilizador",
    "password": "projeto",
}

PROMPT_TEMPLATE = """
Answer the question based only on the following context:

{context}

---

Answer the question based on the above context: {question}
"""

# ── Ligação PostgreSQL ────────────────────────────────────
def get_db_connection():
    return psycopg2.connect(
        host=DB_SETTINGS["host"],
        port=DB_SETTINGS["port"],
        dbname=DB_SETTINGS["database"],
        user=DB_SETTINGS["user"],
        password=DB_SETTINGS["password"],
    )

# ── App ──────────────────────────────────────────────────
app = FastAPI(title="OP Report API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ── Schemas ───────────────────────────────────────────────
class ReportIn(BaseModel):
    source_code: str
    file_name: str
    report_url: str
    publication_date: date
    area_tematica: str = ""
    estado: str = ""
    palavras_chave: str = ""
    resumo: str = ""

class ChatIn(BaseModel):
    question: str

class OpDataIn(BaseModel):
    report_id: int
    file_name: str
    file_url: str
    extract_function: str = ""
    file_type: str = ""

# ── Helpers RAG ───────────────────────────────────────────
def get_embedding_function():
    return OllamaEmbeddings(model="mxbai-embed-large")

def query_rag(query_text: str):
    embedding_function = get_embedding_function()

    connection_string = (
        f"postgresql+psycopg2://{DB_SETTINGS['user']}:{DB_SETTINGS['password']}"
        f"@{DB_SETTINGS['host']}:{DB_SETTINGS['port']}/{DB_SETTINGS['database']}"
    )

    db = PGVector(
        connection_string=connection_string,
        embedding_function=embedding_function,
        collection_name="documents",
    )

    results = db.similarity_search_with_score(query_text, k=5)

    if not results:
        return {"answer": "Não encontrei informação relevante nos documentos indexados.", "sources": []}

    context_text = "\n\n---\n\n".join([doc.page_content for doc, _score in results])
    prompt_template = ChatPromptTemplate.from_template(PROMPT_TEMPLATE)
    prompt = prompt_template.format(context=context_text, question=query_text)

    model = Ollama(model="mistral")
    response_text = model.invoke(prompt)

    sources = [doc.metadata.get("id", None) for doc, _score in results]

    return {"answer": response_text, "sources": sources}


# ── Endpoints INSERÇÃO (POST) ─────────────────────────────

@app.post("/op_report", status_code=201)
def add_report(report: ReportIn):
    """Insere um novo relatório na tabela op_report."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO op_report (report_id, source_code, file_name, report_url, publication_date,
                                   area_tematica, estado, palavras_chave, resumo)
            VALUES ((SELECT COALESCE(MAX(report_id), 0) + 1 FROM op_report),
                    %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING report_id;
        """, (report.source_code, report.file_name, report.report_url, report.publication_date,
               report.area_tematica, report.estado, report.palavras_chave, report.resumo))
        report_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        return {"report_id": report_id, "message": "Relatório inserido com sucesso."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/op_data", status_code=201)
def add_op_data(data: OpDataIn):
    """Insere um novo registo na tabela op_data, verificando a existência do report_id."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()

        # Verificar se o report_id existe — feito ANTES do try/except genérico
        cur.execute("SELECT 1 FROM op_report WHERE report_id = %s", (data.report_id,))
        if not cur.fetchone():
            cur.close()
            conn.close()
            raise HTTPException(
                status_code=404,
                detail=f"O report_id {data.report_id} não existe na base de dados."
            )

        cur.execute("""
            INSERT INTO op_data (file_id, report_id, file_name, file_url, extract_function, file_type)
            VALUES ((SELECT COALESCE(MAX(file_id), 0) + 1 FROM op_data), %s, %s, %s, %s, %s)
            RETURNING file_id;
        """, (data.report_id, data.file_name, data.file_url, data.extract_function, data.file_type))

        file_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        return {"file_id": file_id, "message": "Ficheiro op_data inserido com sucesso."}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        conn.close()
        raise HTTPException(status_code=500, detail=str(e))


# ── Endpoints LEITURA (GET) ───────────────────────────────

@app.get("/op_report")
def get_reports():
    """Devolve todos os registos da tabela op_report."""
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT report_id, source_code, file_name, report_url, publication_date,
                   area_tematica, estado, palavras_chave, resumo
            FROM op_report
            ORDER BY report_id DESC;
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/op_data")
def get_op_data():
    """Devolve todos os registos da tabela op_data."""
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT
                d.file_id,
                d.report_id,
                d.file_name,
                d.file_url,
                d.extract_function,
                d.file_type,
                r.source_code
            FROM op_data d
            LEFT JOIN op_report r ON r.report_id = d.report_id
            ORDER BY d.file_id DESC;
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/sources")
def get_sources():
    """Devolve todas as fontes da tabela dim_source."""
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT source_code, source_name FROM dim_source ORDER BY source_name;")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/indicators")
def get_indicators(source_code: str = None):
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if source_code:
            cur.execute("""
                SELECT DISTINCT i.indicator_code, i.indicator_name, r.source_code
                FROM dim_indicator i
                JOIN fact_values f ON f.indicator_code = i.indicator_code
                JOIN op_report r ON r.report_id = f.report_id
                WHERE r.source_code = %s
                ORDER BY i.indicator_name;
            """, (source_code,))
        else:
            cur.execute("""
                SELECT DISTINCT ON (i.indicator_code)
                    i.indicator_code, i.indicator_name, r.source_code
                FROM dim_indicator i
                JOIN fact_values f ON f.indicator_code = i.indicator_code
                JOIN op_report r ON r.report_id = f.report_id
                ORDER BY i.indicator_code;
            """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/fact_values")
def get_fact_values(indicator_code: str):
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT
                c.location_code,
                c.location_name,
                d.year,
                f.value
            FROM fact_values f
            JOIN dim_location c ON f.location_code = c.location_code
            JOIN dim_indicator i ON f.indicator_code = i.indicator_code
            JOIN dim_date d ON f.date_id = d.date_id
            WHERE i.indicator_code = %s
            ORDER BY d.year ASC, c.location_name ASC;
        """, (indicator_code,))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Endpoint ETL ─────────────────────────────────────────

@app.post("/etl/run")
def etl_run():
    """Executa o pipeline ETL (etl.py) e devolve os logs em streaming."""

    etl_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "etl", "etl.py")

    if not os.path.exists(etl_path):
        raise HTTPException(status_code=404, detail=f"etl.py não encontrado em: {etl_path}")

    def stream_output():
        yield "A iniciar pipeline ETL...\n"
        try:
            process = subprocess.Popen(
                [sys.executable, etl_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            for line in process.stdout:
                yield line
            process.wait()
            if process.returncode == 0:
                yield "\n✓ ETL concluído com sucesso.\n"
            else:
                yield f"\n✗ ETL terminou com erro (código {process.returncode}).\n"
        except Exception as e:
            yield f"\n✗ Erro ao executar etl.py: {e}\n"

    return StreamingResponse(stream_output(), media_type="text/plain")


@app.get("/etl_logs")
def get_etl_logs():
    """Devolve todos os registos da tabela etl_logs."""
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM etl_logs ORDER BY 1 DESC;")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/dashboard")
def get_dashboard(indicator_name: str, year: int):
    """Devolve os dados da view para um indicador e ano específicos."""
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        # Normaliza newlines no nome do indicador (BD pode ter \n, cliente envia sem)
        cur.execute(
            """SELECT location_name, value FROM view
               WHERE REPLACE(REPLACE(indicator_name, E'\n', ' '), E'\r', '') = %s
               AND year = %s
               ORDER BY location_name;""",
            (indicator_name.strip(), year)
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# @app.get("/dashboard/filters")
# def get_dashboard_filters():
#     """Devolve os indicadores e anos disponíveis na view."""
#     try:
#         conn = get_db_connection()
#         cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
#         cur.execute("SELECT DISTINCT indicator_name FROM view ORDER BY indicator_name;")
#         indicators = [r["indicator_name"] for r in cur.fetchall()]
#         cur.execute("SELECT DISTINCT year FROM view ORDER BY year DESC;")
#         years = [r["year"] for r in cur.fetchall()]
#         cur.close()
#         conn.close()
#         return {"indicators": indicators, "years": years}
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))


@app.get("/dashboard/filters")
def get_dashboard_filters(indicator_name: str = None):
    """Devolve os indicadores e anos disponíveis na view, filtrando por indicador se fornecido."""
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        # Devolve nomes com newlines normalizados para espaço
        cur.execute("""
            SELECT DISTINCT REPLACE(REPLACE(indicator_name, E'\n', ' '), E'\r', '') AS indicator_name
            FROM view
            ORDER BY 1;
        """)
        indicators = [r["indicator_name"].strip() for r in cur.fetchall()]

        if indicator_name:
            cur.execute("""
                SELECT DISTINCT year FROM view
                WHERE REPLACE(REPLACE(indicator_name, E'\n', ' '), E'\r', '') = %s
                ORDER BY year DESC;
            """, (indicator_name.strip(),))
        else:
            cur.execute("SELECT DISTINCT year FROM view ORDER BY year DESC;")

        years = [r["year"] for r in cur.fetchall()]
        cur.close()
        conn.close()
        return {"indicators": indicators, "years": years}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
# ── Endpoint CHAT ─────────────────────────────────────────

@app.post("/chat")
def chat(body: ChatIn):
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="A pergunta não pode estar vazia.")
    try:
        result = query_rag(body.question)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
