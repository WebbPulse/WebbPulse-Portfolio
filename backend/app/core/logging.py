from aws_lambda_powertools import Logger

from ..config import settings

logger = Logger(service=settings.POWERTOOLS_SERVICE_NAME, level=settings.LOG_LEVEL)
