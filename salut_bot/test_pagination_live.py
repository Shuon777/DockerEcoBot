#!/usr/bin/env python3
"""Extended pagination tests for FastAPI backend."""
import urllib.request
import json

BASE = "http://localhost:8000"

def test_pagination_edge_cases():
    """Test pagination with various limit/offset combinations."""
    body = {
        "system_parameters": {
            "user_query": "эндемики",
            "limit": 10,
            "offset": 0,
            "debug": True
        },
        "search_parameters": {
            "object": {
                "properties": {"Редкость": "Эндемик"}
            }
        }
    }
    
    # Get total count first
    req = urllib.request.Request(
        f"{BASE}/search",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}
    )
    resp = json.loads(urllib.request.urlopen(req, timeout=10).read())
    total = resp["pagination"]["total"]
    print(f"Total objects with 'Эндемик': {total}")
    
    tests = [
        ("limit=3, offset=0 (first page)", 3, 0, 3, True),
        ("limit=3, offset=3 (second page)", 3, 3, 3, True),
        ("limit=3, offset=6 (third page)", 3, 6, min(3, total-6), total > 9),
        ("limit=100, offset=0 (all at once)", 100, 0, min(100, total), False),
        ("limit=5, offset=999 (beyond total)", 5, 999, 0, False),
        ("limit=0, offset=0 (zero limit)", 0, 0, 0, False),
    ]
    
    for name, limit, offset, expected_count, expected_has_more in tests:
        body["system_parameters"]["limit"] = limit
        body["system_parameters"]["offset"] = offset
        req = urllib.request.Request(
            f"{BASE}/search",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"}
        )
        try:
            resp = json.loads(urllib.request.urlopen(req, timeout=10).read())
            p = resp["pagination"]
            obj_count = len(resp["objects"])
            
            status = "PASS" if (obj_count == expected_count and p["has_more"] == expected_has_more) else "FAIL"
            print(f"[{status}] {name}: got {obj_count} objects (expected {expected_count}), "
                  f"has_more={p['has_more']} (expected {expected_has_more})")
        except Exception as e:
            print(f"[FAIL] {name}: {e}")

def test_pagination_consistency():
    """Verify pagination consistency across pages."""
    body = {
        "system_parameters": {
            "user_query": "эндемики",
            "limit": 2,
            "offset": 0,
            "debug": True
        },
        "search_parameters": {
            "object": {
                "properties": {"Редкость": "Эндемик"}
            }
        }
    }
    
    all_ids = []
    offset = 0
    total = None
    
    while True:
        body["system_parameters"]["offset"] = offset
        req = urllib.request.Request(
            f"{BASE}/search",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"}
        )
        resp = json.loads(urllib.request.urlopen(req, timeout=10).read())
        p = resp["pagination"]
        
        if total is None:
            total = p["total"]
        
        # Consistency checks
        assert p["total"] == total, f"Total changed: {p['total']} != {total}"
        assert p["offset"] == offset, f"Offset mismatch: {p['offset']} != {offset}"
        assert p["next_offset"] == offset + body["system_parameters"]["limit"], \
            f"next_offset mismatch: {p['next_offset']} != {offset + body['system_parameters']['limit']}"
        
        ids = [o["id"] for o in resp["objects"]]
        all_ids.extend(ids)
        
        print(f"  offset={offset}: {len(ids)} objects, ids={ids}, "
              f"has_more={p['has_more']}, next_offset={p['next_offset']}")
        
        if not p["has_more"]:
            break
        offset = p["next_offset"]
    
    # Check no duplicates
    assert len(all_ids) == len(set(all_ids)), f"Duplicate IDs found! {len(all_ids)} != {len(set(all_ids))}"
    print(f"[PASS] All {len(all_ids)} unique IDs collected across pages, total={total}")
    
    # Check last page has_more=False
    assert p["has_more"] == False, f"Last page should have has_more=False"
    print(f"[PASS] Last page correctly has has_more=False")

if __name__ == "__main__":
    print("=" * 60)
    print("PAGINATION EDGE CASES")
    print("=" * 60)
    test_pagination_edge_cases()
    
    print("\n" + "=" * 60)
    print("PAGINATION CONSISTENCY")
    print("=" * 60)
    test_pagination_consistency()
    
    print("\n" + "=" * 60)
    print("ALL TESTS COMPLETED")
    print("=" * 60)