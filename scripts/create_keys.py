import os, requests
from dotenv import load_dotenv
load_dotenv()
GATEWAY = os.environ.get("GATEWAY_URL", "http://localhost:8000")
ADMIN = os.environ["ADMIN_TOKEN"]
users = ["user1", "user2", "user3", "user4", "user5"]
with open("keys.txt", "w") as f:
    for u in users:
        r = requests.post(f"{GATEWAY}/admin/keys", json={"user_name": u},
                          headers={"Authorization": f"Bearer {ADMIN}"})
        r.raise_for_status()
        key = r.json()["api_key"]
        print(u, key)
        f.write(f"{u} {key}\n")
print("Saved to keys.txt  (do NOT push this file to GitHub)")