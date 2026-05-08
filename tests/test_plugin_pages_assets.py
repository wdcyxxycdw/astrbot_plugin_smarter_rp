from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_metadata_registers_smarter_rp_plugin_page():
    metadata = (ROOT / "metadata.yaml").read_text(encoding="utf-8")

    assert "pages:" in metadata
    assert "name: dashboard" in metadata
    assert "title: Smarter RP" in metadata


def test_webui_uses_astrbot_plugin_page_bridge_with_token_fallback():
    source = (ROOT / "webui" / "src" / "App.jsx").read_text(encoding="utf-8")

    assert "window.AstrBotPluginPage" in source
    assert "bridge.apiGet" in source
    assert "bridge.apiPost" in source
    assert "fetch(path" in source


def test_vite_build_outputs_plugin_page_dashboard():
    package_json = (ROOT / "webui" / "package.json").read_text(encoding="utf-8")

    assert "../pages/dashboard" in package_json
    assert "build:plugin-page" in package_json


def test_plugin_page_build_uses_relative_assets():
    index = (ROOT / "pages" / "dashboard" / "index.html").read_text(encoding="utf-8")

    assert 'src="/assets/' not in index
    assert 'href="/assets/' not in index
    assert 'src="./assets/' in index or 'src="assets/' in index
    assert 'href="./assets/' in index or 'href="assets/' in index


def test_plugin_page_build_references_existing_assets():
    page_root = ROOT / "pages" / "dashboard"
    index = (page_root / "index.html").read_text(encoding="utf-8")
    assets_dir = page_root / "assets"

    assert (page_root / "index.html").exists()
    assert any(path.suffix == ".js" for path in assets_dir.iterdir())
    assert any(path.suffix == ".css" for path in assets_dir.iterdir())
    for asset_path in assets_dir.iterdir():
        if asset_path.suffix in {".js", ".css"}:
            assert asset_path.name in index
