"""Diagnostic test for Google Photos API access."""
import requests
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

SCOPES = [
    "https://www.googleapis.com/auth/presentations",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/photoslibrary",
    "https://www.googleapis.com/auth/photoslibrary.sharing",
]

creds = Credentials.from_authorized_user_file("oauth_token.json", SCOPES)
creds.refresh(Request())

print("=== Token info ===")
ti = requests.get(f"https://oauth2.googleapis.com/tokeninfo?access_token={creds.token}").json()
print("email  :", ti.get("email"))
print("scope  :", ti.get("scope"))
print("aud    :", ti.get("aud"))
print("error  :", ti.get("error"))

print("\n=== GET /mediaItems (no filter) ===")
r = requests.get(
    "https://photoslibrary.googleapis.com/v1/mediaItems",
    headers={"Authorization": f"Bearer {creds.token}"},
    params={"pageSize": 1},
    timeout=15,
)
print("status:", r.status_code)
print("body  :", r.text[:300])

print("\n=== POST /mediaItems:search ===")
r2 = requests.post(
    "https://photoslibrary.googleapis.com/v1/mediaItems:search",
    headers={"Authorization": f"Bearer {creds.token}"},
    json={"pageSize": 1},
    timeout=15,
)
print("status:", r2.status_code)
print("body  :", r2.text[:300])
