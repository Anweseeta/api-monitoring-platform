"""Auth tests: register, login, invalid credentials, unauthorized access."""
from tests.conftest import auth_headers, register_user


async def test_register_returns_envelope_with_token(client):
    r = await client.post("/api/auth/register", json={
        "name": "Alice", "email": "alice@example.com", "password": "Password123!",
    })
    assert r.status_code == 201
    body = r.json()
    assert body["success"] is True
    data = body["data"]
    assert data["token_type"] == "bearer"
    assert data["access_token"]
    user = data["user"]
    assert user["email"] == "alice@example.com"
    assert user["name"] == "Alice"
    assert "id" in user and len(user["id"]) == 24
    assert "password" not in user and "password_hash" not in user


async def test_register_duplicate_email(client):
    await register_user(client, email="dup@example.com")
    r = await client.post("/api/auth/register", json={
        "name": "Dup", "email": "dup@example.com", "password": "Password123!",
    })
    assert r.status_code == 409
    body = r.json()
    assert body["success"] is False
    assert body["error_code"] == "USER_EXISTS"


async def test_register_validation_error_envelope(client):
    r = await client.post("/api/auth/register", json={
        "name": "", "email": "not-an-email", "password": "short",
    })
    assert r.status_code == 422
    body = r.json()
    assert body["success"] is False
    assert body["error_code"] == "VALIDATION_ERROR"


async def test_login_success(client):
    await register_user(client, email="login@example.com", password="Password123!")
    r = await client.post("/api/auth/login", json={
        "email": "login@example.com", "password": "Password123!",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"]["token_type"] == "bearer"
    assert body["data"]["access_token"]


async def test_login_invalid_credentials(client):
    await register_user(client, email="bad@example.com", password="Password123!")
    r = await client.post("/api/auth/login", json={
        "email": "bad@example.com", "password": "WrongPassword1!",
    })
    assert r.status_code == 401
    assert r.json()["error_code"] == "INVALID_CREDENTIALS"

    r = await client.post("/api/auth/login", json={
        "email": "nobody@example.com", "password": "Password123!",
    })
    assert r.status_code == 401
    assert r.json()["error_code"] == "INVALID_CREDENTIALS"


async def test_me_requires_auth(client):
    r = await client.get("/api/auth/me")
    assert r.status_code == 401
    assert r.json()["error_code"] == "UNAUTHORIZED"


async def test_me_invalid_token(client):
    r = await client.get("/api/auth/me", headers={"Authorization": "Bearer garbage"})
    assert r.status_code == 401
    assert r.json()["error_code"] == "INVALID_TOKEN"


async def test_me_with_valid_token(client):
    headers = await auth_headers(client, email="me@example.com")
    r = await client.get("/api/auth/me", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"]["user"]["email"] == "me@example.com"


async def test_protected_route_without_token_uses_error_envelope(client):
    r = await client.get("/api/monitors")
    assert r.status_code == 401
    body = r.json()
    assert body == {"success": False, "message": body["message"], "error_code": "UNAUTHORIZED"}
