def test_phase1_tables_registered() -> None:
    import app.models  # noqa: F401
    from app.db.base import Base

    assert set(Base.metadata.tables) == {
        "users",
        "user_sessions",
        "projects",
        "audit_logs",
        "api_endpoints",
        "generation_tasks",
        "generation_targets",
        "test_cases",
        "test_case_versions",
        "review_events",
        "test_runs",
        "run_results",
        "data_reports",
        "project_environments",
        "project_members",
        "suites",
        "suite_items",
        "idempotency_records",
        "notifications",
        "defect_candidates",
        "schedules",
        "schedule_events",
    }
