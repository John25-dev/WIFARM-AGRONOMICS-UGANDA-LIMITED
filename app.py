from js import Response, Headers
import json, time, base64, hmac, hashlib

# ── Config ────────────────────────────────────────────────────────────────────
SECRET = "wifarm-secret-2026"
USERS  = {
    "admin":   {"password": "wifarm@admin",   "role": "admin"},
    "ceo":     {"password": "wifarm@ceo",     "role": "ceo"},
    "officer": {"password": "wifarm@officer", "role": "officer"},
}

# ── Minimal JWT (HS256) ───────────────────────────────────────────────────────
def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

def make_token(username: str, role: str) -> str:
    header  = b64url(json.dumps({"alg":"HS256","typ":"JWT"}).encode())
    payload = b64url(json.dumps({"sub":username,"role":role,"exp":int(time.time())+86400}).encode())
    sig     = b64url(hmac.new(SECRET.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest())
    return f"{header}.{payload}.{sig}"

def verify_token(token: str):
    try:
        parts = token.split(".")
        if len(parts) != 3: return None
        header, payload, sig = parts
        expected = b64url(hmac.new(SECRET.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest())
        if sig != expected: return None
        pad = 4 - len(payload) % 4
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * pad))
        if data.get("exp", 0) < int(time.time()): return None
        return data
    except:
        return None

def get_user(request):
    auth = request.headers.get("Authorization") or ""
    if not auth.startswith("Bearer "): return None
    return verify_token(auth[7:])

# ── Business Logic ────────────────────────────────────────────────────────────
class LoanCalculator:
    @staticmethod
    def calculate_total_due(balance, arrears, rate):
        penalty = arrears * (rate / 100)
        return {
            "principal_balance": balance,
            "arrears": arrears,
            "interest_penalty": penalty,
            "total_payable": balance + arrears + penalty
        }

class AssetTracker:
    @staticmethod
    def process_gps(lat1, lon1, lat2, lon2, last_time):
        delta  = abs(lat1 - lat2) + abs(lon1 - lon2)
        status = "Moving" if delta > 0.0001 else "Parked"
        return {"status": status, "last_seen": last_time}

# ── Helpers ───────────────────────────────────────────────────────────────────
def json_response(data, status=200):
    h = Headers.new({"Content-Type": "application/json",
                     "Access-Control-Allow-Origin": "*"}.items())
    return Response.new(json.dumps(data), headers=h, status=status)

def unauthorized():
    return json_response({"error": "Unauthorized — please log in"}, 401)

