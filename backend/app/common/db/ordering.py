"""Sort helpers applied in Python, since the tables have no sort keys.

Every ordering puts rows with a missing value last and breaks ties by id, so a
listing is stable across calls."""


def _key(field):
    """A sort key for `field` that orders missing values last."""

    def key(item):
        """Order one item by `field`, placing a missing value last."""
        value = item.get(field)
        return (value is None, value)

    return key


def order_by(items, *specs):
    """Sort `items` by `(field, direction)` specs, most significant first."""
    ordered = sorted(items, key=_key("id"))
    for field, direction in reversed(specs):
        ordered.sort(key=_key(field), reverse=direction == "desc")
    return ordered


PROJECT_SORT_MODES = {
    "manual": (("display_order", "asc"), ("created_at", "desc")),
    "newest": (("created_at", "desc"),),
    "oldest": (("created_at", "asc"),),
    "title_asc": (("title", "asc"),),
}


def projects(items, sort_mode="manual"):
    """Featured projects first, then the requested secondary sort mode."""
    secondary = PROJECT_SORT_MODES.get(sort_mode, PROJECT_SORT_MODES["manual"])
    return order_by(items, ("featured", "desc"), *secondary)


def skills(items):
    """By explicit order, then name."""
    return order_by(items, ("order", "asc"), ("name", "asc"))


def experience(items):
    """Most recent start date first."""
    return order_by(items, ("start_date", "desc"))


def education(items):
    """By explicit order, then most recent start date."""
    return order_by(items, ("order", "asc"), ("start_date", "desc"))


def certifications(items):
    """By explicit order, then most recent issue date."""
    return order_by(items, ("order", "asc"), ("issued_date", "desc"))


def categories(items):
    """Alphabetically by name."""
    return order_by(items, ("name", "asc"))


def admin_posts(items):
    """Most recently created first, drafts included."""
    return order_by(items, ("created_at", "desc"))


def published_posts(items):
    """Most recently published first."""
    return order_by(items, ("published_at", "desc"))
