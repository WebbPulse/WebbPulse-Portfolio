"""What the two composition roots share.

`settings` is the Portfolio subclass of the shared package's
`BaseServiceSettings`, and it is the reason this package exists: it does not
require a secret to be readable at import, so a domain application can be
imported with no AWS credentials and no environment beyond the class defaults.

`wiring` names the four domains and the routers each one owns. `app` is root A,
the mounted whole-surface application that local development and the test suite
run against; `app.entrypoints.<domain>` is root B, one per deployed function.
"""
