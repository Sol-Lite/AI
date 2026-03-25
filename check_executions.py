from app.db.oracle import fetch_all

rows = fetch_all("""
    SELECT
        e.execution_id,
        i.stock_name,
        e.order_side,
        e.execution_price,
        e.execution_quantity,
        e.net_amount,
        TRUNC(CAST(SYSTIMESTAMP AS DATE) - CAST(e.executed_at AS DATE)) AS days_ago
    FROM executions e
    JOIN instruments i ON e.instrument_id = i.instrument_id
    WHERE e.account_id = 1
    ORDER BY e.executed_at
""")

print(f"총 {len(rows)}행\n")
print(f"{'ID':>3}  {'종목':<12}  {'매수/매도':<6}  {'가격':>10}  {'수량':>5}  {'순손익':>12}  {'일전':>5}")
print("-" * 65)
for r in rows:
    exec_id, stock_name, side, price, qty, net, days = r
    side_label = "매수" if side == "buy" else "매도"
    print(f"{exec_id:>3}  {str(stock_name):<12}  {side_label:<6}  {float(price):>10,.0f}  {int(qty):>5}  {float(net):>12,.0f}  {int(days):>4}일전")
