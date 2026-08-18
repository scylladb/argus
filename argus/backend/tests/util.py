import json


def client_post(api_client, path: str, payload: dict | None = None):
    return api_client.post(path, json=payload or {})
