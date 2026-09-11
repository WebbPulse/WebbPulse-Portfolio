"""Root B: one module per domain, each the `CMD` of a deployed image.

The import graph is the point: each entrypoint reaches only its own domain,
so an image imports no other domain and cannot serve its routes.
"""
