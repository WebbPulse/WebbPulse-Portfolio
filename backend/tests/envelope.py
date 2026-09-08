"""The shared error envelope, named in one place.

`webbpulse.http.create_app` installs handlers that render every error as
`{"success": false, "status": ..., "message": ..., "request_id": ...}`. The
monolith had no such handlers, so its errors were FastAPI's default
`{"detail": ...}`, and the suite asserted on that key.

This is not a change this PR makes to the application. The four deployed
functions have rendered errors this way since the domain cuts, because they
have always been built by `create_app`. The suite kept passing against `detail`
only because its client was still the monolith, so for the length of the
migration these assertions were pinning a shape production had already stopped
returning. Building the client from the composition root is what surfaced it,
which is the argument for building it there rather than keeping a second
composition root alive to check the first one.
"""


def error_message(response):
    """The envelope's human-readable half, with the rest of it checked.

    `message` is what the callers below assert on. `request_id` changes per
    request and `status` duplicates `response.status_code`, so both are checked
    for presence and agreement here instead of at every call site.
    """
    body = response.json()
    assert body["success"] is False, body
    assert body["status"] == response.status_code, body
    assert body["request_id"], body
    return body["message"]
