"""
Oracle DB 더미 데이터 삽입 스크립트
TEST 스키마의 실제 컬럼 구조에 맞춰 acc-001 더미 데이터를 삽입합니다.

실행:
    python setup_dummy_data.py
"""
from app.db.oracle import get_oracle_connection

ACCOUNT_ID          = 1   # NUMBER 타입, main.py account_id와 동일
SIMULATION_ROUND_ID = 1
USD_EXCHANGE_RATE   = 1380.0

# ── 더미 데이터 ────────────────────────────────────────────────────────────────

INSTRUMENTS = [
    # (instrument_id, market_type, instrument_type, stock_code, stock_name,
    #  currency_code, active_yn, etf_yn, nxt_yn, sector)
    (1, "domestic", "STOCK", "005930", "삼성전자",   "KRW", "Y", "N", "N", "IT"),
    (2, "domestic", "STOCK", "000660", "SK하이닉스", "KRW", "Y", "N", "N", "반도체"),
    (3, "domestic", "STOCK", "035420", "NAVER",      "KRW", "Y", "N", "N", "IT"),
    (4, "overseas", "STOCK", "AAPL",   "Apple",      "USD", "Y", "N", "N", "IT"),
    (5, "overseas", "STOCK", "NVDA",   "NVIDIA",     "USD", "Y", "N", "N", "반도체"),
]

CASH_BALANCES = [
    # (cash_balance_id, currency_code, available_amount, total_amount)
    (1, "KRW", 3_000_000, 5_000_000),
    (2, "USD",     1_000,     1_500),
]

HOLDINGS = [
    # (holding_id, instrument_id, holding_qty, available_qty, avg_buy_price, avg_buy_exchange_rate)
    (1, 1,  50,  50,  70_000,          1.0),   # 삼성전자  (KRW)
    (2, 2,  20,  20, 180_000,          1.0),   # SK하이닉스 (KRW)
    (3, 3,  10,  10, 200_000,          1.0),   # NAVER    (KRW)
    (4, 4,   5,   5,     200, USD_EXCHANGE_RATE),  # Apple  (USD)
    (5, 5,   3,   3,     800, USD_EXCHANGE_RATE),  # NVIDIA (USD)
]

EXECUTIONS = [
    # (execution_id, order_id, instrument_id, execution_no,
    #  order_side, price, qty, gross_amount, fee_amount, tax_amount, net_amount, days_ago)
    (1, 1, 1, "EX-001", "buy",   70_000,  50,  3_500_000, 3_500,      0, -3_503_500, 30),
    (2, 2, 2, "EX-002", "buy",  180_000,  20,  3_600_000, 3_600,      0, -3_603_600, 25),
    (3, 3, 3, "EX-003", "buy",  200_000,  10,  2_000_000, 2_000,      0, -2_002_000, 20),
    (4, 4, 4, "EX-004", "buy",      200,   5,      1_000,   100,      0,     -1_100, 15),
    (5, 5, 5, "EX-005", "buy",      800,   3,      2_400,   100,      0,     -2_500, 10),
    (6, 6, 1, "EX-006", "sell",  75_000,  10,    750_000, 3_750, 11_250,    735_000,  5),
    (7, 7, 2, "EX-007", "sell", 200_000,   5,  1_000_000, 5_000, 15_000,    980_000,  3),
    (8, 8, 3, "EX-008", "sell", 190_000,   3,    570_000, 2_850,  8_550,    558_600,  1),
]

PORTFOLIO_SNAPSHOTS = [
    # (snapshot_id, days_ago, total_value, cash_krw, cash_usd, stock_value, daily_return)
    (1,  0,  12_000_000, 5_000_000, 1_500, 5_627_000, 0.50),
    (2,  1,  11_940_000, 5_000_000, 1_500, 5_567_000, -0.20),
    (3,  2,  11_900_000, 5_000_000, 1_500, 5_527_000,  0.30),
    (4,  3,  11_870_000, 5_000_000, 1_500, 5_497_000, -0.10),
    (5,  4,  11_850_000, 5_000_000, 1_500, 5_477_000,  0.20),
    (6,  5,  11_830_000, 5_000_000, 1_500, 5_457_000, -0.15),
    (7,  6,  11_800_000, 5_000_000, 1_500, 5_427_000,  0.40),
    (8,  7,  11_760_000, 5_000_000, 1_500, 5_387_000, -0.25),
    (9,  8,  11_730_000, 5_000_000, 1_500, 5_357_000,  0.10),
    (10, 9,  11_700_000, 5_000_000, 1_500, 5_327_000, -0.30),
    (11, 10, 11_670_000, 5_000_000, 1_500, 5_297_000,  0.15),
    (12, 11, 11_650_000, 5_000_000, 1_500, 5_277_000, -0.05),
    (13, 12, 11_630_000, 5_000_000, 1_500, 5_257_000,  0.60),
    (14, 13, 11_570_000, 5_000_000, 1_500, 5_197_000, -0.40),
    (15, 14, 11_540_000, 5_000_000, 1_500, 5_167_000,  0.20),
    (16, 15, 11_510_000, 5_000_000, 1_500, 5_137_000, -0.10),
    (17, 16, 11_490_000, 5_000_000, 1_500, 5_117_000,  0.35),
    (18, 17, 11_450_000, 5_000_000, 1_500, 5_077_000, -0.20),
    (19, 18, 11_430_000, 5_000_000, 1_500, 5_057_000,  0.10),
    (20, 19, 11_410_000, 5_000_000, 1_500, 5_037_000, -0.05),
    (21, 20, 11_400_000, 5_000_000, 1_500, 5_027_000,  0.25),
    (22, 21, 11_370_000, 5_000_000, 1_500, 4_997_000, -0.30),
    (23, 22, 11_350_000, 5_000_000, 1_500, 4_977_000,  0.50),
    (24, 23, 11_290_000, 5_000_000, 1_500, 4_917_000, -0.45),
    (25, 24, 11_240_000, 5_000_000, 1_500, 4_867_000,  0.20),
    (26, 25, 11_210_000, 5_000_000, 1_500, 4_837_000, -0.15),
    (27, 26, 11_190_000, 5_000_000, 1_500, 4_817_000,  0.10),
    (28, 27, 11_170_000, 5_000_000, 1_500, 4_797_000, -0.05),
    (29, 28, 11_150_000, 5_000_000, 1_500, 4_777_000,  0.30),
    (30, 29, 11_120_000, 5_000_000, 1_500, 4_747_000, -0.20),
    (31, 31, 11_000_000, 5_000_000, 1_500, 4_627_000,  0.10),  # base_1m
    (32, 91, 10_500_000, 5_000_000, 1_500, 4_127_000, -0.10),  # base_3m
    (33,181,  9_800_000, 5_000_000, 1_500, 3_427_000,  0.05),  # base_6m
]

