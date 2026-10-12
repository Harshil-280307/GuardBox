"""
Direct test of LAN IP whitelisting and endpoint authentication in GuardBoxSecurityMiddleware.
"""
import ipaddress
from fastapi.testclient import TestClient
from app.main import app, _is_trusted_local_or_lan

def test_ip_whitelist():
    # Loopback
    assert _is_trusted_local_or_lan("127.0.0.1") is True
    assert _is_trusted_local_or_lan("localhost") is True
    assert _is_trusted_local_or_lan("::1") is True
    assert _is_trusted_local_or_lan("") is True
    
    # RFC 1918 Private LAN
    assert _is_trusted_local_or_lan("192.168.31.188") is True
    assert _is_trusted_local_or_lan("192.168.1.1") is True
    assert _is_trusted_local_or_lan("10.0.0.5") is True
    assert _is_trusted_local_or_lan("172.16.0.100") is True
    assert _is_trusted_local_or_lan("172.31.255.255") is True
    
    # Public WAN / External IPs
    assert _is_trusted_local_or_lan("8.8.8.8") is False
    assert _is_trusted_local_or_lan("1.1.1.1") is False
    assert _is_trusted_local_or_lan("104.26.10.1") is False
    assert _is_trusted_local_or_lan("172.32.0.1") is False
    print("[PASS] IP whitelist CIDR checks pass.")

def test_middleware_requests():
    client = TestClient(app)
    
    # 1. LAN client without API key -> should succeed (HTTP 200)
    res_status = client.get("/system/status", headers={"X-Forwarded-For": "192.168.31.188"})
    assert res_status.status_code == 200, f"Status failed: {res_status.status_code}"
    print(f"[PASS] GET /system/status from LAN: {res_status.status_code}")

    res_arm = client.post("/system/arm")
    assert res_arm.status_code == 200, f"Arm failed: {res_arm.status_code}"
    print(f"[PASS] POST /system/arm from LAN: {res_arm.status_code}")

    res_disarm = client.post("/system/disarm")
    assert res_disarm.status_code == 200, f"Disarm failed: {res_disarm.status_code}"
    print(f"[PASS] POST /system/disarm from LAN: {res_disarm.status_code}")

if __name__ == "__main__":
    test_ip_whitelist()
    test_middleware_requests()
    print("ALL LAN SECURITY TESTS PASSED!")
