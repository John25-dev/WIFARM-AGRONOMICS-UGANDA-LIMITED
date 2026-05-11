import json
import hashlib
import hmac
import base64
import time
from js import Response

class WifarmSecurity:
    """Enterprise Security: JWT, Domain Locking, and Role Management."""
    def __init__(self, secret: str):
        self.secret = secret

    def hash_password(self, password: str) -> str:
        return hashlib.sha256(password.encode()).hexdigest()

    def generate_token(self, user_data: dict) -> str:
        header = self._e64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
        payload = self._e64(json.dumps({
            "uid": user_data["id"],
            "un": user_data["username"],
            "role": user_data["role"],
            "exp": int(time.time()) + 28800
        }).encode())
        sig = hmac.new(self.secret.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
        return f"{header}.{payload}.{self._e64(sig)}"

    def verify_request(self, request):
        a = request.headers.get("Authorization") or ""
        if not a.startswith("Bearer "): return None
        try:
            pts = a[7:].split(".")
            if len(pts) != 3: return None
            sig = hmac.new(self.secret.encode(), f"{pts[0]}.{pts[1]}".encode(), hashlib.sha256).digest()
            if self._e64(sig) != pts[2]: return None
            pl = json.loads(self._d64(pts[1]))
            if pl.get("exp", 0) < int(time.time()): return None
            return pl
        except: return None

    def _e64(self, d: bytes) -> str: return base64.urlsafe_b64encode(d).rstrip(b"=").decode()
    def _d64(self, s: str) -> bytes: return base64.urlsafe_b64decode(s + "=" * (4 - len(s) % 4))

class LoanEngine:
    """Automated Financial Calculations for Dashboard."""
    @staticmethod
    async def get_client_summary(db, client_id):
        q = "SELECT balance, next_payment_date FROM loans WHERE client_id = ? AND status = 'ACTIVE'"
        loans = await db.prepare(q).bind(client_id).all()
        total_bal = 0.0
        total_arr = 0.0
        now = int(time.time())

        for l in loans.results:
            days_late = max(0, (now - l['next_payment_date']) // 86400)
            arrears = (l['balance'] * 0.001 * days_late) if days_late > 0 else 0
            total_bal += (l['balance'] + arrears)
            total_arr += arrears
        return {"balance": round(total_bal, 2), "arrears": round(total_arr, 2)}

class OnboardingManager:
    """Strict Client Registration with 3-Relative Rule."""
    @staticmethod
    async def register(db, data):
        rels = data.get("relatives", [])
        if len(rels) != 3:
            return {"error": "Failed: Exactly 3 relatives are required for security verification."}
        
        try:
            q = """INSERT INTO clients (full_name, nin, contact_phone, next_of_kin_name, next_of_kin_contact) 
                   VALUES (?, ?, ?, ?, ?)"""
            res = await db.prepare(q).bind(
                data.get("full_name"), data.get("nin"), data.get("contact_phone"),
                data.get("nok_name"), data.get("nok_phone")
            ).run()
            
            client_id = res.meta.last_row_id
            for r in rels:
                rq = "INSERT INTO client_relatives (client_id, relative_name, relationship, contact_phone) VALUES (?,?,?,?)"
                await db.prepare(rq).bind(client_id, r['name'], r['relation'], r['phone']).run()
            return {"success": True, "id": client_id}
        except Exception as e:
            return {"error": "Database error or Duplicate NIN detected."}

def ok(d, c=200):
    h = {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*", 
         "Access-Control-Allow-Headers": "Authorization, Content-Type", "Access-Control-Allow-Methods": "GET, POST, OPTIONS"}
    return Response.new(json.dumps(d), headers=h, status=c)

async def on_fetch(request, env):
    sec = WifarmSecurity(env.JWT_SECRET or "wifarm-default-key")
    path = str(request.url)
    method = request.method

    if method == "OPTIONS":
        return Response.new("", status=204, headers={
            "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Authorization, Content-Type"
        })

    try:
        # --- PUBLIC: LOGIN ---
        if "/login" in path and method == "POST":
            b = await request.json()
            u = await env.DB.prepare("SELECT * FROM users WHERE username=?").bind(b.get("username")).first()
            if u and u['password_hash'] == sec.hash_password(b.get("password")):
                return ok({"token": sec.generate_token(u), "role": u['role']})
            return ok({"error": "Invalid login"}, 401)

        # --- PROTECTED: REQUIRES LOGIN ---
        session = sec.verify_request(request)
        if not session: return ok({"error": "Unauthorized"}, 401)

        # 1. Search Logic (Universal Lookup)
        if "/search" in path:
            sq = request.headers.get("X-Search-Query") or ""
            term = f"%{sq}%"
            res = await env.DB.prepare("""
                SELECT id, full_name as name, 'CLIENT' as type FROM clients WHERE full_name LIKE ? OR nin LIKE ?
                UNION
                SELECT id, number_plate as name, 'EQUIPMENT' as type FROM equipment WHERE number_plate LIKE ? OR serial_code LIKE ?
            """).bind(term, term, term, term).all()
            return ok(list(res.results))

        # 2. Client Dashboard Stats
        if "/client-summary" in path:
            cid = request.headers.get("X-Client-ID") or session['uid']
            stats = await LoanEngine.get_client_summary(env.DB, cid)
            return ok(stats)

        # 3. New Client Onboarding
        if "/onboard" in path and method == "POST":
            b = await request.json()
            res = await OnboardingManager.register(env.DB, b)
            return ok(res)

        # 4. CEO Branch Balance Check
        if "/admin/sync-check" in path:
            if session['role'] != 'ceo': return ok({"error": "Forbidden"}, 403)
            unsynced = await env.DB.prepare("SELECT COUNT(*) as count FROM branch_inventory WHERE is_synced=FALSE").first()
            return ok({"status": "Balanced" if unsynced['count'] == 0 else f"{unsynced['count']} branches pending"})

        return ok({"error": "Not found"}, 404)

    except Exception as e:
        return ok({"error": str(e)}, 500)
