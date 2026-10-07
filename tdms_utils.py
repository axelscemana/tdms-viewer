"""Utilitaires de lecture TDMS avec support gros fichiers (streaming + décimation)."""
from pathlib import Path
import numpy as np
import pandas as pd
from nptdms import TdmsFile


def get_structure(path: str | Path) -> dict:
    """Retourne propriétés fichier + groupes/canaux sans charger les données."""
    path = Path(path)
    out = {"file_properties": {}, "groups": {}}
    with TdmsFile.open(str(path)) as f:
        out["file_properties"] = dict(f.properties)
        for group in f.groups():
            ch_info = {}
            for ch in group.channels():
                props = dict(ch.properties)
                ch_info[ch.name] = {
                    "properties": props,
                    "length": len(ch),
                    "dtype": str(ch.dtype),
                    "unit": props.get("unit_string", props.get("unit", "")),
                }
            out["groups"][group.name] = {
                "properties": dict(group.properties),
                "channels": ch_info,
            }
    return out


def _time_axis(ch, data_len: int) -> np.ndarray | None:
    """Construit l'axe temps si wf_start_time / wf_increment présents, sinon None."""
    try:
        props = ch.properties
        if "wf_start_time" in props and "wf_increment" in props:
            inc = float(props["wf_increment"])
            return np.arange(data_len) * inc
    except Exception:
        pass
    return None


def read_channel_decimated(path: str | Path, group: str, channel: str,
                           max_points: int = 2000) -> dict:
    """Lit un canal et le décime à ~max_points pour affichage Plotly.

    MVP : lecture complète puis décimation. V Pro : lecture par blocs.
    Retourne {x, y, full_length, decimation_factor, unit, properties}.
    """
    with TdmsFile.open(str(path)) as f:
        ch = f[group][channel]
        n = len(ch)
        props = dict(ch.properties)
        unit = props.get("unit_string", props.get("unit", ""))
        if n <= max_points:
            y = ch[:]
            x = _time_axis(ch, n)
            factor = 1
        else:
            factor = int(np.ceil(n / max_points))
            y = ch[:][::factor]
            t = _time_axis(ch, n)
            x = t[::factor] if t is not None else None
        if x is None:
            x = np.arange(len(y)) * factor  # axe en index échantillon
        return {
            "x": np.asarray(x),
            "y": np.asarray(y),
            "full_length": n,
            "decimation_factor": factor,
            "unit": unit,
            "properties": props,
        }


def read_channel_slice(path: str | Path, group: str, channel: str,
                       offset: int = 0, length: int | None = None) -> np.ndarray:
    """Re-fetch pleine résolution sur une zone (pour zoom précis)."""
    with TdmsFile.open(str(path)) as f:
        ch = f[group][channel]
        n = len(ch)
        offset = max(0, offset)
        end = n if length is None else min(n, offset + length)
        return ch[offset:end]


def channel_to_dataframe(path: str | Path, group: str, channel: str) -> pd.DataFrame:
    """Charge un canal entier en DataFrame (x + y). Attention RAM sur gros fichiers."""
    d = read_channel_decimated(path, group, channel, max_points=10**12)
    return pd.DataFrame({"x": d["x"], "y": d["y"]})
