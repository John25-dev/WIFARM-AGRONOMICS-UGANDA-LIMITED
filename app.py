import json
import hashlib
import hmac
import base64
import time
from js import Response

class WifarmSecurity:
    """Handles Encryption, JWT, and Role-Based Access Control."""
    def __init__(self, secret: str):
        self.secret = secret

    def hash_password(self, password: str) -> str:
        return hashlib.sha256(password.encode()).hexdigest()

    def generate_token(self, user_data: dict) -> str:
        header = self._base64_url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
        payload_data = {
            "uid": user_data["id"],
            "un": user_data["username"],
            "role": user_data["role"],
            "exp": int(time.time()) + 28800  # 8 Hour Session
        }
        payload = self._base64_url_encode(json.dumps(payload_data).encode())
        signature = hmac.new(self.secret.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
        return f"{header}.{payload}.{self._base64_url_encode(signature)}"

    def verify_request(self, request):
        auth_header = request.headers.get("Authorization") or ""
        if not auth_header.startswith("Bearer "): return None
        try:
            parts = auth_header[7:].split(".")
            if len(parts) != 3: return None
            sig = hmac.new(self.secret.encode(), f"{parts[0]}.{parts[1]}".encode(), hashlib.sha256).digest()
            if self._base64_url_encode(sig) != parts[2]: return None
            
            payload = json.loads(self._base64_url_decode(parts[1]))
            if payload.get("exp", 0) < int(time.time()): return None
            return payload
        except: return None

    def _base64_url_encode(self, data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    def _base64_url_decode(self, s: str) -> bytes:
        return base64.urlsafe_b64decode(s + "=" * (4 - len(s) % 4))

class LoanEngine:
    """Automates Interest, Arrears, and Balance calculations."""
    @staticmethod
    async def get_client_statement(db, client_id):
        # Fetch all active loans for the client
        query = "SELECT * FROM loans WHERE client_id = ? AND status = 'ACTIVE'"
        loans = await db.prepare(query).bind(client_id).all()
        
        total_balance = 0.0
        total_arrears = 0.0
        
        for loan in loans.results:
            # Logic: Arrears = Expected Cumulative Payment - Actual Paid
            # This is a simplified production model
            days_overdue = max(0, (int(time.time()) - loan['next_payment_date']) // 86400)
            if days_overdue > 0:
                daily_penalty = loan['amount'] * 0.001 # 0.1% daily penalty example
                total_arrears += (daily_penalty * days_overdue)
            
            total_balance += (loan['balance'] + total_arrears)
            
        return {"balance": round(total_balance, 2), "arrears": round(total_arrears, 2)}

class InventoryManager:
    """Manages branch-level stock and CEO EOD balancing."""
    @staticmethod
    async def get_system_status(db):
        unsynced = await db.prepare("SELECT COUNT(*) as count FROM branch_inventory WHERE is_synced=FALSE").first()
        is_balanced = unsynced['count'] == 0
        return {
            "status": "Balanced" if is_balanced else "Pending Subordinate Submission",
            "pending_branches": unsynced['count']
        }

async def on_fetch(request, env):
    # Initialize Core Classes
    security = WifarmSecurity(env.JWT_SECRET or "wifarm-default-secure-key")
    loan_engine = LoanEngine()
    inventory = InventoryManager()
    
    path = str(request.url)
    method = request.method

    # CORS Preflight
    if method == "OPTIONS":
        return Response.new("", status=204, headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Authorization, Content-Type"
        })

    try:
        # --- PUBLIC ROUTES ---
        if "/login" in path and method == "POST":
            body = await request.json()
            user = await env.DB.prepare("SELECT * FROM users WHERE username=?").bind(body.get("username")).first()
            if user and user['password_hash'] == security.hash_password(body.get("password")):
                token = security.generate_token(user)
                return Response.new(json.dumps({"token": token, "role": user['role']}), status=200)
            return Response.new(json.dumps({"error": "Invalid Credentials"}), status=401)

        # --- PROTECTED ROUTES ---
        user_session = security.verify_request(request)
        if not user_session:
            return Response.new(json.dumps({"error": "Unauthorized"}), status=401)

        # 1. Search Area (Clients, Plates, Serials)
        if "/search" in path and method == "GET":
            search_query = request.headers.get("X-Search-Query") or ""
            sql = """
                SELECT id, full_name, 'CLIENT' as type FROM clients WHERE full_name LIKE ? OR nin LIKE ?
                UNION
                SELECT id, number_plate, 'EQUIPMENT' as type FROM equipment WHERE number_plate LIKE ? OR serial_code LIKE ?
            """
            term = f"%{search_query}%"
            results = await env.DB.prepare(sql).bind(term, term, term, term).all()
            return Response.new(json.dumps(list(results.results)), status=200)

        # 2. Client Dashboard Data
        if "/client-summary" in path:
            client_id = user_session['uid'] # Or passed via query param
            finances = await loan_engine.get_client_statement(env.DB, client_id)
            return Response.new(json.dumps(finances), status=200)

        # 3. CEO Dashboard (Branch Balancing)
        if "/admin/status" in path:
            if user_session['role'] != 'ceo':
                return Response.new(json.dumps({"error": "Forbidden"}), status=403)
            status = await inventory.get_system_status(env.DB)
            return Response.new(json.dumps(status), status=200)

        return Response.new(json.dumps({"error": "Endpoint Not Found"}), status=404)

    except Exception as e:
        return Response.new(json.dumps({"error": str(e)}), status=500)
