"""Real HTTP OIDC protocol fixture. No external provider or production secrets are used."""

import base64
import hashlib
import json
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest
from authlib.integrations.starlette_client import OAuth
from fastapi.testclient import TestClient
from joserfc import jwt
from joserfc.jwk import RSAKey

from neuralops import api
from neuralops.config import settings
from neuralops.db import SessionLocal
from neuralops.models import Membership


@pytest.fixture
def provider(monkeypatch, identity):
    _, _, _, member_id = identity()
    with SessionLocal() as db:
        subject = db.get(Membership, member_id).subject
    key = RSAKey.generate_key(2048, parameters={"kid": "fixture-key"})
    other = RSAKey.generate_key(2048, parameters={"kid": "fixture-key"})
    state = {"mode": "valid", "pkce_verified": False, "subject": subject}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def respond(self, value, status=200):
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(value).encode())

        def do_GET(self):
            if self.path == "/.well-known/openid-configuration":
                self.respond(
                    {
                        "issuer": issuer,
                        "authorization_endpoint": issuer + "/authorize",
                        "token_endpoint": issuer + "/token",
                        "jwks_uri": issuer + "/jwks",
                        "response_types_supported": ["code"],
                        "subject_types_supported": ["public"],
                        "id_token_signing_alg_values_supported": ["RS256"],
                        "code_challenge_methods_supported": ["S256"],
                    }
                )
            elif self.path == "/jwks":
                self.respond({"keys": [key.as_dict()]})
            else:
                self.respond({"error": "not_found"}, 404)

        def do_POST(self):
            body = parse_qs(self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode())
            verifier = body.get("code_verifier", [""])[0]
            actual_challenge = (
                base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
            )
            state["pkce_verified"] = bool(verifier) and secrets.compare_digest(
                actual_challenge, state["challenge"]
            )
            if not state["pkce_verified"]:
                return self.respond({"error": "invalid_grant"}, 400)
            claims = {
                "iss": issuer,
                "sub": state["subject"],
                "aud": "neuralops-fixture-client",
                "iat": int(time.time()),
                "exp": int(time.time()) + 300,
                "nonce": state["nonce"],
                "name": "OIDC fixture",
            }
            if state["mode"] == "audience":
                claims["aud"] = "another-client"
            if state["mode"] == "nonce":
                claims["nonce"] = "incorrect-nonce"
            if state["mode"] == "expired":
                claims["iat"], claims["exp"] = int(time.time()) - 900, int(time.time()) - 600
            if state["mode"] == "issuer":
                claims["iss"] = "https://untrusted.example"
            token = jwt.encode(
                {"alg": "RS256", "kid": "fixture-key"}, claims, other if state["mode"] == "signature" else key
            )
            self.respond(
                {
                    "access_token": secrets.token_urlsafe(24),
                    "token_type": "Bearer",
                    "expires_in": 300,
                    "id_token": token,
                }
            )

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    issuer = f"http://127.0.0.1:{server.server_port}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(settings(), "oidc_issuer", issuer)
    client = OAuth()
    client.register(
        "identity",
        client_id="neuralops-fixture-client",
        client_secret=secrets.token_urlsafe(32),
        server_metadata_url=issuer + "/.well-known/openid-configuration",
        client_kwargs={"scope": "openid profile", "code_challenge_method": "S256"},
    )
    monkeypatch.setattr(api, "oauth", client)
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize("mode", ["valid", "audience", "nonce", "expired", "issuer", "signature", "state"])
def test_authorization_code_pkce_and_id_token_validation(provider, mode):
    provider["mode"] = mode
    client = TestClient(api.app)
    login = client.get("/v1/auth/login", follow_redirects=False)
    assert login.status_code == 302, login.text
    params = parse_qs(urlparse(login.headers["location"]).query)
    assert params["response_type"] == ["code"] and params["code_challenge_method"] == ["S256"]
    provider["challenge"], provider["nonce"] = params["code_challenge"][0], params["nonce"][0]
    state = "incorrect-state" if mode == "state" else params["state"][0]
    callback = client.get(
        "/v1/auth/callback",
        params={"state": state, "code": "fixture-authorization-code"},
        follow_redirects=False,
    )
    if mode == "valid":
        assert callback.status_code == 303, callback.text
        assert provider["pkce_verified"]
        assert client.get("/v1/me").status_code == 200
        assert client.cookies.get("neuralops_session")
        # Callback cannot be replayed after state has been consumed.
        assert (
            client.get(
                "/v1/auth/callback", params={"state": state, "code": "fixture-authorization-code"}
            ).status_code
            == 401
        )
    else:
        assert callback.status_code == 401, callback.text
        assert not client.cookies.get("neuralops_session")
