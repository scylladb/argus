import json
import re


def client_post(api_client, path: str, payload: dict | None = None):
    return api_client.post(path, json=payload or {})


def script_value(page: str, name: str):
    """Decode the literal a page assigns to `const <name>` in its script."""
    match = re.search(rf"const {name} = (.*);", page)
    assert match, f"const {name} not found in the page"
    return json.loads(match.group(1))
