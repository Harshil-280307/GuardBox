"""
FCM Token Database Inspection Script for Veronic GuardBox
Reads and inspects guardbox/notification_tokens in Firebase Realtime Database without exposing token values.
"""

import sys
import logging
import firebase_admin
from firebase_admin import credentials, db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("inspect_fcm_tokens")

def init_firebase():
    if not firebase_admin._apps:
        cred = credentials.Certificate("serviceAccountKey.json")
        firebase_admin.initialize_app(cred, {
            "databaseURL": "https://guardbox-jewelleryshop-default-rtdb.firebaseio.com"
        })
    logger.info("Firebase Admin initialized successfully.")

def inspect_tokens():
    tokens_tree = db.reference("guardbox/notification_tokens").get()
    
    owner_uids = 0
    records = []
    
    if isinstance(tokens_tree, dict):
        owner_uids = len(tokens_tree)
        for uid, token_map in tokens_tree.items():
            if isinstance(token_map, dict):
                for tid, tdata in token_map.items():
                    if isinstance(tdata, dict):
                        tok = tdata.get("token") or ""
                        records.append({
                            "uid": uid,
                            "token_id": tid,
                            "token_length": len(tok),
                            "device_id": tdata.get("device_id", "N/A"),
                            "platform": tdata.get("platform", "android"),
                            "updated_at": tdata.get("updated_at", "N/A")
                        })
                        
    print("=" * 60)
    print("FCM TOKEN DATABASE INSPECTION")
    print(f"Owner UID nodes: {owner_uids}")
    print(f"Android token records: {len(records)}")
    print("=" * 60)
    
    for idx, rec in enumerate(records, 1):
        print(f"Record #{idx}")
        print(f"device_id={rec['device_id']}")
        print(f"platform={rec['platform']}")
        print(f"token_length={rec['token_length']}")
        print(f"updated_at={rec['updated_at']}")
        print(f"path=guardbox/notification_tokens/{rec['uid']}/{rec['token_id']}")
        print("-" * 60)

if __name__ == "__main__":
    init_firebase()
    inspect_tokens()
