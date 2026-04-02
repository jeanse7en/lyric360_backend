"""
Run this script to diagnose service account + API permissions:
  python check_service_account.py
"""
import json
import sys

SERVICE_ACCOUNT_FILE = "service_account.json"

print("=== Step 1: Load service account file ===")
try:
    with open(SERVICE_ACCOUNT_FILE) as f:
        sa = json.load(f)
    print(f"  ✓ File loaded")
    print(f"  Project:       {sa.get('project_id')}")
    print(f"  Client email:  {sa.get('client_email')}")
    print(f"  Type:          {sa.get('type')}")
except FileNotFoundError:
    print(f"  ✗ File not found: {SERVICE_ACCOUNT_FILE}")
    sys.exit(1)
except Exception as e:
    print(f"  ✗ Error: {e}")
    sys.exit(1)

print()
print("=== Step 2: Build credentials ===")
try:
    from google.oauth2 import service_account
    SCOPES = [
        "https://www.googleapis.com/auth/presentations",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    print(f"  ✓ Credentials created for: {creds.service_account_email}")
except Exception as e:
    print(f"  ✗ Error building credentials: {e}")
    sys.exit(1)

SHARED_DRIVE_ID = input("\nEnter your Shared Drive ID (from the URL after /folders/): ").strip()

print()
print("=== Step 2b: Verify Slides API is enabled via serviceusage ===")
try:
    import urllib.request, json as _json
    creds.refresh(__import__("google.auth.transport.requests", fromlist=["Request"]).Request())
    req = urllib.request.Request(
        f"https://serviceusage.googleapis.com/v1/projects/{sa.get('project_id')}/services/slides.googleapis.com",
        headers={"Authorization": f"Bearer {creds.token}"},
    )
    with urllib.request.urlopen(req) as resp:
        svc = _json.loads(resp.read())
    state = svc.get("state", "UNKNOWN")
    print(f"  Slides API state: {state}")
    if state != "ENABLED":
        print(f"  ✗ NOT ENABLED — go to:")
        print(f"    https://console.cloud.google.com/apis/library/slides.googleapis.com?project={sa.get('project_id')}")
        sys.exit(1)
    print(f"  ✓ Slides API is ENABLED")
except Exception as e:
    print(f"  (Could not check via serviceusage: {e})")

print()
print("=== Step 3: Test Google Slides API (create presentation in Shared Drive) ===")
try:
    from googleapiclient.discovery import build
    slides = build("slides", "v1", credentials=creds)
    drive = build("drive", "v3", credentials=creds)

    pres = slides.presentations().create(body={"title": "[TEST] lyric360 check"}).execute()
    pres_id = pres["presentationId"]
    print(f"  ✓ Presentation created: {pres_id}")

    # Move to Shared Drive
    drive.files().update(
        fileId=pres_id,
        addParents=SHARED_DRIVE_ID,
        removeParents="root",
        supportsAllDrives=True,
        fields="id,parents",
    ).execute()
    print(f"  ✓ Moved to Shared Drive")
    print(f"  URL: https://docs.google.com/presentation/d/{pres_id}/edit")

    # Clean up
    drive.files().delete(fileId=pres_id, supportsAllDrives=True).execute()
    print(f"  ✓ Test presentation deleted (cleanup)")
except Exception as e:
    print(f"  ✗ Error: {e}")
    print()
    print("  --> Fix:")
    print("  1. Create a Shared Drive at drive.google.com → 'Shared drives' → '+ New'")
    print(f"  2. Add {sa.get('client_email')} as Content Manager")
    print("  3. Set SLIDES_OUTPUT_FOLDER_ID=<shared-drive-id> in .env")
    sys.exit(1)

print()
print("=== Step 4: Test Google Drive API (list Shared Drive) ===")
try:
    result = drive.files().list(
        driveId=SHARED_DRIVE_ID,
        corpora="drive",
        includeItemsFromAllDrives=True,
        supportsAllDrives=True,
        pageSize=1,
        fields="files(id,name)",
    ).execute()
    print(f"  ✓ Drive API accessible — Shared Drive is readable")
except Exception as e:
    print(f"  ✗ Error: {e}")
    sys.exit(1)

print()
print("=== All checks passed ✓ ===")
