"""The public domain's entrypoint.

The unauthenticated surface: `GET /`, `/health` and the live figures. It reads
no secret at all.
"""

from webbpulse.composition import domain_entrypoint

from app.common.composition.settings import get_settings
from app.common.composition.wiring import DOMAINS, build_domain_app

DOMAIN = DOMAINS["public"]
build_app, main = domain_entrypoint(
    DOMAIN,
    build=build_domain_app,
    settings=get_settings,
)

if __name__ == "__main__":
    main()
