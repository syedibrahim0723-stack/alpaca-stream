import sqlite3, json

conn = sqlite3.connect('alerts.db')
cur = conn.cursor()

cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cur.fetchall()]
print('TABLES:', tables)

for tbl in tables:
    cur.execute(f"PRAGMA table_info({tbl})")
    cols = cur.fetchall()
    print(f"\n--- {tbl} COLUMNS ---")
    for c in cols:
        print(c)
    cur.execute(f"SELECT COUNT(*) FROM {tbl}")
    print("ROW COUNT:", cur.fetchone()[0])

    # Sample 3 rows
    cur.execute(f"SELECT * FROM {tbl} LIMIT 3")
    rows = cur.fetchall()
    print("SAMPLE ROWS:")
    for r in rows:
        print(r)

conn.close()
