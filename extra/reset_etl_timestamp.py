import psycopg2

conn = psycopg2.connect(
    host="localhost",
    port=5433,
    dbname="projeto_db",
    user="projeto_utilizador",
    password="projeto"
)

cur = conn.cursor()

cur.execute(
    "UPDATE etl_data SET last_run = '2000-01-01 00:00:00' WHERE process_name = 'etl_main';"
)

conn.commit()

cur.close()
conn.close()

print("Timestamp atualizado para 2000-01-01")