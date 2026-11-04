def test_phase1_tables_registered() -> None:
    import app.models  # noqa: F401
    from app.db.base import Base

    assert set(Base.metadata.tables) == {"users", "user_sessions", "projects", "audit_logs"}
