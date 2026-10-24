def route_paths(app) -> list[str]:
    return list(app.openapi()["paths"])


def test_app_imports(app):
    assert app.title != ""


def test_invalid_double_slashes(app):
    for path in route_paths(app):
        assert "//" not in path


def test_health(app, client):
    paths = [p for p in route_paths(app) if "health" in p]
    assert len(paths) == 1

    response = client.get(paths[0])
    assert response.status_code == 200


def test_ping(client):
    response = client.post("/api/v1/ping", json={"ping": 41})
    assert response.status_code == 200
    assert response.json()["pong"] == 42


def test_ping_invalid_body(client):
    response = client.post("/api/v1/ping", json={"ping": "nan"})
    assert response.status_code != 200
