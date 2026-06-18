import os

os.environ["DATABASE_PATH"] = ":memory:"

from app.authz import can_edit_manual, can_read_manual
from app.rag import ingest_manual, run_evaluation, search
from app.schemas import Manual, User


def manual(**overrides):
    data = {
        "id": "m1",
        "title": "テスト",
        "category": "予約",
        "body": "予約変更とキャンセル対応",
        "visibility": "company",
        "status": "published",
        "branch_id": None,
        "tags": [],
        "version": 1,
        "updated_at": "2026-01-01T00:00:00Z",
    }
    data.update(overrides)
    return Manual(**data)


def user(**overrides):
    data = {"id": "u1", "name": "u", "role": "nailist", "org_type": "branch", "branch_id": "shibuya"}
    data.update(overrides)
    return User(**data)


def test_admin_can_read_admin_only_manual():
    assert can_read_manual(user(role="admin", org_type="headquarters", branch_id=None), manual(visibility="admin_only"))


def test_branch_nailist_cannot_read_other_branch_manual():
    assert not can_read_manual(user(branch_id="shibuya"), manual(visibility="branch", branch_id="shinjuku"))


def test_branch_manager_can_edit_own_branch_manual_only():
    manager = user(role="manager", branch_id="shibuya")
    assert can_edit_manual(manager, manual(visibility="branch", branch_id="shibuya"))
    assert not can_edit_manual(manager, manual(visibility="branch", branch_id="shinjuku"))


def test_manager_cannot_edit_admin_only_manual():
    manager = user(role="manager", branch_id="shibuya")
    assert not can_edit_manual(manager, manual(visibility="admin_only"))
