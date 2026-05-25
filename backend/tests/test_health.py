"""
tests/test_health.py — Health Check Tests
"""
from fastapi.testclient import TestClient


def test_health_check(test_client: TestClient):
    response = test_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data
    assert "mode" in data
