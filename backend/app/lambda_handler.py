from aws_lambda_powertools.logging import correlation_paths
from mangum import Mangum

from .core.logging import logger
from .main import app

asgi_handler = Mangum(app, lifespan="off", api_gateway_base_path=None)


@logger.inject_lambda_context(
    correlation_id_path=correlation_paths.API_GATEWAY_HTTP, log_event=False
)
def handler(event, context):
    return asgi_handler(event, context)