# ── 실행 ──────────────────────────────────────────────────────────────────────

def delete_existing(cur):
    for table, id_col in [
        ("holdings",          "account_id"),
        ("executions",        "account_id"),
        ("cash_balances",     "account_id"),
        ("portfolio_snapshots","account_id"),
    ]:
        cur.execute(f"DELETE FROM {table} WHERE {id_col} = :1", [ACCOUNT_ID])
    cur.execute("DELETE FROM instruments WHERE instrument_id IN (1,2,3,4,5)")
    print("  [delete] 기존 데이터 삭제")


def insert_all(cur):
    cur.executemany(
        "INSERT INTO instruments"
        " (instrument_id, market_type, instrument_type, stock_code, stock_name,"
        "  currency_code, active_yn, etf_yn, nxt_yn, sector, created_at, updated_at)"
        " VALUES (:1,:2,:3,:4,:5,:6,:7,:8,:9,:10, SYSDATE, SYSDATE)",
        INSTRUMENTS,
    )
    print(f"  [insert] instruments {len(INSTRUMENTS)}건")

    cur.executemany(
        "INSERT INTO cash_balances"
        " (cash_balance_id, account_id, simulation_round_id,"
        "  currency_code, available_amount, total_amount, updated_at)"
        " VALUES (:1,:2,:3,:4,:5,:6, SYSDATE)",
        [(r[0], ACCOUNT_ID, SIMULATION_ROUND_ID, r[1], r[2], r[3]) for r in CASH_BALANCES],
    )
    print(f"  [insert] cash_balances {len(CASH_BALANCES)}건")

    cur.executemany(
        "INSERT INTO holdings"
        " (holding_id, account_id, simulation_round_id, instrument_id,"
        "  holding_quantity, available_quantity, avg_buy_price, avg_buy_exchange_rate, updated_at)"
        " VALUES (:1,:2,:3,:4,:5,:6,:7,:8, SYSDATE)",
        [(r[0], ACCOUNT_ID, SIMULATION_ROUND_ID, r[1], r[2], r[3], r[4], r[5]) for r in HOLDINGS],
    )
    print(f"  [insert] holdings {len(HOLDINGS)}건")

    cur.executemany(
        "INSERT INTO executions"
        " (execution_id, order_id, account_id, simulation_round_id, instrument_id,"
        "  execution_no, order_side, execution_price, execution_quantity,"
        "  gross_amount, fee_amount, tax_amount, net_amount, executed_at, created_at)"
        " VALUES (:1,:2,:3,:4,:5,:6,:7,:8,:9,:10,:11,:12,:13, SYSDATE-:14, SYSDATE)",
        [(r[0], r[1], ACCOUNT_ID, SIMULATION_ROUND_ID, r[2],
          r[3], r[4], r[5], r[6], r[7], r[8], r[9], r[10], r[11])
         for r in EXECUTIONS],
    )
    print(f"  [insert] executions {len(EXECUTIONS)}건")

    cur.executemany(
        "INSERT INTO portfolio_snapshots"
        " (snapshot_id, account_id, simulation_round_id, snapshot_date,"
        "  total_value, cash_krw, cash_usd, usd_exchange_rate, stock_value, daily_return, created_at)"
        " VALUES (:1,:2,:3, TRUNC(SYSDATE)-:4,:5,:6,:7,:8,:9,:10, SYSDATE)",
        [(r[0], ACCOUNT_ID, SIMULATION_ROUND_ID, r[1], r[2], r[3], r[4], USD_EXCHANGE_RATE, r[5], r[6])
         for r in PORTFOLIO_SNAPSHOTS],
    )
    print(f"  [insert] portfolio_snapshots {len(PORTFOLIO_SNAPSHOTS)}건")


if __name__ == "__main__":
    conn = get_oracle_connection()
    try:
        with conn.cursor() as cur:
            print("=== Setup ===")
            delete_existing(cur)
            insert_all(cur)
        conn.commit()
        print("완료.")
    except Exception as e:
        conn.rollback()
        print(f"[ERROR] {e}")
        raise
    finally:
        conn.close()
