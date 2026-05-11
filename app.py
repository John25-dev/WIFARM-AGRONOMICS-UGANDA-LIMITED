import json
import hashlib
import hmac
import base64
import time
from js import Response

JWT_SECRET = "wifarm-secret-key-change-in-production"

def json_response(data, status=200):
    return Response.new(
        json.dumps(data),
        headers={
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Authorization, Content-Type",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS"
        },
        status=status
    )

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def b64url_encode(data):
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()

def b64url_decode(s):
    s += '=' * (4 - len(s) % 4)
    return base64.urlsafe_b64decode(s)

def create_token(user_id, username, role):
    header = b64url_encode(json.dumps({"alg":"HS256","typ":"JWT"}).encode())
    payload = b64url_encode(json.dumps({
        "user_id": user_id,
        "username": username,
        "role": role,
        "exp": int(time.time()) + 28800
    }).encode())
    sig = hmac.new(JWT_SECRET.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
    return f"{header}.{payload}.{b64url_encode(sig)}"

def verify_token(request):
    try:
        auth = request.headers.get("Authorization") or ""
        if not auth.startswith("Bearer "):
            return None
        parts = auth[7:].split(".")
        if len(parts) != 3:
            return None
        msg = f"{parts[0]}.{parts[1]}".encode()
        expected = hmac.new(JWT_SECRET.encode(), msg, hashlib.sha256).digest()
        if expected != b64url_decode(parts[2]):
            return None
        payload = json.loads(b64url_decode(parts[1]))
        if payload.get("exp", 0) < int(time.time()):
            return None
        return payload
    except Exception:
        return None

async def on_fetch(request, env):
    method = request.method
    url = str(request.url)

    if method == "OPTIONS":
        return Response.new("", status=204, headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Authorization, Content-Type"
        })

    try:
        if "/login" in url and method == "POST":
            body = await request.json()
            username = body.get("username", "")
            password_hash = hash_password(body.get("password", ""))
            result = await env.DB.prepare(
                "SELECT id, username, role FROM users WHERE username
