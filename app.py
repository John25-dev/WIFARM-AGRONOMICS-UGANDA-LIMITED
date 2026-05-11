from js import Response, Headers
import json

class LoanCalculator:
    @staticmethod
    def calculate_total_due(balance: float, arrears: float, rate: float) -> dict:
        interest_on_arrears = arrears * (rate / 100)
        total = balance + arrears + interest_on_arrears
        return {
            "principal_balance": balance,
            "arrears": arrears,
            "interest_penalty": interest_on_arrears,
            "total_payable": total
        }

class AssetTracker:
    @staticmethod
    def process_gps(lat1, lon1, lat2, lon2, last_time):
        delta = abs(lat1 - lat2) + abs(lon1 - lon2)
        status = "Moving" if delta > 0.0001 else "Parked"
        return {"status": status, "last_seen": last_time}


async def on_fetch(request, env):
    url = request.url
    method = request.method
    headers = Headers.new({"Content-Type": "application/json"}.items())

    # GET /health
    if "/health" in url and method == "GET":
        body = json.dumps({"status": "ok", "service": "Wifarm Agronomics Uganda Limited"})
        return Response.new(body, headers=headers, status=200)

    # GET /clients — list all clients
    if "/clients" in url and method == "GET":
        try:
            result = await env.DB.prepare("SELECT id, full_name, contact_phone, next_of_kin, created_at FROM clients ORDER BY created_at DESC").all()
            rows = [dict(r) for r in result.results]
            return Response.new(json.dumps(rows), headers=headers, status=200)
        except Exception as e:
            return Response.new(json.dumps({"error": str(e)}), headers=headers, status=500)

    # POST /clients — register a new client
    if "/clients" in url and method == "POST":
        try:
            data = await request.json()
            await env.DB.prepare(
                "INSERT INTO clients (full_name, nin_encrypted, contact_phone, next_of_kin, lc1_doc_url) VALUES (?, ?, ?, ?, ?)"
            ).bind(
                data.get("full_name"),
                data.get("nin_encrypted", ""),
                data.get("contact_phone", ""),
                data.get("next_of_kin", ""),
                data.get("lc1_doc_url", "")
            ).run()
            return Response.new(json.dumps({"message": "Client registered successfully"}), headers=headers, status=201)
        except Exception as e:
            return Response.new(json.dumps({"error": str(e)}), headers=headers, status=500)

    # GET /loans — list all loans with client names
    if "/loans" in url and method == "GET":
        try:
            result = await env.DB.prepare(
                "SELECT l.id, c.full_name, l.principal_amount, l.balance, l.arrears, l.interest_rate, l.status FROM loans l JOIN clients c ON l.client_id = c.id"
            ).all()
            rows = [dict(r) for r in result.results]
            return Response.new(json.dumps(rows), headers=headers, status=200)
        except Exception as e:
            return Response.new(json.dumps({"error": str(e)}), headers=headers, status=500)

    # POST /loans — create a new loan
    if "/loans" in url and method == "POST":
        try:
            data = await request.json()
            await env.DB.prepare(
                "INSERT INTO loans (client_id, principal_amount, interest_rate, balance, arrears) VALUES (?, ?, ?, ?, ?)"
            ).bind(
                int(data.get("client_id")),
                float(data.get("principal_amount")),
                float(data.get("interest_rate")),
                float(data.get("principal_amount")),
                0.0
            ).run()
            return Response.new(json.dumps({"message": "Loan created successfully"}), headers=headers, status=201)
        except Exception as e:
            return Response.new(json.dumps({"error": str(e)}), headers=headers, status=500)

    # POST /loan/calculate — calculate loan exposure
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

    # GET /inventory — CEO dashboard view
    if "/inventory" in url and method == "GET":
        try:
            unsynced = await env.DB.prepare(
                "SELECT COUNT(*) as count FROM branch_inventory WHERE is_synced = FALSE"
            ).first()
            all_stock = await env.DB.prepare(
                "SELECT branch_name, item_name, stock_count, is_synced, updated_at FROM branch_inventory ORDER BY branch_name"
            ).all()
            rows = [dict(r) for r in all_stock.results]
            dashboard_status = "Balanced" if unsynced["count"] == 0 else f"Unbalanced — {unsynced['count']} branch(es) pending sync"
            return Response.new(json.dumps({"dashboard_status": dashboard_status, "inventory": rows}), headers=headers, status=200)
        except Exception as e:
            return Response.new(json.dumps({"error": str(e)}), headers=headers, status=500)

    # GET /asset/track
    if "/asset/track" in url and method == "GET":
        result = AssetTracker.process_gps(0.3136, 32.5811, 0.3137, 32.5812, "2026-05-11T16:00:00Z")
        return Response.new(json.dumps(result), headers=headers, status=200)

    # Default 404
    return Response.new(json.dumps({
        "error": "Route not found",
        "available_routes": [
            "GET  /health",
            "GET  /clients",
            "POST /clients",
            "GET  /loans",
            "POST /loans",
            "POST /loan/calculate",
            "GET  /inventory",
            "GET  /asset/track"
        ]
    }), headers=headers, status=404)
