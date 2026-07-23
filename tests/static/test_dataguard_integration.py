from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_qc_app_accepts_direct_root_from_dataguard():
    main = (ROOT / "desktop" / "production" / "app" / "main.py").read_text(encoding="utf-8")
    assert "DATATANG_QC_ROOT" in main
    assert 'settings.setValue("last_root"' in main


def test_release_contains_dataguard_admin_and_user_packages():
    workflow = (ROOT / ".github" / "workflows" / "release-stable.yml").read_text(encoding="utf-8")
    assert "DataGuard-Admin-Suite.zip" in workflow
    assert "DataGuard-User.zip" in workflow
    assert (ROOT / "dataguard" / "dataguard-source.zip").is_file()
