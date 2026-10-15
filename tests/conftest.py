import pytest

from api.config import get_settings
from api.graph import Graph


@pytest.fixture(scope="session")
def falkordb_url() -> str:
    url = get_settings().falkordb_url
    if not Graph(url, timeout_s=2).ping():
        pytest.skip(f"FalkorDB not reachable at {url.split('@')[-1]}")
    return url
