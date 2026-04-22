import json


def client_post(flask_client, path: str, payload: dict | None = None):
    return flask_client.post(path, data=json.dumps(payload or {}), content_type="application/json")
