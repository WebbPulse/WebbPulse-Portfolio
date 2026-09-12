"""Reading the routes an application serves, for tests that assert on the surface.

FastAPI 0.116 made `include_router` lazy: instead of copying each child route into
the parent, it appends one placeholder per included router and resolves the real
routes when a request arrives or the schema is generated. So `app.routes` is no
longer the list of served routes, and a test that iterates it sees placeholders
carrying no `path` and no `methods`.

`served_routes` flattens that through `fastapi.routing.iter_route_contexts`, which
yields one object per served route with the `path`, `methods`, `name`, `tags` and
`dependant` the placeholders hide. Those objects are `RouteContext` rather than
`starlette.routing.Route`, so a caller filters on the attributes it needs rather
than on the type.
"""

from fastapi.routing import iter_route_contexts

DOCUMENTATION_PATHS = frozenset({"/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json"})
"""The paths FastAPI declares for its own documentation."""


def served_routes(app):
    """Every route the application serves, with included routers resolved."""
    return list(iter_route_contexts(app.routes))


def method_path_pairs(app, *, skip_documentation=True, skip_methods=("HEAD", "OPTIONS")):
    """`(method, path)` for every route, one entry per method."""
    pairs = set()
    for route in served_routes(app):
        path = getattr(route, "path", None)
        if path is None:
            continue
        if skip_documentation and path in DOCUMENTATION_PATHS:
            continue
        for method in getattr(route, "methods", None) or ():
            if method in skip_methods:
                continue
            pairs.add((method, path))
    return pairs


def paths_for_method(app, method):
    """Every path the application serves for one method."""
    return {
        path
        for served_method, path in method_path_pairs(app, skip_documentation=False, skip_methods=())
        if served_method == method
    }


def all_paths(app):
    """Every path the application serves, whatever the method."""
    return {path for path in (getattr(route, "path", None) for route in served_routes(app)) if path is not None}
