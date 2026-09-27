import os, time, json, hashlib, secrets, sqlite3
import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv

load_dotenv()
BACKEND_URL = os.environ["BACKEND_URL"]          # e.g. https://xxxx.endpoints.huggingface.cloud/v1
BACKEND_TOKEN = os.environ.get("BACKEND_TOKEN", "")
BACKEND_MODEL = os.environ.get("BACKEND_MODEL", "tgi")
ADMIN_TOKEN = os.environ["ADMIN_TOKEN"]
DB = os.environ.get("DB_PATH", "gateway.db")

app = FastAPI(title="LLM Gateway")


def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    con = db()
    con.execute("""CREATE TABLE IF NOT EXISTS api_keys(
        id INTEGER PRIMARY KEY, user_name TEXT, key_hash TEXT UNIQUE,
        active INTEGER DEFAULT 1, created_at REAL)""")
    con.execute("""CREATE TABLE IF NOT EXISTS logs(
        id INTEGER PRIMARY KEY, user_name TEXT, prompt TEXT, response TEXT,
        prompt_tokens INTEGER, completion_tokens INTEGER,
        latency_ms INTEGER, status INTEGER, created_at REAL)""")
    con.commit()


init_db()


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def check_admin(token):
    if token != f"Bearer {ADMIN_TOKEN}":
        raise HTTPException(401, "admin only")


def get_user(authorization):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing API key")
    key = authorization.removeprefix("Bearer ")
    row = db().execute("SELECT user_name FROM api_keys WHERE key_hash=? AND active=1",
                       (hash_key(key),)).fetchone()
    if not row:
        raise HTTPException(401, "invalid or revoked API key")
    return row["user_name"]


# ---------- admin: manage keys ----------
@app.post("/admin/keys")
def create_key(body: dict, authorization: str = Header(None)):
    check_admin(authorization)
    key = "sk-" + secrets.token_urlsafe(24)       # shown ONCE, we only store the hash
    con = db()
    con.execute("INSERT INTO api_keys(user_name,key_hash,created_at) VALUES(?,?,?)",
                (body["user_name"], hash_key(key), time.time()))
    con.commit()
    return {"user_name": body["user_name"], "api_key": key}


@app.get("/admin/keys")
def list_keys(authorization: str = Header(None)):
    check_admin(authorization)
    rows = db().execute("SELECT id,user_name,active,created_at FROM api_keys").fetchall()
    return [dict(r) for r in rows]


@app.delete("/admin/keys/{key_id}")
def revoke_key(key_id: int, authorization: str = Header(None)):
    check_admin(authorization)
    con = db()
    con.execute("UPDATE api_keys SET active=0 WHERE id=?", (key_id,))
    con.commit()
    return {"revoked": key_id}


# ---------- users: chat ----------
@app.post("/v1/chat/completions")
async def chat(request: Request, authorization: str = Header(None)):
    user = get_user(authorization)
    body = await request.json()
    body["model"] = BACKEND_MODEL
    body.setdefault("max_tokens", 256)
    prompt = body["messages"][-1]["content"]

    start = time.time()
    async with httpx.AsyncClient(timeout=300) as client:
        r = await client.post(f"{BACKEND_URL}/chat/completions", json=body,
                              headers={"Authorization": f"Bearer {BACKEND_TOKEN}"})
    latency = int((time.time() - start) * 1000)

    data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {"error": r.text}
    answer = data["choices"][0]["message"]["content"] if r.status_code == 200 else json.dumps(data)
    usage = data.get("usage", {}) if r.status_code == 200 else {}

    con = db()
    con.execute("""INSERT INTO logs(user_name,prompt,response,prompt_tokens,completion_tokens,
                   latency_ms,status,created_at) VALUES(?,?,?,?,?,?,?,?)""",
                (user, prompt, answer, usage.get("prompt_tokens"), usage.get("completion_tokens"),
                 latency, r.status_code, time.time()))
    con.commit()

    if r.status_code != 200:
        raise HTTPException(502, f"model backend error: {answer[:300]}")
    return data


# ---------- admin: see logs ----------
@app.get("/admin/logs")
def get_logs(authorization: str = Header(None), user: str = None, limit: int = 50):
    check_admin(authorization)
    q, args = "SELECT * FROM logs", []
    if user:
        q, args = q + " WHERE user_name=?", [user]
    rows = db().execute(q + " ORDER BY id DESC LIMIT ?", args + [limit]).fetchall()
    return [dict(r) for r in rows]


@app.get("/admin/dashboard", response_class=HTMLResponse)
def dashboard(token: str):
    if token != ADMIN_TOKEN:
        raise HTTPException(401, "admin only")
    rows = db().execute("SELECT * FROM logs ORDER BY id DESC LIMIT 100").fetchall()
    stats = db().execute("""SELECT user_name, COUNT(*) n, SUM(COALESCE(completion_tokens,0)) t,
                            AVG(latency_ms) l FROM logs GROUP BY user_name""").fetchall()
    esc = lambda s: (s or "").replace("&", "&amp;").replace("<", "&lt;")
    srows = "".join(f"<tr><td>{s['user_name']}</td><td>{s['n']}</td><td>{s['t']}</td><td>{int(s['l'] or 0)} ms</td></tr>" for s in stats)
    lrows = "".join(
        f"<tr><td>{time.strftime('%d %b %H:%M', time.localtime(r['created_at']))}</td><td>{r['user_name']}</td>"
        f"<td>{esc(r['prompt'])}</td><td>{esc(r['response'])}</td><td>{r['latency_ms']} ms</td><td>{r['status']}</td></tr>"
        for r in rows)
    return f"""<html><head><title>LLM Gateway logs</title><style>
      body{{font-family:sans-serif;margin:24px}} table{{border-collapse:collapse;width:100%;margin-bottom:24px}}
      td,th{{border:1px solid #ccc;padding:6px;vertical-align:top;font-size:14px}} th{{background:#eee}}</style></head>
      <body><h2>Usage per user</h2><table><tr><th>User</th><th>Requests</th><th>Output tokens</th><th>Avg latency</th></tr>{srows}</table>
      <h2>Last 100 requests</h2><table><tr><th>Time</th><th>User</th><th>Prompt</th><th>Response</th><th>Latency</th><th>Status</th></tr>{lrows}</table></body></html>"""