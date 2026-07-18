from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_dataease_overlay_refreshes_stale_browser_key_before_loading_official_app():
    source = (PROJECT_ROOT / "deploy" / "dataease-overlay" / "static" / "index.html").read_text(encoding="utf-8")

    assert "./de2api/dekey" in source
    assert "cache: 'no-store'" in source
    assert "localStorage.removeItem(DATAEASE_KEY)" in source
    assert "v: JSON.stringify(payload.data)" in source
    assert "localStorage.setItem(DATAEASE_KEY, JSON.stringify(cacheItem))" in source
    assert "douyinLive.dataeaseKeySha256" in source
    assert "await refreshDataEaseKey()" in source
    assert "await import('./js/index-2.10.20-dataease.js')" in source
    assert source.index("localStorage.removeItem(DATAEASE_KEY)") < source.index("fetch('./de2api/dekey'")
    assert source.index("localStorage.setItem(DATAEASE_KEY") < source.index("await import('./js/index-2.10.20-dataease.js')")


def test_compose_mounts_dataease_overlay_before_classpath_static_resources():
    source = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "./deploy/dataease-overlay/static:/opt/dataease-overlay:ro" in source
    assert "file:/opt/dataease-overlay/,classpath:/META-INF/resources/" in source


def test_doctor_distinguishes_historical_key_errors_from_an_inactive_overlay():
    source = (PROJECT_ROOT / "scripts" / "doctor.sh").read_text(encoding="utf-8")

    assert "DATAEASE_OVERLAY_ACTIVE=false" in source
    assert 'grep -q "douyinLive.dataeaseKeySha256"' in source
    assert "DataEase 存在历史旧公钥错误，自动刷新层已启用" in source
