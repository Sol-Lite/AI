from app.db.oracle import get_oracle_connection

TABLES = ["instruments", "cash_balances", "holdings", "executions", "portfolio_snapshots"]

conn = get_oracle_connection()
try:
    with conn.cursor() as cur:
        for table in TABLES:
            cur.execute("""
                SELECT column_name, data_type, data_length, nullable
                FROM user_tab_columns
                WHERE table_name = :1
                ORDER BY column_id
            """, [table.upper()])
            rows = cur.fetchall()
            if rows:
                print(f"\n[{table}]")
                for col, dtype, length, nullable in rows:
                    nn = "NOT NULL" if nullable == "N" else ""
                    print(f"  {col} {dtype}({length}) {nn}")
            else:
                print(f"\n[{table}] 테이블 없음")
finally:
    conn.close()
