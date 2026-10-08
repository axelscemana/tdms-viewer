"""Tests autonomes : le fichier .tdms est genere a la volee (pas de donnees commitees)."""
import numpy as np
import pandas as pd
import pytest
from nptdms import TdmsWriter, RootObject, GroupObject, ChannelObject

from tdms_utils import get_structure, read_channel_decimated, read_channel_slice
from analysis import compute_fft, apply_filter, detect_peaks

FS = 1000.0
N = 10_000  # 10 s @ 1 kHz, 50 Hz pur + bruit


@pytest.fixture(scope="module")
def sample_tdms(tmp_path_factory):
    p = tmp_path_factory.mktemp("data") / "sample.tdms"
    rng = np.random.default_rng(42)
    t = np.arange(N) / FS
    y = np.sin(2 * np.pi * 50 * t) + 0.05 * rng.standard_normal(N)
    with TdmsWriter(str(p)) as w:
        w.write_segment([
            RootObject(properties={"author": "pytest"}),
            GroupObject("Vibration"),
            ChannelObject("Vibration", "accel_x", y,
                          properties={"unit_string": "g", "wf_increment": 1.0 / FS}),
        ])
    return str(p)


def test_structure(sample_tdms):
    s = get_structure(sample_tdms)
    ch = s["groups"]["Vibration"]["channels"]["accel_x"]
    assert ch["length"] == N
    assert ch["unit"] == "g"


def test_decimation_bounds(sample_tdms):
    d = read_channel_decimated(sample_tdms, "Vibration", "accel_x", max_points=2000)
    assert len(d["y"]) <= 2000
    assert d["full_length"] == N
    assert d["decimation_factor"] == 5


def test_slice_full_res(sample_tdms):
    z = read_channel_slice(sample_tdms, "Vibration", "accel_x", offset=100, length=500)
    assert len(z) == 500


def test_fft_known_50hz(sample_tdms):
    y = read_channel_slice(sample_tdms, "Vibration", "accel_x")
    f, m = compute_fft(y, FS)
    assert abs(float(f[int(np.argmax(m))]) - 50.0) < 1.0


def test_filter_keeps_length(sample_tdms):
    y = read_channel_slice(sample_tdms, "Vibration", "accel_x")
    assert len(apply_filter(y, FS, "lowpass", 100.0)) == len(y)


def test_peaks_found(sample_tdms):
    y = read_channel_slice(sample_tdms, "Vibration", "accel_x")
    assert len(detect_peaks(y, prominence=0.5, distance=10)) > 100


def test_pdf_builds(sample_tdms, tmp_path):
    from report import build_pdf
    d = read_channel_decimated(sample_tdms, "Vibration", "accel_x", max_points=2000)
    out = tmp_path / "r.pdf"
    build_pdf(out, {"author": "pytest & <test>"}, "Vibration/accel_x",
              d["properties"], FS, d["x"], d["y"], [],
              np.array([0.0, 50.0]), np.array([0.01, 1.0]))
    assert out.stat().st_size > 0


def test_export_channel_chunked(sample_tdms, tmp_path):
    from tdms_utils import export_channel_to_csv, read_export_csv
    out = tmp_path / "accel_x.csv"
    info = export_channel_to_csv(sample_tdms, "Vibration", "accel_x",
                                 out, chunk_size=3000)
    assert info["rows"] == N
    df = read_export_csv(out)
    assert list(df.columns) == ["x", "y"]
    assert len(df) == N
    # axe temps : wf_increment = 1/FS
    assert abs(float(df["x"].iloc[1]) - 1.0 / FS) < 1e-9


