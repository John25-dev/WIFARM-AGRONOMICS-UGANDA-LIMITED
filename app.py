from js import Response, Headers
import json

# ── Your existing business logic classes (unchanged) ──────────────────────────

class WifarmEngine:
    def __init__(self, db_binding):
        self.db = db_binding

class LoanCalculator:
    @staticmethod
    def calculate_total_due(balance: float, arrears: float, rate: float) -> dict:
        """Calculates current exposure for Wifarm clients."""
        interest_on_arrears = arrears * (rate / 100)
        total = balance + arrears + interest_on_arrears
        return {
            "principal_balance": balance,
            "arrears": arrears,
            "interest_penalty": interest_on_arrears,
            "total_payable": total
        }

class InventoryManager:
    async def sync_branch_stock(self, branch_id: str, stock_data: list):
        """Branch-specific submission logic."""
        pass

    async def get_ceo_dashboard(self):
        """CEO view: Only balances if all branches have is_synced = True."""
        pass

class AssetTracker:
    @staticmethod
    def process_gps(lat1, lon1, lat2, lon2, last_time):
        """Differentiates Moving vs Parked based on coordinate delta."""
        delta = abs(lat1 - lat2) + abs(lon1 - lon2)
        status = "Moving" if delta > 0.0001 else "Parked"
        return {"status": status, "last_seen": last_time}


# ── Cloudflare Worker entry point (REQUIRED) ──────────────────────────────────

async def on_fetch(request, env):
    url = request.url
    method = request.method

    headers = Headers.new({"Content-Type": "application/json"}.items())

    # Route: GET /health
    if "/health" in url and method == "GET":
        body = json.dumps({"status": "ok", "service": "Wifarm Agronomics Uganda Limited"})
        return Response.new(body, headers=headers, status=200)

    # Route: POST /loan/calculate
    if "/loan/calculate" in url and method == "POST":
        try:
            data = await request.json()
            result = LoanCalculator.calculate_total_due(
                balance=float(data.get("balance", 0)),
                arrears=float(data.get("arrears", 0)),
                rate=float(data.get("rate", 0))
            )
            return Response.new(json.dumps(result), headers=headers, status=200)
        except Exception as e:
            return Response.new(json.dumps({"error": str(e)}), headers=headers, status=400)

    # Route: GET /asset/track
    if "/asset/track" in url and method == "GET":
        result = AssetTracker.process_gps(0.3136, 32.5811, 0.3137, 32.5812, "2026-05-11T16:00:00Z")
        return Response.new(json.dumps(result), headers=headers, status=200)

    # Default 404
    body = json.dumps({"error": "Route not found", "service": "Wifarm Agronomics"})
    return Response.new(body, headers=headers, status=404)
