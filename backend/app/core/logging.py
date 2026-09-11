"""The application logger, on the shared package's JSON formatter.

`webbpulse.logging` is what installs the root handler now, and this module is
the one name the rest of the backend imports to reach it. What it replaced was
five lines around `aws_lambda_powertools.Logger`, and the reason for the swap is
narrower than "the package has a logger too".

## Why Powertools had to go rather than merely could

Powertools' correlation is `@logger.inject_lambda_context`, a decorator on a
Lambda handler. There is no handler here. The four domain functions run behind
the Lambda Web Adapter, which starts ahead of the process and turns each invoke
into an ordinary HTTP request against `127.0.0.1:$AWS_LWA_PORT`, so nothing is
decorated and the decorator never runs. Every log line this backend emitted
therefore carried a `function_request_id` of `None` and no correlation id at
all, which is the state the Web Adapter migration left behind rather than
anything anyone chose.

`webbpulse.log_context` is the replacement for exactly that. `RequestIdMiddleware`,
which `create_app` already mounts, binds a ContextVar per request, and
`JsonFormatter` merges it into every record, so `request_id` reaches a log line
emitted three layers down without the `Request` object being threaded there.
The authentication dependency adds `user_id` the same way once it has resolved a
principal.

## The field names are CarModPicker's

Both products now emit `timestamp`, `level`, `message`, `logger`, `service`,
`environment`, `request_id`, `user_id`, and `trace_id` / `span_id` when a span
is recording, because both get them from the same formatter. That is the point
of the shared package rather than a coincidence: one saved CloudWatch Logs
Insights query reads both log groups, and the `{ $.level = "ERROR" }` metric
filter behind the `api-alarms` module matches the same key in each.

## `extra=` rather than keyword arguments

Powertools' `Logger` accepts arbitrary keywords and folds them into the JSON;
`logging.Logger` does not, and passing one raises. Every call site that used the
keyword form now passes `extra={...}`, which `JsonFormatter` lifts to top-level
keys, so the emitted object is the same shape it was.
"""

from __future__ import annotations

import logging

from webbpulse.logging import configure_logging, get_logger

__all__ = ["configure_logging", "get_logger", "logger"]

#: The shared application logger. A plain `logging.Logger`, so `extra={...}` is
#: how a call site adds fields; see the module docstring.
logger: logging.Logger = get_logger("app")
