"""
GET /api/orders Spring API 연동 확인

실행:
    python test_orders_get.py
"""
import os, sys
import httpx
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TEST_JWT_TOKEN")
if not TOKEN:
    print("[ERROR] .env에 TEST_JWT_TOKEN이 없습니다.")
    sys.exit(1)

SPRING_BASE_URL = os.getenv("SPRING_BASE_URL", "http://localhost:8080")

resp = httpx.get(
    f"{SPRING_BASE_URL}/api/orders",
    params={"status": "ALL"},
    headers={"Authorization": f"Bearer {TOKEN}"},
    timeout=5,
)

print(f"status: {resp.status_code}")
if resp.status_code == 200:
    orders = resp.json()
    print(f"주문 {len(orders)}건")
    for o in orders[:3]:
        print(f"  {o['orderNo']}  {o['stockName']}  {o['orderSide']}  {o['orderStatus']}  {o['orderPrice']:,}원 x {o['orderQuantity']}주")
else:
    print(resp.text)
