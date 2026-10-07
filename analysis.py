"""Analyse : FFT, filtres, détection de pics."""
import numpy as np
from scipy import signal


def get_fs(properties: dict, default: float = 1000.0) -> float:
    try:
        if "wf_increment" in properties:
            return float(1.0 / float(properties["wf_increment"]))
        if "sampling_rate" in properties:
            return float(properties["sampling_rate"])
    except Exception:
        pass
    return float(default)


def compute_fft(y: np.ndarray, fs: float, n_max: int = 200000) -> tuple[np.ndarray, np.ndarray]:
    """Spectre d'amplitude (rfft). Décime y si trop long pour rester fluide."""
    y = np.asarray(y, dtype=float)
    if len(y) > n_max:
        step = int(len(y) / n_max)
        y = y[::step]
        # fs inchangée, on sous-échantillonne juste pour l'affichage du spectre
    n = len(y)
    windowed = y - np.mean(y)
    spec = np.abs(np.fft.rfft(windowed)) / n
    freqs = np.fft.rfftfreq(n, d=1.0 / fs)
    return freqs, spec


def apply_filter(y: np.ndarray, fs: float, kind: str = "lowpass",
                 cutoff: float = 100.0, order: int = 4) -> np.ndarray:
    """Filtre Butterworth (lowpass/highpass). Retourne y inchangé si cutoff invalide."""
    y = np.asarray(y, dtype=float)
    nyq = fs / 2.0
    if cutoff <= 0 or cutoff >= nyq or kind == "none":
        return y
    try:
        sos = signal.butter(order, cutoff / nyq, btype="lowpass" if kind == "lowpass" else "highpass",
                            output="sos")
        return signal.sosfiltfilt(sos, y)
    except Exception:
        return y


def detect_peaks(y: np.ndarray, prominence: float = 0.5, distance: int = 100) -> np.ndarray:
    """Indices des pics via scipy.find_peaks."""
    y = np.asarray(y, dtype=float)
    peaks, _ = signal.find_peaks(y, prominence=prominence, distance=max(1, distance))
    return peaks
