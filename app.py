import json
import hashlib
import hmac
import base64
import time
from js import Response

S = "wifarm-secret-key"

def ok(d, c=200):
    h = {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "Authorization, Content-Type", "Access-Control-Allow-Methods": "GET, POST, OPTIONS"}
    return Response.new(json.dumps(d), headers=h, status=c)

def hp(p):
    return hashlib.sha256(p.encode()).hexdigest()

def e64(d):
    return base64.urlsafe_b64encode(d).rstrip(b"=").decode()

def d64(s):
    s += "=" * (4 - len(s) % 4)
    return base64.urlsafe_b64decode(s)

def mkt(uid, un, role):
    h = e64(json.dumps({"alg": "HS256"}).encode())
    p = e64(json.dumps({"uid": uid, "un": un, "role": role, "exp": int(time.time()) + 28800}).encode())
    sig = hmac.new(S.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest()
    return f"{h}.{p}.{e64(sig)}"

def chkt(req):
    try:
        a = req.headers.get("Authorization") or ""
        if not a.startswith("Bearer "):
            return None
        pts = a[7:].split(".")
        if len(pts) != 3:
            return None
        exp = hmac.new(S.encode(), f"{pts[0]}.{pts[1]}".encode(), hashlib.sha256).digest()
        if exp != d64(pts[2]):
            return None
        pl = json.loads(d64(pts[1]))
        if pl.get("exp", 0) < int(time.time()):
            return None
        return pl
    except Exception:
        return None

async def on_fetch(request, env):
    m = request.method
    u = str(request.url)
    if m == "OPTIONS":
        return Response.new("", status=204, headers={"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "GET, POST, OPTIONS", "Access-Control-Allow-Headers": "Authorization, Content-Type"})
    try:
        if "/login" in u and m == "POST":
            b = await request.json()
            q = "SELECT id, username, role FROM users WHERE username=? AND password_hash=?"
            r = await env.DB.prepare(q).bind(b.get("username", ""), hp(b.get("password", ""))).first()
            if not r:
                return ok({"error": "Invalid credentials"}, 401)
            return ok({"token": mkt(r["id"], r["username"], r["role"]), "role": r["role"]})
        if "/clients" in u and m == "GET":
            if not chkt(request):
                return ok({"error": "Unauthorized"}, 401)
            r = await env.DB.prepare("SELECT * FROM clients").all()
            return ok(list(r.results))
        if "/clients" in u and m == "POST":
            if not chkt(request):
                return ok({"error": "Unauthorized"}, 401)
            b = await request.json()
            q = "INSERT INTO clients (full_name, contact_phone, next_of_kin) VALUES (?,?,?)"
            await env.DB.prepare(q).bind(b.get("full_name"), b.get("contact_phone"), b.get("next_of_kin")).run()
            return ok({"success": True})
        if "/loans" in u and m == "GET":
            if not chkt(request):
                return ok({"error": "Unauthorized"}, 401)
            q = "SELECT loans.*, clients.full_name FROM loans JOIN clients ON loans.client_id=clients.id"
            r = await env.DB.prepare(q).all()
            return ok(list(r.results))
        if "/dashboard" in u and m == "GET":
            user = chkt(request)
            if not user or user.get("role") != "ceo":
                return ok({"error": "Forbidden"}, 403)
            q1 = "SELECT COUNT(*) as cnt FROM branch_inventory WHERE is_synced=FALSE"
            q2 = "SELECT SUM(balance) as tot FROM loans WHERE status='ACTIVE'"
            u1 = await env.DB.prepare(q1).first()
            l1 = await env.DB.prepare(q2).first()
            return ok({"inventory": "Balanced" if u1["cnt"] == 0 else str(u1["cnt"]) + " unsynced", "exposure": l1["tot"] or 0})
        return
