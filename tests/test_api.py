from __future__ import annotations


def test_api_requires_token(client):
    response = client.get("/api/health")
    assert response.status_code == 401
    assert response.get_json()["error"] == "unauthorized"


def test_api_list_actions_returns_only_allowed(client, auth_headers):
    response = client.get("/api/actions", headers=auth_headers)
    assert response.status_code == 200
    data = response.get_json()["data"]["actions"]
    names = {item["name"] for item in data}
    assert "打开记事本" in names
    assert "私有动作" not in names


def test_api_run_action_success_and_failure(client, auth_headers):
    success_response = client.post("/api/run/打开记事本", headers=auth_headers, json={})
    assert success_response.status_code == 200
    assert success_response.get_json()["success"] is True

    failure_response = client.post("/api/run/私有动作", headers=auth_headers, json={})
    assert failure_response.status_code == 400
    assert failure_response.get_json()["success"] is False
    assert failure_response.get_json()["error"] == "action_not_allowed"


def test_api_brightness_validation(client, auth_headers):
    invalid_response = client.post(
        "/api/system/brightness", headers=auth_headers, json={"value": 101}
    )
    assert invalid_response.status_code == 400
    assert invalid_response.get_json()["error"] == "brightness_out_of_range"

    valid_response = client.post("/api/system/brightness", headers=auth_headers, json={"value": 40})
    assert valid_response.status_code == 200
    assert valid_response.get_json()["data"]["value"] == 40


def test_api_logs_limit_and_auth(client, auth_headers):
    unauthorized = client.get("/api/logs")
    assert unauthorized.status_code == 401

    response = client.get("/api/logs", headers=auth_headers)
    assert response.status_code == 200
    logs = response.get_json()["data"]["logs"]
    assert len(logs) == 50
    assert logs[0] == "log line 30"
    assert any("log line 79" in line for line in logs)
