import os
from pathlib import Path
import pytest

@pytest.fixture
def api_key():
    if os.environ.get("MISTRAL_API_KEY"):
        return os.environ["MISTRAL_API_KEY"]
    api_key_path = Path(".mistral-api-key")
    if api_key_path.exists():
        return api_key_path.read_text().strip()
    raise ValueError("No api key found, please fill the MISTRAL_API_KEY "
                     " environment variable or create a .mistral-api-key file")
