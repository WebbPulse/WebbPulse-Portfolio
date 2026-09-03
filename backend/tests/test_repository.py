from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.db import entities, ordering
from app.db.repository import Repository, UniqueViolation
from app.db.serializer import (
    encode_datetime,
    from_item,
    parse_date,
    parse_datetime,
    to_item,
)


class TestSerializer:
    @pytest.mark.unit
    def test_to_item_drops_none_and_encodes_temporal_values(self):
        item = to_item(
            {
                "a": None,
                "when": datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
                "day": date(2024, 1, 2),
                "ratio": 1.5,
                "nested": {"x": None, "y": [1, 2.5]},
            }
        )
        assert "a" not in item
        assert item["when"] == "2024-01-02T03:04:05.000000+00:00"
        assert item["day"] == "2024-01-02"
        assert item["ratio"] == Decimal("1.5")
        assert item["nested"] == {"x": None, "y": [1, Decimal("2.5")]}

    @pytest.mark.unit
    def test_naive_datetimes_are_treated_as_utc(self):
        assert (
            encode_datetime(datetime(2024, 1, 2)) == "2024-01-02T00:00:00.000000+00:00"
        )

    @pytest.mark.unit
    def test_from_item_decodes_decimals(self):
        item = from_item(
            {"id": Decimal("3"), "ratio": Decimal("1.5"), "xs": [Decimal("2")]}
        )
        assert item == {"id": 3, "ratio": 1.5, "xs": [2]}
        assert isinstance(item["id"], int)

    @pytest.mark.unit
    def test_parse_helpers(self):
        assert parse_datetime("2024-01-02T03:04:05.000000+00:00") == datetime(
            2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc
        )
        assert parse_datetime(None) is None
        assert parse_date("2024-01-02") == date(2024, 1, 2)
        assert parse_date(None) is None


class TestRepository:
    @pytest.mark.unit
    def test_ids_come_from_an_atomic_counter(self):
        first = entities.skills.create({"name": "A", "category": "frontend"})
        second = entities.skills.create({"name": "B", "category": "frontend"})
        assert (first["id"], second["id"]) == (1, 2)
        assert entities.skills.current_counter() == 2

    @pytest.mark.unit
    def test_raise_counter_to_never_lowers(self):
        entities.skills.raise_counter_to(10)
        entities.skills.raise_counter_to(5)
        assert entities.skills.current_counter() == 10
        assert entities.skills.create({"name": "A", "category": "frontend"})["id"] == 11

    @pytest.mark.unit
    def test_defaults_are_applied(self):
        skill = entities.skills.create({"name": "A", "category": "frontend"})
        assert skill["tier"] == "working"
        assert skill["order"] == 0
        assert skill["is_active"] is True
        project = entities.projects.create({"title": "P", "description": "D"})
        assert project["technologies"] == []
        assert project["featured"] is False
        assert project["display_order"] == 0

    @pytest.mark.unit
    def test_unique_fields_reject_duplicates(self):
        entities.categories.create({"name": "One", "slug": "one"})
        with pytest.raises(UniqueViolation) as excinfo:
            entities.categories.create({"name": "Two", "slug": "one"})
        assert excinfo.value.field == "slug"
        assert entities.categories.count() == 1
        assert entities.categories.current_counter() == 2

    @pytest.mark.unit
    def test_find_by_unique(self):
        created = entities.categories.create({"name": "One", "slug": "one"})
        assert entities.categories.find_by_unique("slug", "one")["id"] == created["id"]
        assert entities.categories.find_by_unique("slug", "missing") is None
        assert entities.categories.find_by_unique("slug", None) is None

    @pytest.mark.unit
    def test_update_swaps_unique_lookup(self):
        created = entities.categories.create({"name": "One", "slug": "one"})
        entities.categories.create({"name": "Two", "slug": "two"})
        updated = entities.categories.update(created["id"], {"slug": "uno"})
        assert updated["slug"] == "uno"
        assert updated["updated_at"] is not None
        assert entities.categories.find_by_unique("slug", "one") is None
        assert entities.categories.find_by_unique("slug", "uno")["id"] == created["id"]
        with pytest.raises(UniqueViolation):
            entities.categories.update(created["id"], {"slug": "two"})
        assert entities.categories.get(created["id"])["slug"] == "uno"

    @pytest.mark.unit
    def test_update_with_no_changes_keeps_updated_at_unset(self):
        created = entities.categories.create({"name": "One", "slug": "one"})
        same = entities.categories.update(created["id"], {"name": "One"})
        assert same.get("updated_at") is None
        assert entities.categories.update(999, {"name": "x"}) is None

    @pytest.mark.unit
    def test_update_with_none_removes_attribute(self):
        created = entities.categories.create(
            {"name": "One", "slug": "one", "description": "desc"}
        )
        updated = entities.categories.update(created["id"], {"description": None})
        assert "description" not in updated
        raw = entities.categories.table.get_item(Key={"id": created["id"]})["Item"]
        assert "description" not in raw

    @pytest.mark.unit
    def test_soft_delete_hides_from_reads(self):
        skill = entities.skills.create({"name": "A", "category": "frontend"})
        assert entities.skills.soft_delete(skill["id"]) is True
        assert entities.skills.get(skill["id"]) is None
        assert (
            entities.skills.get(skill["id"], include_inactive=True)["is_active"]
            is False
        )
        assert entities.skills.list_all() == []
        assert len(entities.skills.list_all(include_inactive=True)) == 1
        assert entities.skills.get_many([skill["id"]]) == {}
        assert entities.skills.soft_delete(999) is False

    @pytest.mark.unit
    def test_hard_delete_removes_unique_lookups(self):
        created = entities.categories.create({"name": "One", "slug": "one"})
        assert entities.categories.hard_delete(created["id"]) is True
        assert entities.categories.get(created["id"]) is None
        assert entities.categories.find_by_unique("slug", "one") is None
        assert entities.categories.hard_delete(created["id"]) is False
        entities.categories.create({"name": "Again", "slug": "one"})

    @pytest.mark.unit
    def test_get_many_batches(self):
        ids = [
            entities.skills.create({"name": str(i), "category": "x"})["id"]
            for i in range(120)
        ]
        found = entities.skills.get_many(ids + [None, 9999])
        assert sorted(found) == ids

    @pytest.mark.unit
    def test_create_with_explicit_id_and_conflict(self):
        entities.site_content.create({"hero_title": "a"}, item_id=1)
        with pytest.raises(Exception):
            entities.site_content.create({"hero_title": "b"}, item_id=1)
        assert entities.site_content.get(1)["hero_title"] == "a"

    @pytest.mark.unit
    def test_import_item_is_idempotent_and_preserves_ids(self):
        repository = Repository("categories", unique_fields=("slug",))
        repository.import_item({"id": 42, "name": "Imported", "slug": "imported"})
        repository.import_item({"id": 42, "name": "Imported again", "slug": "imported"})
        assert repository.count() == 1
        assert repository.find_by_unique("slug", "imported")["name"] == "Imported again"


