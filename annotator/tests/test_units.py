import pytest

from app.config import Settings
from app.executors.detectors import GroundingDinoExecutor
from app.executors.phenovision import PHENO_MAP
from app.features import FeatureCatalog
from app.images import ImageError, open_image, resolve_url


def test_catalog_loads_and_pheno_features_exist():
    cat = FeatureCatalog.load(Settings().features_path)
    assert "Время года" in cat.names()
    for name in PHENO_MAP:
        spec = cat.get(name)
        assert spec is not None and "phenovision" in spec.executors
        assert set(spec.value_names) == {"Да", "Нет"}


def test_dino_label_matching():
    spec = FeatureCatalog.load(Settings().features_path).get("Тип поверхности")
    m = GroundingDinoExecutor._match
    assert m("rocks", spec) == "Камень"
    assert m("snow on the ground", spec) == "Снег"
    assert m("snow", spec) == "Снег"
    assert m("", spec) is None


def test_resolve_url():
    assert resolve_url("/images/a.jpg", "http://nginx") == "http://nginx/images/a.jpg"
    with pytest.raises(ImageError):
        resolve_url("/images/a.jpg", "")
    with pytest.raises(ImageError):
        resolve_url("file:///etc/passwd", "")
    rw = [("http://localhost", "http://nginx")]
    assert resolve_url("http://localhost/images/a.jpg", "", rw) == "http://nginx/images/a.jpg"
    assert resolve_url("https://ext.ru/a.jpg", "", rw) == "https://ext.ru/a.jpg"


def test_download_cyrillic_url(tmp_path, jpeg_bytes):
    import http.server, threading, functools
    from app.images import download
    (tmp_path / "Лиственница_сибирская.jpg").write_bytes(jpeg_bytes)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(tmp_path))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{srv.server_port}/Лиственница_сибирская.jpg"
        assert download(url, 10_000_000, 5) == jpeg_bytes
    finally:
        srv.shutdown()


def test_open_image_rejects_garbage(jpeg_bytes):
    assert open_image(jpeg_bytes).size == (64, 48)
    with pytest.raises(ImageError):
        open_image(b"not an image")


def test_lifeform_from_db_values():
    from app.features import normalize_lifeform
    assert normalize_lifeform("Объект флоры") == "flora"
    assert normalize_lifeform("Объект фауны") == "fauna"
    assert normalize_lifeform("fauna") == "fauna"
    assert normalize_lifeform("") is None and normalize_lifeform("что-то") is None
