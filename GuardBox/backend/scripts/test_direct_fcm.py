"""
Direct FCM Test Script for Veronic GuardBox
Tests FCM token discovery and dispatches a test push notification to registered devices.
"""

import sys
import logging
from datetime import datetime, timezone
import firebase_admin
from firebase_admin import credentials, db, messaging

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("direct_fcm_test")

def init_firebase():
    if not firebase_admin._apps:
        cred = credentials.Certificate("serviceAccountKey.json")
        firebase_admin.initialize_app(cred, {
            "databaseURL": "https://guardbox-jewelleryshop-default-rtdb.firebaseio.com"
        })
    logger.info("Firebase Admin initialized successfully.")

def discover_tokens():
    tokens_tree = db.reference("guardbox/notification_tokens").get()
    discovered = []
    if isinstance(tokens_tree, dict):
        for uid, token_map in tokens_tree.items():
            if isinstance(token_map, dict):
                for tid, tdata in token_map.items():
                    if isinstance(tdata, dict):
                        tok = tdata.get("token")
                        if tok:
                            discovered.append({
                                "uid": uid,
                                "token_id": tid,
                                "token": tok,
                                "token_length": len(tok),
                                "device_id": tdata.get("device_id", ""),
                                "platform": tdata.get("platform", "android"),
                                "updated_at": tdata.get("updated_at", "")
                            })
    return discovered

def send_direct_test_push(token_info):
    tok = token_info["token"]
    masked = tok[:6] + "••••" if len(tok) >= 10 else "••••"
    logger.info(f"Sending direct test push to token (length: {len(tok)}, device_id: {token_info['device_id']})...")

    title = "GuardBox Test Alert"
    body = "Remote notification test"

    data_payload = {
        "alert_id": "manual-test-001",
        "device_id": "guardbox-shop-f20424b4",
        "type": "TEST_ALERT",
        "severity": "HIGH",
        "camera_name": "Test Security Zone",
        "event_type": "TEST_ALERT",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    msg = messaging.Message(
        token=tok,
        notification=messaging.Notification(
            title=title,
            body=body
        ),
        data=data_payload,
        android=messaging.AndroidConfig(
            priority="high",
            notification=messaging.AndroidNotification(
                channel_id="guardbox_security_alerts",
                sound="guardbox_emergency_alert",
                priority="max",
                default_vibrate_timings=True
            )
        )
    )

    try:
        msg_id = messaging.send(msg)
        logger.info(f"FCM send: SUCCESS (Message ID: {msg_id})")
        return True, msg_id, None
    except Exception as e:
        logger.error(f"FCM send: FAIL (Exception: {e})")
        return False, None, str(e)

def main():
    init_firebase()
    tokens = discover_tokens()
    print("=" * 60)
    print(f"FCM TOKENS FOUND = {len(tokens)}")
    for idx, t in enumerate(tokens):
        print(f"Token #{idx + 1}: token_length={t['token_length']}, device_id={t['device_id']}, platform={t['platform']}, updated_at={t['updated_at']}")
    print("=" * 60)

    if not tokens:
        print("No tokens found in Firebase. Please open the Android app in REMOTE mode to register token.")
        sys.exit(1)

    # Test the latest token
    latest_token = tokens[-1]
    success, msg_id, err = send_direct_test_push(latest_token)
    if success:
        print("FCM DIRECT TEST: SUCCESS")
    else:
        print(f"FCM DIRECT TEST: FAILED - {err}")

if __name__ == "__main__":
    main()
