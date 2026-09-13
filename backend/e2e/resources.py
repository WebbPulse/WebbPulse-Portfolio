"""The kinds of resource a product flow creates, shared by the flows and the cleanup hook.

Kept in its own module so the cleanup hook in `conftest.py` and the tests that append to
`created_resources` name the same thing without either importing the other. `e2e/` is not
a package, so a relative import between its modules is not available.
"""

CREATED_CERTIFICATION = "certification"
CREATED_CATEGORY = "category"
CREATED_POST = "post"
