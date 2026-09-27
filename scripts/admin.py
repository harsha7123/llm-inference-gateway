import os, sys, requests
from dotenv import load_dotenv

load_dotenv()
GATEWAY = "http://localhost:8000"
HEADERS = {"Authorization": f"Bearer {os.environ['ADMIN_TOKEN']}"}   # read from .env, never printed

cmd = sys.argv[1] if len(sys.argv) > 1 else "help"

if cmd == "keys":
    for k in requests.get(f"{GATEWAY}/admin/keys", headers=HEADERS).json():
        print(f"id={k['id']:<3} {k['user_name']:<8} {'ACTIVE' if k['active'] else 'REVOKED'}")
elif cmd == "revoke":
    print(requests.delete(f"{GATEWAY}/admin/keys/{sys.argv[2]}", headers=HEADERS).json())
elif cmd == "logs":
    for r in requests.get(f"{GATEWAY}/admin/logs", headers=HEADERS).json():
        print(f"[{r['user_name']}] ({r['status']}, {r['latency_ms']} ms)")
        print(f"   Q: {r['prompt'][:80]}")
        print(f"   A: {(r['response'] or '')[:80]}\n")
else:
    print("usage: python scripts/admin.py keys | revoke <id> | logs")