def _key(field):
    def key(item):
        value = item.get(field)
        return (value is None, value)

    return key


def order_by(items, *specs):
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
    secondary = PROJECT_SORT_MODES.get(sort_mode, PROJECT_SORT_MODES["manual"])
    return order_by(items, ("featured", "desc"), *secondary)


def skills(items):
    return order_by(items, ("order", "asc"), ("name", "asc"))


def experience(items):
    return order_by(items, ("start_date", "desc"))


def education(items):
    return order_by(items, ("order", "asc"), ("start_date", "desc"))


def certifications(items):
    return order_by(items, ("order", "asc"), ("issued_date", "desc"))


def categories(items):
    return order_by(items, ("name", "asc"))


def admin_posts(items):
    return order_by(items, ("created_at", "desc"))


def published_posts(items):
    return order_by(items, ("published_at", "desc"))
