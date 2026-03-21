import pytest
import json
from fastapi import FastAPI
from fastapi.testclient import TestClient

app = FastAPI()

# Sample authentication endpoints for testing
def fake_authentication(username: str, password: str):
    if username == "testuser" and password == "testpass":
        return {"access_token": "fake_access_token", "token_type": "bearer"}
    raise ValueError("Invalid credentials")

@app.post("/auth/login/")
def login(username: str, password: str):
    return fake_authentication(username, password)

@pytest.fixture()
def client():
    yield TestClient(app)

@pytest.mark.parametrize("username,password,expected_status", [
    ("testuser", "testpass", 200),
    ("testuser", "wrongpass", 422),
    ("wronguser", "testpass", 422)
])
def test_login(client, username, password, expected_status):
    response = client.post("/auth/login/", json={"username": username, "password": password})
    assert response.status_code == expected_status
    if expected_status == 200:
        assert "access_token" in response.json()
    else:
        assert "detail" in response.json()
        
# If you'd like to run this function as a script to test it directly, uncomment the following line:
# if __name__ == '__main__':
#     pytest.main()