class TestPostRepository:
    def _post(self, slug, published_at=None, category_id=None):
        return entities.posts.create(
            {
                "title": slug,
                "slug": slug,
                "content": "c",
                "published_at": published_at,
                "category_id": category_id,
            }
        )

    @pytest.mark.unit
    def test_published_flag_is_derived(self):
        draft = self._post("draft")
        raw = entities.posts.table.get_item(Key={"id": draft["id"]})["Item"]
        assert "published_flag" not in raw
        entities.posts.update(draft["id"], {"published_at": datetime.now(timezone.utc)})
        raw = entities.posts.table.get_item(Key={"id": draft["id"]})["Item"]
        assert raw["published_flag"] == "1"
        entities.posts.update(draft["id"], {"published_at": None})
        raw = entities.posts.table.get_item(Key={"id": draft["id"]})["Item"]
        assert "published_flag" not in raw and "published_at" not in raw

    @pytest.mark.unit
    def test_list_published_orders_newest_first_and_filters_category(self):
        self._post("draft", None, 1)
        self._post("old", datetime(2020, 1, 1, tzinfo=timezone.utc), 1)
        self._post("new", datetime(2024, 1, 1, tzinfo=timezone.utc), 2)
        self._post("mid", datetime(2022, 1, 1, tzinfo=timezone.utc), 1)
        assert [p["slug"] for p in entities.posts.list_published()] == [
            "new",
            "mid",
            "old",
        ]
        assert [p["slug"] for p in entities.posts.list_published(1)] == ["mid", "old"]
        assert entities.posts.list_published(3) == []

    @pytest.mark.unit
    def test_has_posts_in_category(self):
        assert entities.posts.has_posts_in_category(1) is False
        self._post("draft", None, 1)
        assert entities.posts.has_posts_in_category(1) is True
        assert entities.posts.has_posts_in_category(2) is False


class TestOrdering:
    @pytest.mark.unit
    def test_order_by_handles_mixed_directions_and_missing_values(self):
        items = [
            {"id": 1, "order": 2, "name": "b"},
            {"id": 2, "order": 1, "name": "z"},
            {"id": 3, "order": 1, "name": "a"},
            {"id": 4, "name": "m"},
        ]
        assert [i["id"] for i in ordering.skills(items)] == [3, 2, 1, 4]

    @pytest.mark.unit
    def test_project_sort_modes(self):
        items = [
            {
                "id": 1,
                "title": "B",
                "featured": False,
                "display_order": 1,
                "created_at": "2024-01-01",
            },
            {
                "id": 2,
                "title": "A",
                "featured": True,
                "display_order": 2,
                "created_at": "2023-01-01",
            },
            {
                "id": 3,
                "title": "C",
                "featured": False,
                "display_order": 0,
                "created_at": "2022-01-01",
            },
        ]
        assert [i["id"] for i in ordering.projects(items)] == [2, 3, 1]
        assert [i["id"] for i in ordering.projects(items, "newest")] == [2, 1, 3]
        assert [i["id"] for i in ordering.projects(items, "oldest")] == [2, 3, 1]
        assert [i["id"] for i in ordering.projects(items, "title_asc")] == [2, 1, 3]
        assert [i["id"] for i in ordering.projects(items, "unknown")] == [2, 3, 1]

    @pytest.mark.unit
    def test_date_orderings(self):
        items = [
            {
                "id": 1,
                "start_date": "2020-01-01",
                "order": 0,
                "issued_date": "2020-01-01",
            },
            {
                "id": 2,
                "start_date": "2022-01-01",
                "order": 0,
                "issued_date": "2022-01-01",
            },
        ]
        assert [i["id"] for i in ordering.experience(items)] == [2, 1]
        assert [i["id"] for i in ordering.education(items)] == [2, 1]
        assert [i["id"] for i in ordering.certifications(items)] == [2, 1]
