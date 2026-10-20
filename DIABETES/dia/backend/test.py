"""
Run this from your backend folder:
  python test.py
It will tell you exactly what is working and what is not.
"""
import urllib.request
import json

BASE = "http://127.0.0.1:5000"

def test(label, url, method="GET", data=None):
    try:
        body = json.dumps(data).encode() if data else None
        req  = urllib.request.Request(url, data=body, method=method,
               headers={"Content-Type": "application/json"})
        res  = urllib.request.urlopen(req, timeout=5)
        resp = json.loads(res.read())
        print(f"  ✅  {label}: OK → {resp}")
        return resp
    except Exception as e:
        print(f"  ❌  {label}: FAILED → {e}")
        return None

print("\n── DIABETRIX CONNECTION TEST ──\n")

# 1. Health check
test("Flask running", f"{BASE}/api/health")

# 2. Signup
result = test("Firebase signup", f"{BASE}/api/auth/signup", "POST", {
    "name": "TestUser",
    "email": "testuser123@gmail.com",
    "password": "test123456"
})

# 3. Login with same credentials
if result:
    test("Firebase login", f"{BASE}/api/auth/login", "POST", {
        "email": "testuser123@gmail.com",
        "password": "test123456"
    })

print("\n── If all show ✅ your app is fully working ──\n")
print("Now check Firebase Console → Firestore → you should see a 'users' collection\n")