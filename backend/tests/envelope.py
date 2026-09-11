"""The shared error envelope, named in one place."""


def error_message(response):
    """The envelope's human-readable half, with the rest of it checked."""
    body = response.json()
    assert body["success"] is False, body
    assert body["status"] == response.status_code, body
    assert body["request_id"], body
    return body["message"]
