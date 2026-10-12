"""
Deploy database.rules.json to Firebase Realtime Database
"""
import os
import json
import requests
from google.oauth2 import service_account
from google.auth.transport.requests import Request

CRED_PATH = os.path.join(os.path.dirname(__file__), "..", "serviceAccountKey.json")
RULES_PATH = os.path.join(os.path.dirname(__file__), "..", "database.rules.json")
DB_URL = "https://guardbox-jewelleryshop-default-rtdb.firebaseio.com"

def get_access_token():
    scopes = [
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/firebase.database"
    ]
    creds = service_account.Credentials.from_service_account_file(CRED_PATH, scopes=scopes)
    creds.refresh(Request())
    return creds.token

def get_current_rules(token):
    res = requests.get(f"{DB_URL}/.settings/rules.json", headers={"Authorization": f"Bearer {token}"})
    print("GET rules status:", res.status_code)
    print("Current rules in Firebase:")
    print(res.text)
    return res.json() if res.status_code == 200 else None

def deploy_rules(token, rules_dict):
    res = requests.put(
        f"{DB_URL}/.settings/rules.json",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=rules_dict
    )
    print("PUT rules status:", res.status_code)
    print("Response:", res.text)
    return res.status_code == 200

if __name__ == "__main__":
    token = get_access_token()
    print("Acquired token successfully.")
    
    with open(RULES_PATH, "r", encoding="utf-8") as f:
        rules = json.load(f)
        
    print(f"Deploying updated rules from {RULES_PATH}...")
    success = deploy_rules(token, rules)
    if success:
        print("[SUCCESS] Firebase RTDB rules deployed successfully.")
        print("\nVerifying newly deployed rules from Firebase...")
        get_current_rules(token)
    else:
        print("[ERROR] Failed to deploy rules to Firebase RTDB.")
