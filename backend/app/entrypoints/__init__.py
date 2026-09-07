"""Root B: one module per domain, each the `CMD` of a deployed image.

Each of the four is the same six lines around a different domain name, and the
shape is deliberately not abstracted away: an entrypoint is the file somebody
reads when a function will not start, and indirection there costs more than the
repetition saves. What they share lives in `app.composition.wiring`.

The import graph is the point. `app.entrypoints.public` reaches only
`app.domains.public`, so the `public` image imports no `content` module, pays no
`content` import at cold start, and cannot accidentally serve a `content` route.
`tests/entrypoints/` asserts exactly that.
"""
