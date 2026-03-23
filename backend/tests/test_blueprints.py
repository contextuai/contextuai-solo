"""
Tests for the Blueprints feature.

Covers:
- Blueprint library service (parsing .md files, catalog, search)
- Blueprint repository (CRUD operations)
- Blueprint API endpoints (router)
"""

import os
import tempfile
import pytest
import pytest_asyncio


# ── Blueprint Library Service — Unit Tests ────────────────────────────

class TestBlueprintLibraryServiceParsing:
    """Unit tests for .md file parsing (no DB needed)."""

    def _write_md(self, tmpdir: str, category: str, slug: str, content: str) -> str:
        """Write a blueprint .md file under tmpdir/category/slug.md."""
        cat_dir = os.path.join(tmpdir, category)
        os.makedirs(cat_dir, exist_ok=True)
        path = os.path.join(cat_dir, f"{slug}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def test_parse_basic_blueprint(self):
        from services.blueprint_library_service import BlueprintLibraryService
        svc = BlueprintLibraryService()

        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write_md(tmpdir, "strategy", "test-blueprint", """# Test Blueprint

A test blueprint for unit testing.

## Objective
Test the parsing logic.

## Steps
1. First step
2. Second step

## Expected Output
- A parsed result

## Recommended Agents
CEO, Product Manager
""")
            result = svc.parse_blueprint_md(path)

            assert result["name"] == "Test Blueprint"
            assert result["slug"] == "test-blueprint"
            assert result["category"] == "strategy"
            assert "test blueprint for unit testing" in result["description"]
            assert "Objective" in result["sections"]
            assert "Steps" in result["sections"]
            assert "Expected Output" in result["sections"]
            assert result["full_content"].startswith("# Test Blueprint")
            assert "CEO" in result["recommended_agents"]
            assert "Product Manager" in result["recommended_agents"]

    def test_parse_blueprint_no_h1_raises(self):
        from services.blueprint_library_service import BlueprintLibraryService
        svc = BlueprintLibraryService()

        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write_md(tmpdir, "general", "bad", "No heading here.")
            with pytest.raises(ValueError, match="No H1"):
                svc.parse_blueprint_md(path)

    def test_parse_blueprint_extracts_tags(self):
        from services.blueprint_library_service import BlueprintLibraryService
        svc = BlueprintLibraryService()

        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write_md(tmpdir, "product", "tagged", """# Tagged Blueprint

A blueprint with tags.

## Tags
brainstorm, planning, product
""")
            result = svc.parse_blueprint_md(path)
            assert "brainstorm" in result["tags"]
            assert "planning" in result["tags"]
            assert "product" in result["tags"]

    def test_parse_blueprint_empty_sections(self):
        from services.blueprint_library_service import BlueprintLibraryService
        svc = BlueprintLibraryService()

        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write_md(tmpdir, "general", "minimal", """# Minimal Blueprint

Just a description, no sections.
""")
            result = svc.parse_blueprint_md(path)
            assert result["name"] == "Minimal Blueprint"
            assert result["description"] == "Just a description, no sections."
            assert result["tags"] == []
            assert result["recommended_agents"] == []

    def test_parse_recommended_agents_bullet_list(self):
        from services.blueprint_library_service import BlueprintLibraryService
        svc = BlueprintLibraryService()

        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write_md(tmpdir, "strategy", "bullets", """# Bullet Agents

Desc.

## Recommended Agents
- CEO
- CTO
- CFO
""")
            result = svc.parse_blueprint_md(path)
            assert "CEO" in result["recommended_agents"]
            assert "CTO" in result["recommended_agents"]
            assert "CFO" in result["recommended_agents"]


# ── Blueprint Library Service — Catalog Tests ─────────────────────────

@pytest.mark.asyncio
class TestBlueprintLibraryCatalog:
    """Tests for catalog browsing and search (reads from disk)."""

    def _setup_library(self, tmpdir: str):
        """Create a small test library."""
        for cat, files in {
            "strategy": [("lean-canvas", "# Lean Canvas\nLean canvas desc.\n## Objective\nObj")],
            "product": [("feature-pri", "# Feature Prioritization\nFeature desc.\n## Steps\n1. Step")],
        }.items():
            cat_dir = os.path.join(tmpdir, cat)
            os.makedirs(cat_dir, exist_ok=True)
            for slug, content in files:
                with open(os.path.join(cat_dir, f"{slug}.md"), "w") as f:
                    f.write(content)

    async def test_get_catalog_all(self):
        from services.blueprint_library_service import BlueprintLibraryService
        svc = BlueprintLibraryService()

        with tempfile.TemporaryDirectory() as tmpdir:
            self._setup_library(tmpdir)
            svc.LIBRARY_PATH = tmpdir

            catalog = await svc.get_catalog()
            assert catalog["total_count"] == 2
            assert "strategy" in catalog["categories"]
            assert "product" in catalog["categories"]
            names = [b["name"] for b in catalog["blueprints"]]
            assert "Lean Canvas" in names
            assert "Feature Prioritization" in names

    async def test_get_catalog_filtered(self):
        from services.blueprint_library_service import BlueprintLibraryService
        svc = BlueprintLibraryService()

        with tempfile.TemporaryDirectory() as tmpdir:
            self._setup_library(tmpdir)
            svc.LIBRARY_PATH = tmpdir

            catalog = await svc.get_catalog(category="strategy")
            assert catalog["total_count"] == 1
            assert catalog["blueprints"][0]["category"] == "strategy"

    async def test_search_catalog(self):
        from services.blueprint_library_service import BlueprintLibraryService
        svc = BlueprintLibraryService()

        with tempfile.TemporaryDirectory() as tmpdir:
            self._setup_library(tmpdir)
            svc.LIBRARY_PATH = tmpdir

            result = await svc.search_catalog("lean")
            assert result["total_count"] == 1
            assert result["blueprints"][0]["name"] == "Lean Canvas"

    async def test_search_catalog_no_results(self):
        from services.blueprint_library_service import BlueprintLibraryService
        svc = BlueprintLibraryService()

        with tempfile.TemporaryDirectory() as tmpdir:
            self._setup_library(tmpdir)
            svc.LIBRARY_PATH = tmpdir

            result = await svc.search_catalog("nonexistent")
            assert result["total_count"] == 0

    async def test_get_detail(self):
        from services.blueprint_library_service import BlueprintLibraryService
        svc = BlueprintLibraryService()

        with tempfile.TemporaryDirectory() as tmpdir:
            self._setup_library(tmpdir)
            svc.LIBRARY_PATH = tmpdir

            detail = await svc.get_detail("strategy", "lean-canvas")
            assert detail is not None
            assert detail["name"] == "Lean Canvas"
            assert "full_content" in detail

    async def test_get_detail_not_found(self):
        from services.blueprint_library_service import BlueprintLibraryService
        svc = BlueprintLibraryService()

        with tempfile.TemporaryDirectory() as tmpdir:
            svc.LIBRARY_PATH = tmpdir
            detail = await svc.get_detail("strategy", "nonexistent")
            assert detail is None

    async def test_catalog_empty_library(self):
        from services.blueprint_library_service import BlueprintLibraryService
        svc = BlueprintLibraryService()

        with tempfile.TemporaryDirectory() as tmpdir:
            svc.LIBRARY_PATH = tmpdir
            catalog = await svc.get_catalog()
            assert catalog["total_count"] == 0
            assert catalog["blueprints"] == []

    async def test_catalog_missing_directory(self):
        from services.blueprint_library_service import BlueprintLibraryService
        svc = BlueprintLibraryService()
        svc.LIBRARY_PATH = "/nonexistent/path"

        catalog = await svc.get_catalog()
        assert catalog["total_count"] == 0


# ── Blueprint Repository Tests ────────────────────────────────────────

@pytest.mark.asyncio
class TestBlueprintRepository:
    """Test Blueprint CRUD operations via the repository."""

    async def test_create_and_get(self, db_proxy):
        from repositories.blueprint_repository import BlueprintRepository
        repo = BlueprintRepository(db_proxy)

        bp = await repo.create_blueprint("test-user", {
            "name": "Test Blueprint",
            "description": "A test",
            "category": "strategy",
            "content": "# Test\nContent here.",
            "tags": ["test", "strategy"],
        })

        assert bp["name"] == "Test Blueprint"
        assert bp["blueprint_id"] is not None
        assert bp["source"] == "custom"
        assert bp["is_system"] is False

        fetched = await repo.get_by_blueprint_id(bp["blueprint_id"])
        assert fetched is not None
        assert fetched["name"] == "Test Blueprint"
        assert fetched["category"] == "strategy"

    async def test_list_blueprints(self, db_proxy):
        from repositories.blueprint_repository import BlueprintRepository
        repo = BlueprintRepository(db_proxy)

        await repo.create_blueprint("test-user", {
            "name": "Blueprint A",
            "category": "product",
            "content": "# A\nContent A",
        })
        await repo.create_blueprint("test-user", {
            "name": "Blueprint B",
            "category": "strategy",
            "content": "# B\nContent B",
        })

        docs, total = await repo.get_user_blueprints()
        assert total >= 2
        names = [d["name"] for d in docs]
        assert "Blueprint A" in names
        assert "Blueprint B" in names

    async def test_filter_by_category(self, db_proxy):
        from repositories.blueprint_repository import BlueprintRepository
        repo = BlueprintRepository(db_proxy)

        await repo.create_blueprint("test-user", {
            "name": "Strategy BP",
            "category": "strategy",
            "content": "# S\nContent",
        })
        await repo.create_blueprint("test-user", {
            "name": "Marketing BP",
            "category": "marketing",
            "content": "# M\nContent",
        })

        docs, total = await repo.get_user_blueprints(category="marketing")
        assert total >= 1
        assert all(d["category"] == "marketing" for d in docs)

    async def test_search(self, db_proxy):
        from repositories.blueprint_repository import BlueprintRepository
        repo = BlueprintRepository(db_proxy)

        await repo.create_blueprint("test-user", {
            "name": "SWOT Analysis Guide",
            "category": "strategy",
            "content": "# SWOT\nContent",
            "tags": ["swot", "analysis"],
        })

        docs, total = await repo.get_user_blueprints(search="SWOT")
        assert total >= 1
        assert any("SWOT" in d["name"] for d in docs)

    async def test_update_blueprint(self, db_proxy):
        from repositories.blueprint_repository import BlueprintRepository
        repo = BlueprintRepository(db_proxy)

        bp = await repo.create_blueprint("test-user", {
            "name": "Before Update",
            "category": "general",
            "content": "# Before\nOld content",
        })

        updated = await repo.update_blueprint(bp["blueprint_id"], {
            "name": "After Update",
            "content": "# After\nNew content",
        })
        assert updated is not None
        assert updated["name"] == "After Update"

    async def test_soft_delete(self, db_proxy):
        from repositories.blueprint_repository import BlueprintRepository
        repo = BlueprintRepository(db_proxy)

        bp = await repo.create_blueprint("test-user", {
            "name": "To Delete",
            "category": "general",
            "content": "# Del\nContent",
        })

        deleted = await repo.soft_delete_blueprint(bp["blueprint_id"])
        assert deleted is True

        gone = await repo.get_by_blueprint_id(bp["blueprint_id"])
        assert gone is None

    async def test_increment_usage(self, db_proxy):
        from repositories.blueprint_repository import BlueprintRepository
        repo = BlueprintRepository(db_proxy)

        bp = await repo.create_blueprint("test-user", {
            "name": "Usage Track",
            "category": "general",
            "content": "# Usage\nContent",
        })
        assert bp["usage_count"] == 0

        await repo.increment_usage(bp["blueprint_id"])
        fetched = await repo.get_by_blueprint_id(bp["blueprint_id"])
        assert fetched["usage_count"] == 1

    async def test_get_nonexistent_returns_none(self, db_proxy):
        from repositories.blueprint_repository import BlueprintRepository
        repo = BlueprintRepository(db_proxy)

        result = await repo.get_by_blueprint_id("nonexistent-id")
        assert result is None

    async def test_soft_delete_nonexistent_returns_false(self, db_proxy):
        from repositories.blueprint_repository import BlueprintRepository
        repo = BlueprintRepository(db_proxy)

        result = await repo.soft_delete_blueprint("nonexistent-id")
        assert result is False


# ── Blueprint Library Sync Tests ──────────────────────────────────────

@pytest.mark.asyncio
class TestBlueprintLibrarySync:
    """Test syncing .md files to the database."""

    async def test_sync_to_db(self, db_proxy):
        from services.blueprint_library_service import BlueprintLibraryService
        svc = BlueprintLibraryService()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test blueprints
            for cat, slug, content in [
                ("strategy", "sync-test-a", "# Sync A\nDesc A.\n## Objective\nObj A"),
                ("product", "sync-test-b", "# Sync B\nDesc B.\n## Steps\n1. Step B"),
            ]:
                cat_dir = os.path.join(tmpdir, cat)
                os.makedirs(cat_dir, exist_ok=True)
                with open(os.path.join(cat_dir, f"{slug}.md"), "w") as f:
                    f.write(content)

            svc.LIBRARY_PATH = tmpdir
            collection = db_proxy["blueprints"]

            seeded = await svc.sync_library_to_db(collection)
            assert seeded == 2

            # Verify they're in the DB
            doc_a = await collection.find_one({"_id": "strategy-sync-test-a"})
            assert doc_a is not None
            assert doc_a["name"] == "Sync A"

            doc_b = await collection.find_one({"_id": "product-sync-test-b"})
            assert doc_b is not None
            assert doc_b["name"] == "Sync B"

    async def test_sync_idempotent(self, db_proxy):
        from services.blueprint_library_service import BlueprintLibraryService
        svc = BlueprintLibraryService()

        with tempfile.TemporaryDirectory() as tmpdir:
            cat_dir = os.path.join(tmpdir, "general")
            os.makedirs(cat_dir, exist_ok=True)
            with open(os.path.join(cat_dir, "idempotent.md"), "w") as f:
                f.write("# Idempotent\nDesc.\n## Objective\nObj")

            svc.LIBRARY_PATH = tmpdir
            collection = db_proxy["blueprints"]

            first_run = await svc.sync_library_to_db(collection)
            assert first_run == 1

            second_run = await svc.sync_library_to_db(collection)
            assert second_run == 0  # Already exists, skip


# ── API Endpoint Tests ────────────────────────────────────────────────

class TestBlueprintsAPI:
    """Test Blueprint REST endpoints via FastAPI TestClient."""

    def test_list_blueprints_empty(self, test_app):
        resp = test_app.get("/api/v1/blueprints/")
        assert resp.status_code == 200
        data = resp.json()
        assert "blueprints" in data
        assert "total_count" in data

    def test_create_blueprint(self, test_app):
        resp = test_app.post("/api/v1/blueprints/", json={
            "name": "API Test Blueprint",
            "description": "Created via API",
            "category": "strategy",
            "content": "# API Test\n\nAPI content here.",
            "tags": ["api", "test"],
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "success"
        assert data["data"]["name"] == "API Test Blueprint"
        assert data["data"]["category"] == "strategy"
        assert data["data"]["source"] == "custom"

    def test_create_and_get_blueprint(self, test_app):
        # Create
        resp = test_app.post("/api/v1/blueprints/", json={
            "name": "Get Test Blueprint",
            "category": "product",
            "content": "# Get Test\n\nContent.",
        })
        assert resp.status_code == 201
        bp_id = resp.json()["data"]["blueprint_id"]

        # Get
        resp = test_app.get(f"/api/v1/blueprints/{bp_id}")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["name"] == "Get Test Blueprint"
        assert data["content"] == "# Get Test\n\nContent."

    def test_create_and_list_blueprint(self, test_app):
        resp = test_app.post("/api/v1/blueprints/", json={
            "name": "List Test Blueprint",
            "category": "marketing",
            "content": "# List Test\n\nContent.",
        })
        assert resp.status_code == 201
        bp_id = resp.json()["data"]["blueprint_id"]

        resp = test_app.get("/api/v1/blueprints/")
        blueprints = resp.json()["blueprints"]
        assert any(b["blueprint_id"] == bp_id for b in blueprints)

    def test_update_blueprint(self, test_app):
        # Create
        resp = test_app.post("/api/v1/blueprints/", json={
            "name": "Update Me",
            "category": "general",
            "content": "# Old\n\nOld content.",
        })
        bp_id = resp.json()["data"]["blueprint_id"]

        # Update
        resp = test_app.patch(f"/api/v1/blueprints/{bp_id}", json={
            "name": "Updated Name",
            "content": "# New\n\nNew content.",
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "Updated Name"

    def test_delete_blueprint(self, test_app):
        # Create
        resp = test_app.post("/api/v1/blueprints/", json={
            "name": "Delete Me",
            "category": "general",
            "content": "# Del\n\nContent.",
        })
        bp_id = resp.json()["data"]["blueprint_id"]

        # Delete
        resp = test_app.delete(f"/api/v1/blueprints/{bp_id}")
        assert resp.status_code == 200

        # Verify gone
        resp = test_app.get(f"/api/v1/blueprints/{bp_id}")
        assert resp.status_code == 404

    def test_get_nonexistent_blueprint(self, test_app):
        resp = test_app.get("/api/v1/blueprints/nonexistent-id")
        assert resp.status_code == 404

    def test_delete_nonexistent_blueprint(self, test_app):
        resp = test_app.delete("/api/v1/blueprints/nonexistent-id")
        assert resp.status_code == 404

    def test_list_with_category_filter(self, test_app):
        test_app.post("/api/v1/blueprints/", json={
            "name": "Filter Strategy",
            "category": "strategy",
            "content": "# FS\nContent.",
        })
        test_app.post("/api/v1/blueprints/", json={
            "name": "Filter Product",
            "category": "product",
            "content": "# FP\nContent.",
        })

        resp = test_app.get("/api/v1/blueprints/?category=strategy")
        assert resp.status_code == 200
        blueprints = resp.json()["blueprints"]
        assert all(b["category"] == "strategy" for b in blueprints)

    def test_list_with_search(self, test_app):
        test_app.post("/api/v1/blueprints/", json={
            "name": "Unique Searchable Name XYZ123",
            "category": "general",
            "content": "# Search\nContent.",
        })

        resp = test_app.get("/api/v1/blueprints/?search=XYZ123")
        assert resp.status_code == 200
        assert resp.json()["total_count"] >= 1

    def test_create_blueprint_validation(self, test_app):
        # Missing name
        resp = test_app.post("/api/v1/blueprints/", json={
            "category": "general",
            "content": "# No Name",
        })
        assert resp.status_code == 422

        # Missing content
        resp = test_app.post("/api/v1/blueprints/", json={
            "name": "No Content",
            "category": "general",
        })
        assert resp.status_code == 422


class TestBlueprintsLibraryAPI:
    """Test the library (file-based) endpoints."""

    def test_library_catalog(self, test_app):
        resp = test_app.get("/api/v1/blueprints/library")
        assert resp.status_code == 200
        data = resp.json()
        assert "blueprints" in data
        assert "total_count" in data
        assert "categories" in data

    def test_library_search(self, test_app):
        resp = test_app.get("/api/v1/blueprints/library/search?q=lean")
        assert resp.status_code == 200
        data = resp.json()
        assert "blueprints" in data

    def test_library_sync(self, test_app):
        resp = test_app.post("/api/v1/blueprints/library/sync")
        assert resp.status_code == 200
        assert "message" in resp.json()
