"""Tests autonomes : le fichier .tdms est genere a la volee (pas de donnees commitees)."""
import numpy as np
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
