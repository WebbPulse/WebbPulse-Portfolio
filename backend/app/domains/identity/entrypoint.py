"""The identity domain's entrypoint.

The login route on its own function, so the signing key is reachable from
exactly one place.
"""

from webbpulse.composition import domain_entrypoint

from app.common.composition.settings import get_settings
from app.common.composition.wiring import DOMAINS, build_domain_app, check_domain_secrets

DOMAIN = DOMAINS["identity"]
build_app, main = domain_entrypoint(
    DOMAIN,
    build=build_domain_app,
    settings=get_settings,
    check=check_domain_secrets,
)

if __name__ == "__main__":
    main()
