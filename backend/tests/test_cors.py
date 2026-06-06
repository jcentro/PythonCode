from fastapi.testclient import TestClient

from app.main import app


def test_cors_allows_vite_dev_origin() -> None:
    with TestClient(app) as client:
        response = client.options(
            "/api/trades",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
