import json
import hashlib
import hmac
import base64
import time
from js import Response

SECRET = "wifarm-secret-key-change-in-production"


def ok(data, status=200):
    h = {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Authorization, Content-Type",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    }
    return Response.new(json.dumps(data), headers=h, status=status)


def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()


def b64e(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def b64d(s):
    s += "=" * (4 - len(s) % 4)
    return base64.urlsafe_b64decode(s)


def make_token(uid, uname, role):
    h = b64e(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    exp = int(time.time()) + 28800
    p = b64e(json.dumps({"user_id": uid, "username": uname, "role": role, "exp": exp}).encode())
    sig = hmac.new(SECRET.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest()
    return f"{h}.{p}.{b64e(sig)}"


def check_token(request):
    try:
        auth = request.headers.get("Authorization") or ""
        if not auth.startswith("Bearer "):
            return None
        parts = auth[7:].split(".")
        if len(parts) != 3:
            return None
        msg = f"{parts[0]}.{parts[1]}".encode()
        expected = hmac.new(SECRET.encode(), msg, hashlib.sha256).digest()
        if expected != b64d(parts[2]):
            return None
        payload = json.loads(b64d(parts[1]))
        if payload.get("exp", 0) < int(time.time()):
            return None
        return payload
    except Exception:
        return None


async def on_fetch(request, env):
    method = request.method
    url = str(request.url)

    if method == "OPTIONS":
        h = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Authorization, Content-Type",
        }
        return Response.new("", status=204, headers=h)

    try:
        if "/login" in url and method == "POST":
            body = await request.json()
            uname = body.get("username", "")
            pw = hash_pw(body.get("password", ""))
            q = "SELECT id, username, role FROM users WHERE username=? AND password_hash=?"
            row = await env.DB.prepare(q).bind(uname, pw).first()
            if not row:
                return ok({"error": "Invalid credentials"}, 401)
            token = make_token(row["id"], row["username"], row["role"])
            return ok({"token": token, "role": row["role"]})

        if "/clients" in url and method == "GET":
            user = check_token(request)
            if not user:
                return ok({"error": "Unauthorized"}, 401)
            q = "SELECT * FROM clients"
            rows = await env.DB.prepare(q).all()
            return ok(list(rows.results))

        if "/clients" in url and method == "POST":
            user = check_token(request)
            if not user:
                return ok({"error": "Unauthorized"}, 401)
            body = await request.json()
            q = "INSERT INTO clients (full_name, contact_phone, next_of_kin) VALUES (?,?,?)"
            await env.DB.prepare(q).bind(
                body.get("full_name"),
                body.get("contact_phone"),
                body.get("next_of_kin"),
            ).run()
            return ok({"success": True})

        if "/loans" in url and method == "GET":
            user = check_token(request)
            if not user:
                return ok({"error": "Unauthorized"}, 401)
            q = "SELECT loans.*, clients.full_name FROM loans JOIN clients ON loans.client_id=clients.id"
            rows = await env.DB.prepare(q).all()
            return ok(list(rows.results))

        if "/dashboard" in url and method == "GET":
            user = check_token(request)
            if not user or user.get("role") != "ceo":
                return ok({"error": "Forbidden"}, 403)
            q1 = "SELECT COUNT(*) as cnt FROM branch_inventory WHERE is_synced=FALSE"
            q2 = "SELECT SUM(balance) as total FROM loans WHERE status='ACTIVE'"
            unsynced = await env.DB.prepare(q1).first()
            loans = await env.DB.prepare(q2).first()
            n = unsynced["cnt"]
            inv = "Balanced" if n == 0 else str(n) + " branches unsynced"
            return ok({"inventory_status": inv, "total_loan_exposure": loans["total"] or 0})

        return ok({"error": "Route not found"}, 404)

    except Exception as e:
        return ok({"error": str(e)}, 500)
