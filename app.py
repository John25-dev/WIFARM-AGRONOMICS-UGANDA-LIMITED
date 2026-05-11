import json
import hashlib
import base64
import time
from js import Response, crypto, TextEncoder, Object

JWT_SECRET = "wifarm-secret-key-change-in-production"

# ─── Helpers ────────────────────────────────────────────────────

def json_response(data, status=200):
    headers = {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Authorization, Content-Type",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS"
    }
    return Response.new(json.dumps(data), status=status, headers=headers)

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()

def b64url_decode(s: str) -> bytes:
    padding = 4 - len(s) % 4
    if padding != 4:
        s += '=' * padding
    return base64.urlsafe_b64decode(s)

def create_token(user_id, username, role) -> str:
    header = b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = b64url_encode(json.dumps({
        "user_id": user_id,
        "username": username,
        "role": role,
        "exp": int(time.time()) + 28800  # 8 hours
    }).encode())
    import hmac as hmac_lib
    signature = hmac_lib.new(
        JWT_SECRET.encode(),
        f"{header}.{payload}".encode(),
        hashlib.sha256
    ).digest()
    return f"{header}.{payload}.{b64url_encode(signature)}"

def verify_token(request):
    auth = request.headers.get("Authorization") or ""
    if not auth.startswith("Bearer "):
        return None
    token = auth[7:]
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header_payload = f"{parts[0]}.{parts[1]}"
        import hmac as hmac_lib
        expected_sig = hmac_lib.new(
            JWT_SECRET.encode(),
            header_payload.encode(),
            hashlib.sha256
        ).digest()
        actual_sig = b64url_decode(parts[2])
        if expected_sig != actual_sig:
            return None
        payload = json.loads(b64url_decode(parts[1]))
        if payload.get("exp", 0) < int(time.time()):
            return None
        return payload
    except Exception:
        return None

# ─── Route Handlers ─────────────────────────────────────────────

async def handle_login(request, env):
    try:
        body = await request.json()
        username = body.get("username", "")
        password = body.get("password", "")
        password_hash = hash_password(password)

        result = await env.DB.prepare(
            "SELECT id, username, role FROM users WHERE username = ? AND password_hash = ?"
        ).bind(username, password_hash).first()

        if not result:
            return json_response({"error": "Invalid credentials"}, 401)

        token = create_token(result["id"], result["username"], result["role"])
        return json_response({"token": token, "role": result["role"]})
    except Exception as e:
        return json_response({"error": str(e)}, 500)

async def handle_get_clients(request, env):
    user = verify_token(request)
    if not user:
        return json_response({"error": "Unauthorized \u2014 please log in"}, 401)
    try:
        results = await env.DB.prepare("SELECT * FROM clients").all()
        return json_response(list(results.results))
    except Exception as e:
        return json_response({"error": str(e)}, 500)

async def handle_add_client(request, env):
    user = verify_token(request)
    if not user:
        return json_response({"error": "Unauthorized"}, 401)
    try:
        body = await request.json()
        await env.DB.prepare(
            "INSERT INTO clients (full_name, contact_phone, next_of_kin) VALUES (?, ?, ?)"
        ).bind(body.get("full_name"), body.get("contact_phone"), body.get("next_of_kin")).run()
        return json_response({"success": True, "message": "Client added"})
    except Exception as e:
        return json_response({"error": str(e)}, 500)

async def handle_get_loans(request, env):
    user = verify_token(request)
    if not user:
        return json_response({"error": "Unauthorized"}, 401)
    try:
        results = await env.DB.prepare(
            "SELECT loans.*, clients.full_name FROM loans JOIN clients ON loans.client_id = clients.id"
        ).all()
        return json_response(list(results.results))
    except Exception as e:
        return json_response({"error": str(e)}, 500)

async def handle_ceo_dashboard(request, env):
    user = verify_token(request)
    if not user or user.get("role") != "ceo":
        return json_response({"error": "Forbidden \u2014 CEO access only"}, 403)
    try:
        unsynced = await env.DB.prepare(
            "SELECT COUNT(*) as count FROM branch_inventory WHERE is_synced = FALSE"
        ).first()
        loans = await env.DB.prepare(
            "SELECT SUM(balance) as total FROM loans WHERE status='ACTIVE'"
        ).first()
        status = "Balanced" if unsynced["count"] == 0 else f"Unbalanced \u2014 {unsynced['count']} branches pending"
        return json_response({
            "inventory_status": status,
            "total_loan_exposure": loans["total"] or 0
        })
    except Exception as e:
        return json_response({"error": str(e)}, 500)

# ─── Main Router ─────────────────────────────────────────────────

async def on_fetch(request, env):
    method = request.method
    url = str(request.url)

    if method == "OPTIONS":
        return Response.new("", status=204, headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Authorization, Content-Type"
        })

    if "/login" in url and method == "POST":
        return await handle_login(request, env)
    elif "/clients" in url and method == "GET":
        return await handle_get_clients(request, env)
    elif "/clients" in url and method == "POST":
        return await handle_add_client(request, env)
    elif "/loans" in url and method == "GET":
        return await handle_get_loans(request, env)
    elif "/dashboard" in url and method == "GET":
        return await handle_ceo_dashboard(request, env)

    return json_response({"error": "Route not found"}, 404)
