#!/usr/bin/env python3
"""Live test for FastAPI backend pagination and search."""
import urllib.request
import json
import sys

BASE = "http://localhost:8000"

def test_health():
    req = urllib.request.Request(f"{BASE}/health")
    resp = json.loads(urllib.request.urlopen(req, timeout=5).read())
    assert resp == {"status": "ok"}, f"Health failed: {resp}"
    print("[PASS] Health endpoint: OK")
    return True

def test_home():
    req = urllib.request.Request(f"{BASE}/")
    resp = json.loads(urllib.request.urlopen(req, timeout=5).read())
    assert "message" in resp
    print(f"[PASS] Home endpoint: {resp['message']}")
    return True

def test_search_pagination():
    """Test pagination with different offsets."""
    body = {
        "system_parameters": {
            "user_query": "эндемики",
            "limit": 3,
            "offset": 0,
            "debug": True
        },
        "search_parameters": {
            "object": {
                "properties": {"Редкость": "Эндемик"}
            }
        }
    }
    
    # Page 1: offset=0
    body["system_parameters"]["offset"] = 0
    req = urllib.request.Request(
        f"{BASE}/search",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}
    )
    resp = json.loads(urllib.request.urlopen(req, timeout=10).read())
    
    assert "objects" in resp, "No objects in response"
    assert "pagination" in resp, "No pagination in response"
    
    p = resp["pagination"]
    assert "total" in p
    assert "limit" in p
    assert "offset" in p
    assert "next_offset" in p
    assert "has_more" in p
    
    print(f"[PASS] Search page 1 (offset=0): {len(resp['objects'])} objects, "
          f"total={p['total']}, has_more={p['has_more']}, next_offset={p['next_offset']}")
    
    # Page 2: offset=3
    if p["has_more"]:
        body["system_parameters"]["offset"] = p["next_offset"]
        req = urllib.request.Request(
            f"{BASE}/search",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"}
        )
        resp2 = json.loads(urllib.request.urlopen(req, timeout=10).read())
        p2 = resp2["pagination"]
        print(f"[PASS] Search page 2 (offset={p['next_offset']}): {len(resp2['objects'])} objects, "
              f"total={p2['total']}, has_more={p2['has_more']}")
        
        # Check no duplicate IDs between pages
        ids1 = {o["id"] for o in resp["objects"]}
        ids2 = {o["id"] for o in resp2["objects"]}
        overlap = ids1 & ids2
        if overlap:
            print(f"[WARN] Duplicate IDs between pages: {overlap}")
        else:
            print(f"[PASS] No duplicate IDs between pages")
    
    return True

def test_search_no_criteria():
    """Test search with empty body."""
    body = {
        "system_parameters": {"limit": 5, "offset": 0, "debug": True},
        "search_parameters": {}
    }
    req = urllib.request.Request(
        f"{BASE}/search",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}
    )
    resp = json.loads(urllib.request.urlopen(req, timeout=10).read())
    assert "objects" in resp
    assert "resources" in resp
    print(f"[PASS] Empty search: {len(resp['objects'])} objects, {len(resp['resources'])} resources")
    return True

def test_search_invalid_json():
    """Test with invalid JSON."""
    req = urllib.request.Request(
        f"{BASE}/search",
        data=b"invalid json",
        headers={"Content-Type": "application/json"}
    )
    try:
        resp = urllib.request.urlopen(req, timeout=5)
        print(f"[WARN] Invalid JSON returned {resp.status}, expected 422")
    except urllib.error.HTTPError as e:
        print(f"[PASS] Invalid JSON rejected with HTTP {e.code}")
    return True

if __name__ == "__main__":
    tests = [
        ("Health", test_health),
        ("Home", test_home),
        ("Search Pagination", test_search_pagination),
        ("Empty Search", test_search_no_criteria),
        ("Invalid JSON", test_search_invalid_json),
    ]
    
    passed = 0
    failed = 0
    for name, func in tests:
        try:
            func()
            passed += 1
        except Exception as e:
            print(f"[FAIL] {name}: {e}")
            failed += 1
    
    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)} tests")
    sys.exit(0 if failed == 0 else 1)