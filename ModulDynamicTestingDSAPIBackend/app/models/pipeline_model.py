from pydantic import BaseModel
from typing import List, Dict, Any, Optional

class TestStats(BaseModel):
    total_tests: int
    passed: int
    failed: int
    success_rate: float

class FullTestResult(BaseModel):
    session_id: str
    timestamp: str
    mode: str
    stats: TestStats
    results: Dict[str, Dict[str, List[Dict[str, Any]]]]