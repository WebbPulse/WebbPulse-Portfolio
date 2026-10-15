"""Cross-domain building blocks: settings, persistence, logging and composition.

Nothing here imports a domain package, except the lazy loader in
`composition.wiring`, which imports the domain inside the function body for it.
"""
