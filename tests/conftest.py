from pathlib import Path

import pytest

from api.config import get_settings
from api.graph import Graph
from api.ingest.seed import seed_indexes

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def falkordb_url() -> str:
    url = get_settings().falkordb_url
    if not Graph(url, timeout_s=2).ping():
        pytest.skip(f"FalkorDB not reachable at {url.split('@')[-1]}")
    return url


@pytest.fixture(scope="session")
def graph(falkordb_url) -> Graph:
    return Graph(falkordb_url)


@pytest.fixture(scope="module")
def env_test(graph):
    """mini_graph loaded into env:test (read-only tests share it); dropped after the module."""
    g = graph.env("test")
    g.delete()
    seed_indexes(g)
    g.load_cypher(FIXTURES / "mini_graph.cypher")
    yield g
    g.delete()


@pytest.fixture
def blank(graph, request):
    """An empty throwaway graph for write tests, deleted afterwards."""
    g = graph.scratch(f"test-{request.node.name}")
    g.delete()
    yield g
    g.delete()
