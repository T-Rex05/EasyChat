"""Fallback management preserves order and serializes slotted model profiles."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.modules.models.routes import build_models_router
from backend.runtime.hermes.agent_factory import _fallback_profile
from backend.runtime.hermes.adapter import HermesRuntimeAdapter
from tests.contracts.test_runtime import _req
from tests.models.test_configs import models


def test_fallback_chain_route_round_trip(models):
    service, _, admin = models
    first = service.create_config(admin, name="first", provider="openai", model="first-model")
    second = service.create_config(admin, name="second", provider="openai", model="second-model")
    app = FastAPI()
    app.include_router(build_models_router(service, lambda _: admin))
    headers = {"Authorization": "Bearer offline-test"}

    with TestClient(app) as client:
        assert client.get("/api/model-routes/fallback-chain", headers=headers).json() == {"chain": []}
        saved = client.put("/api/model-routes/fallback-chain", headers=headers,
                           json={"config_ids": [second, first]})
        assert saved.status_code == 200
        listed = client.get("/api/model-routes/fallback-chain", headers=headers)
        assert listed.status_code == 200
        assert [item["config_id"] for item in listed.json()["chain"]] == [second, first]
        assert listed.json()["chain"][0]["model"] == "second-model"


def test_runtime_receives_configured_fallback_profile(models):
    service, _, admin = models
    main = service.create_config(admin, name="main", provider="openai", model="main-model")
    backup = service.create_config(admin, name="backup", provider="openai", model="backup-model",
                                   base_url="https://example.invalid/v1")
    service.set_active(admin, main)
    assert _fallback_profile(service) is None
    service.save_fallback_chain(admin, [backup])
    assert _fallback_profile(service) == {
        "base_url": "https://example.invalid/v1",
        "model": "backup-model",
        "provider": "openai",
        "profile_id": backup,
    }


def test_session_cache_rebuilds_for_model_and_fallback_changes(models, tmp_path):
    service, _, admin = models
    first = service.create_config(admin, name="first", provider="openai", model="main-model")
    second = service.create_config(admin, name="second", provider="openai", model="backup-model")
    third = service.create_config(admin, name="third", provider="openai", model="third-model")
    service.set_active(admin, first)
    adapter = HermesRuntimeAdapter(hermes_home=tmp_path, models=service,
                                   agent_factory=lambda *_: object())
    request = _req()
    previous = adapter._acquire(request)
    assert adapter._acquire(request) is previous

    for change in (
        lambda: service.update_config(admin, first, model="updated-model"),
        lambda: service.update_config(admin, first, api_key="offline-secret-key"),
        lambda: service.save_fallback_chain(admin, [second, third]),
        lambda: service.update_config(admin, second, reasoning_effort="high"),
        lambda: service.save_fallback_chain(admin, [third, second]),
        lambda: service.save_fallback_chain(admin, []),
        lambda: service.set_active(admin, second),
    ):
        change()
        current = adapter._acquire(request)
        assert current is not previous
        assert adapter._acquire(request) is current
        assert "offline-secret-key" not in repr(current.key)
        previous = current
