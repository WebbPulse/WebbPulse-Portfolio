"""Cross-domain building blocks: settings, persistence, middleware and composition.

Nothing here imports a domain package, except the lazy per-domain loaders in
`composition.wiring`, which import one domain inside the function body for it.
"""