# ── Entry Point ───────────────────────────────────────────────────────────────
async def on_fetch(request, env):
    url    = request.url
    method = request.method

    # CORS preflight
    if method == "OPTIONS":
        h = Headers.new({
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type,Authorization"
        }.items())
        return Response.new("", headers=h, status=204)

    # ── POST /login (public) ──────────────────────────────────────────────────
    if "/login" in url and method == "POST":
        data = await request.json()
        u    = USERS.get(data.get("username",""))
        if u and u["password"] == data.get("password",""):
            token = make_token(data["username"], u["role"])
            return json_response({"token": token, "username": data["username"], "role": u["role"]})
        return json_response({"error": "Invalid username or password"}, 401)

    # ── GET /health (public) ──────────────────────────────────────────────────
    if "/health" in url and method == "GET":
        return json_response({"status": "ok", "service": "Wifarm Agronomics Uganda Limited"})

    # ── All routes below require a valid token ────────────────────────────────
    user = get_user(request)
    if not user:
        return unauthorized()

    # GET /clients/<id>
    path = url.split(".dev")[-1].split("?")[0]
    parts = [p for p in path.split("/") if p]
    if len(parts) == 2 and parts[0] == "clients" and method == "GET":
        try:
            cid    = int(parts[1])
            result = await env.DB.prepare(
                "SELECT id, full_name, contact_phone, next_of_kin, lc1_doc_url, created_at FROM clients WHERE id = ?"
            ).bind(cid).first()
            if not result:
                return json_response({"error": "Client not found"}, 404)
            return json_response(dict(result))
        except Exception as e:
            return json_response({"error": str(e)}, 500)

    # GET /clients
    if "/clients" in url and method == "GET":
        try:
            result = await env.DB.prepare(
                "SELECT id, full_name, contact_phone, next_of_kin, created_at FROM clients ORDER BY created_at DESC"
            ).all()
            return json_response([dict(r) for r in result.results])
        except Exception as e:
            return json_response({"error": str(e)}, 500)

    # POST /clients
    if "/clients" in url and method == "POST":
        try:
            data = await request.json()
            await env.DB.prepare(
                "INSERT INTO clients (full_name, nin_encrypted, contact_phone, next_of_kin, lc1_doc_url) VALUES (?,?,?,?,?)"
            ).bind(data.get("full_name"), data.get("nin_encrypted",""),
                   data.get("contact_phone",""), data.get("next_of_kin",""),
                   data.get("lc1_doc_url","")).run()
            return json_response({"message": "Client registered successfully"}, 201)
        except Exception as e:
            return json_response({"error": str(e)}, 500)

    # GET /loans
    if "/loans" in url and method == "GET":
        try:
            result = await env.DB.prepare(
                "SELECT l.id, l.client_id, c.full_name, l.principal_amount, l.balance, l.arrears, l.interest_rate, l.status FROM loans l JOIN clients c ON l.client_id = c.id"
            ).all()
            return json_response([dict(r) for r in result.results])
        except Exception as e:
            return json_response({"error": str(e)}, 500)

    # POST /loans
    if "/loans" in url and method == "POST":
        try:
            data = await request.json()
            amt  = float(data.get("principal_amount"))
            await env.DB.prepare(
                "INSERT INTO loans (client_id, principal_amount, interest_rate, balance, arrears) VALUES (?,?,?,?,?)"
            ).bind(int(data.get("client_id")), amt,
                   float(data.get("interest_rate", 0)), amt, 0.0).run()
            return json_response({"message": "Loan created successfully"}, 201)
        except Exception as e:
            return json_response({"error": str(e)}, 500)

    # POST /loan/calculate
    if "/loan/calculate" in url and method == "POST":
        try:
            data   = await request.json()
            result = LoanCalculator.calculate_total_due(
                float(data.get("balance", 0)),
                float(data.get("arrears", 0)),
                float(data.get("rate", 0))
            )
            return json_response(result)
        except Exception as e:
            return json_response({"error": str(e)}, 400)

    # GET /inventory
    if "/inventory" in url and method == "GET":
        try:
            unsynced  = await env.DB.prepare(
                "SELECT COUNT(*) as count FROM branch_inventory WHERE is_synced = FALSE"
            ).first()
            all_stock = await env.DB.prepare(
                "SELECT branch_name, item_name, stock_count, is_synced, updated_at FROM branch_inventory ORDER BY branch_name"
            ).all()
            status = "Balanced" if unsynced["count"] == 0 else f"Unbalanced — {unsynced['count']} branch(es) pending sync"
            return json_response({"dashboard_status": status, "inventory": [dict(r) for r in all_stock.results]})
        except Exception as e:
            return json_response({"error": str(e)}, 500)

    # GET /asset/track
    if "/asset/track" in url and method == "GET":
        return json_response(AssetTracker.process_gps(0.3136, 32.5811, 0.3137, 32.5812, "2026-05-11T16:00:00Z"))

    # 404
    return json_response({"error": "Route not found", "routes": [
        "POST /login", "GET /health", "GET /clients", "POST /clients",
        "GET /clients/<id>", "GET /loans", "POST /loans",
        "POST /loan/calculate", "GET /inventory", "GET /asset/track"
    ]}, 404)
