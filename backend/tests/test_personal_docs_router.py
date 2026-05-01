"""API contract tests for the Personal Docs router.

Uses the existing `test_app` fixture (which wires the FastAPI test client
against an in-memory SQLite proxy and overrides auth). Heavyweight ingest
isn't exercised here — that lives in test_personal_docs_service.py.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_list_folders_404_for_unknown_kb(test_app):
    r = test_app.get("/api/v1/personal-docs/kbs/missing/folders")
    assert r.status_code == 404


def test_create_folder_404_for_unknown_kb(test_app, tmp_path):
    r = test_app.post(
        "/api/v1/personal-docs/kbs/missing/folders",
        json={"path": str(tmp_path)},
    )
    assert r.status_code == 404


def test_create_folder_400_for_missing_path(test_app):
    # Seed a KB
    create = test_app.post(
        "/api/v1/knowledge-bases", json={"name": "K", "description": "x"}
    )
    assert create.status_code == 200
    kb_id = create.json()["item"]["_id"]

    r = test_app.post(
        f"/api/v1/personal-docs/kbs/{kb_id}/folders",
        json={"path": "Z:/definitely/not/a/folder/anywhere"},
    )
    assert r.status_code == 400


def test_get_folder_404(test_app):
    r = test_app.get("/api/v1/personal-docs/folders/missing")
    assert r.status_code == 404


def test_get_job_404(test_app):
    r = test_app.get("/api/v1/personal-docs/jobs/missing")
    assert r.status_code == 404


def test_confirm_job_404(test_app):
    r = test_app.post("/api/v1/personal-docs/jobs/missing/confirm")
    assert r.status_code == 404


def test_cancel_job_404(test_app):
    r = test_app.post("/api/v1/personal-docs/jobs/missing/cancel")
    assert r.status_code == 404


def test_list_jobs_returns_empty_for_unknown_source(test_app):
    # No 404 expected — empty list is fine
    r = test_app.get("/api/v1/personal-docs/folders/anything/jobs")
    assert r.status_code == 200
    assert r.json() == {"items": []}
