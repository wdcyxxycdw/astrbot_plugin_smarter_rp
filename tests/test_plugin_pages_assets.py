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


def test_webui_html_installs_boot_error_handler_before_entry_script():
    source = (ROOT / "webui" / "index.html").read_text(encoding="utf-8")

    assert source.index("window.__smarterRpBootError") < source.index('/src/main.jsx')
    assert "window.addEventListener('error'" in source
    assert "window.addEventListener('unhandledrejection'" in source


def test_app_imports_react_binding_for_jsx_runtime_output():
    source = (ROOT / "webui" / "src" / "App.jsx").read_text(encoding="utf-8")

    assert "import React," in source


def test_webui_primary_copy_is_chinese():
    app_source = (ROOT / "webui" / "src" / "App.jsx").read_text(encoding="utf-8")
    html_source = (ROOT / "webui" / "index.html").read_text(encoding="utf-8")
    metadata = (ROOT / "metadata.yaml").read_text(encoding="utf-8")

    assert "控制台" in app_source
    assert "角色" in app_source
    assert "世界书" in app_source
    assert "记忆" in app_source
    assert "正在加载 WebUI" in html_source
    assert "管理 Smarter RP" in metadata

    assert "label: 'Dashboard'" not in app_source
    assert "label: 'Characters'" not in app_source
    assert "label: 'Lorebooks'" not in app_source
    assert "Loading WebUI" not in html_source
    assert "Manage Smarter RP" not in metadata


def test_webui_configures_antd_chinese_locale():
    source = (ROOT / "webui" / "src" / "App.jsx").read_text(encoding="utf-8")

    assert "antd/locale/zh_CN" in source
    assert "locale={zhCN}" in source


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
    js_assets = [path for path in assets_dir.iterdir() if path.suffix == ".js"]
    css_assets = [path for path in assets_dir.iterdir() if path.suffix == ".css"]
    js_sources = "\n".join(path.read_text(encoding="utf-8") for path in js_assets)

    assert (page_root / "index.html").exists()
    assert js_assets
    assert css_assets
    assert any(path.name in index for path in js_assets)
    for asset_path in css_assets:
        assert asset_path.name in index or asset_path.name in js_sources
    for asset_path in js_assets:
        assert asset_path.name in index or asset_path.name in js_sources
