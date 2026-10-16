from pathlib import Path

import pytest

from api.config import get_settings
from api.graph import Graph
from api.ingest.seed import seed_indexes, seed_rules

FIXTURES = Path(__file__).parent / "fixtures"

pytest_plugins = ["tests.report"]  # findings.md + agent-context.md per run (phase 12)


def pytest_configure(config):
    config.addinivalue_line("markers", "live: calls the real OpenRouter (GPT-4o + Jev); needs OPENROUTER_API_KEY")


@pytest.fixture(autouse=True)
def offline_llm(request, monkeypatch):
    """Tests never spend money by accident: no OpenRouter key unless the test is marked `live`."""
    if "live" not in request.keywords:
        monkeypatch.setattr(get_settings(), "openrouter_api_key", None)


@pytest.fixture(scope="session")
def falkordb_url() -> str:
    url = get_settings().falkordb_url
    if not Graph(url, timeout_s=2).ping():
        pytest.skip(f"FalkorDB not reachable at {url.split('@')[-1]}")
    return url


@pytest.fixture(scope="session")
def graph(falkordb_url) -> Graph:
    g = Graph(falkordb_url)
    seed_rules(g.kb())  # diagnosis reads the propagation rules from kb; a fresh FalkorDB (CI) has none yet
    return g


@pytest.fixture(scope="module")
def env_test(graph):
    """mini_graph loaded into env:test (read-only tests share it); dropped after the module."""
    g = graph.env("test")
    g.delete()
    seed_indexes(g)
    g.load_cypher(FIXTURES / "mini_graph.cypher")
    yield g
    g.delete()


API_ENV = "test-api"


@pytest.fixture
def client(graph, tmp_path, monkeypatch):
    """The FastAPI app over mini_graph in env:test-api, with a throwaway checkpoint DB."""
    from fastapi.testclient import TestClient

    from api.main import app

    monkeypatch.setattr(get_settings(), "checkpoint_db", str(tmp_path / "cp.db"))
    g = graph.env(API_ENV)
    g.delete()
    seed_indexes(g)
    g.load_cypher(FIXTURES / "mini_graph.cypher")
    with TestClient(app) as c:
        c.g = g
        yield c
    g.delete()


def diagnosed(client, incident: str = "inc-1") -> dict:
    r = client.post(f"/api/v1/incidents/{incident}/diagnose", params={"env": API_ENV})  # runs in the background task
    assert r.status_code == 202, r.text
    return client.get(f"/api/v1/incidents/{incident}", params={"env": API_ENV}).json()


@pytest.fixture
def blank(graph, request):
    """An empty throwaway graph for write tests, deleted afterwards."""
    g = graph.scratch(f"test-{request.node.name}")
    g.delete()
    yield g
    g.delete()