def test_export_batch_dossier(sample_tdms, tmp_path):
    import json
    import shutil
    from pathlib import Path
    from tdms_utils import export_batch
    src = tmp_path / "src"
    src.mkdir()
    shutil.copy(sample_tdms, src / "a.tdms")
    shutil.copy(sample_tdms, src / "b.tdms")
    manifests = export_batch(src, tmp_path / "exports", chunk_size=4000)
    assert len(manifests) == 2
    for m in manifests:
        assert len(m["exported"]) == 1
        assert m["exported"][0]["rows"] == N
    manifest_path = Path(manifests[0]["exported"][0]["file"]).parent / "manifest.json"
    assert manifest_path.exists()
    assert "author" in json.loads(manifest_path.read_text(encoding="utf-8"))["file_properties"]


def test_scaling_info_extraction():
    from tdms_utils import scaling_info
    m = scaling_info({"NI_Scaling_Status": "unscaled",
                      "NI_Scale[1]_Scale_Type": "Polynomial",
                      "unit_string": "Volts"})
    assert m["scaling_applied"] is True
    assert m["scale_types"] == ["Polynomial"]
    assert m["unit"] == "Volts"


def test_export_manifest_scaling_fields(sample_tdms, tmp_path):
    from tdms_utils import export_file
    m = export_file(sample_tdms, tmp_path / "exp", chunk_size=4000)
    e = m["exported"][0]
    assert e["scaling_applied"] is True
    assert e["unit"] == "g"
    assert "scale_types" in e


def test_export_split_excel_parts(sample_tdms, tmp_path):
    from tdms_utils import export_channel_to_csv, read_export_csv
    out = tmp_path / "accel_x.csv"
    info = export_channel_to_csv(sample_tdms, "Vibration", "accel_x",
                                 out, chunk_size=3000, split_rows=4000)
    assert info["rows"] == N
    assert len(info["parts"]) == 3  # 4000 + 4000 + 2000
    assert [p["rows"] for p in info["parts"]] == [4000, 4000, 2000]
    full = read_export_csv(out)
    assert len(full) == N
    recat = pd.concat([read_export_csv(p["file"]) for p in info["parts"]],
                      ignore_index=True)
    assert len(recat) == N
    assert recat["y"].equals(full["y"])


def test_export_xlsx_workbook(sample_tdms, tmp_path):
    import pandas as pd
    from tdms_utils import export_file
    m = export_file(sample_tdms, tmp_path / "xls", chunk_size=4000,
                    out_format="xlsx", split_rows=4000)
    wb = tmp_path / "xls" / "sample" / "sample.xlsx"
    assert wb.exists()
    sheets = pd.ExcelFile(wb).sheet_names
    assert "Infos" in sheets  # canal découpé 4000/4000/2000 + Infos
    assert len([s for s in sheets if s != "Infos"]) == 3
    df = pd.read_excel(wb, sheet_name="Infos")
    assert "accel_x" in df["canal"].iloc[0]
    assert m["exported"][0]["rows"] == N


def test_export_separator_excel_fr(sample_tdms, tmp_path):
    from tdms_utils import export_channel_to_csv
    out = tmp_path / "sep.csv"
    export_channel_to_csv(sample_tdms, "Vibration", "accel_x", out)
    header = out.read_text(encoding="utf-8").splitlines()[0]
    assert header == "x;y"  # ouverture directe en 2 colonnes dans Excel FR


def test_pdf_builds_both_languages(sample_tdms, tmp_path):
    from report import build_pdf
    d = read_channel_decimated(sample_tdms, "Vibration", "accel_x", max_points=2000)
    for lang in ("fr", "en"):
        out = tmp_path / f"r_{lang}.pdf"
        build_pdf(out, {"author": "pytest", "taille_fichier": 1234567}, "Vibration/accel_x",
                  d["properties"], FS, d["x"], d["y"], [],
                  np.array([0.0, 50.0]), np.array([0.01, 1.0]), lang=lang)
        assert out.stat().st_size > 0
    fr = (tmp_path / "r_fr.pdf").read_bytes()
    en = (tmp_path / "r_en.pdf").read_bytes()
    assert fr != en  # titres/libellés différents selon la langue
