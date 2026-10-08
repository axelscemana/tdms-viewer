"""Utilitaires de lecture TDMS avec support gros fichiers (streaming + décimation)."""
from pathlib import Path
import numpy as np
import pandas as pd
from nptdms import TdmsFile


def _drop_stale_index(path: str | Path) -> None:
    """Supprime le .tdms_index s'il est plus vieux que le .tdms (régénération).

    nptdms lève sinon 'did not find segment start header / tdms_index mismatch'.
    Le fichier index est un cache, il sera régénéré à la prochaine lecture.
    """
    p = Path(path)
    idx = p.with_suffix(p.suffix + "_index") if p.suffix else Path(str(p) + "_index")
    # nptdms nomme l'index <fichier>.tdms_index
    candidates = [p.parent / (p.name + "_index"), Path(str(p) + "_index"), idx]
    try:
        tdms_mtime = p.stat().st_mtime
    except OSError:
        return
    for c in candidates:
        try:
            if c.exists() and c.stat().st_mtime < tdms_mtime - 1:
                c.unlink()
        except OSError:
            pass


def get_structure(path: str | Path) -> dict:
    """Retourne propriétés fichier + groupes/canaux sans charger les données."""
    path = Path(path)
    _drop_stale_index(path)
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


def _safe_name(name: str, max_len: int = 80) -> str:
    """Nettoie un nom groupe/canal pour en faire un nom de fichier Windows valide."""
    import re
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    return (cleaned[:max_len] or "canal")


def _chunk_time_axis(increment: float | None, offset: int, length: int) -> np.ndarray:
    """Axe temps/index pour un bloc commençant à `offset`."""
    idx = offset + np.arange(length)
    if increment is not None:
        return idx * increment
    return idx.astype(np.float64)


def scaling_info(properties: dict) -> dict:
    """Résume la chaîne d'étalonnage NI d'un canal pour le manifest."""
    scale_types = sorted({str(v) for k, v in properties.items()
                          if k.endswith("_Scale_Type")})
    return {
        "scaling_applied": True,  # nptdms applique le scaling à la lecture (scaled=True)
        "scaling_status": str(properties.get("NI_Scaling_Status", "")),
        "scale_types": scale_types,
        "unit": str(properties.get("unit_string", properties.get("unit", ""))),
    }


def export_channel_to_csv(path: str | Path, group: str, channel: str,
                           out_csv: str | Path, chunk_size: int = 100_000,
                           split_rows: int | None = None) -> dict:
    """Exporte un canal vers CSV en streaming (RAM constante, valeurs scalées).

    nptdms applique le scaling NI (ex. polynomial DAQmx) à la lecture :
    le CSV contient des Volts, pas des comptes ADC bruts.
    Colonnes : x,y.

    split_rows : si défini (ex. 500000), découpe en plus en morceaux
    <stem>_part1.csv, <stem>_part2.csv... compatibles Excel (limite
    1 048 576 lignes). Le CSV complet est toujours écrit.
    Retourne {file, rows, parts, group, channel, + scaling_info}.
    """
    from nptdms import TdmsFile

    if split_rows is not None and split_rows < 1000:
        raise ValueError("split_rows doit valoir au moins 1000")

    out_csv = Path(out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    rows = 0
    parts: list[dict] = []
    _drop_stale_index(path)
    with TdmsFile.open(str(path)) as f:
        ch = f[group][channel]
        n = len(ch)
        props = dict(ch.properties)
        meta = scaling_info(props)
        try:
            inc = float(props["wf_increment"]) \
                if "wf_increment" in props else None
        except Exception:
            inc = None
        full_fh = open(out_csv, "w", newline="", encoding="utf-8")
        part_fh = None
        part_idx = 0
        part_rows = 0
        try:
            full_fh.write("x,y\n")
            for offset in range(0, n, chunk_size):
                end = min(n, offset + chunk_size)
                y = np.asarray(ch[offset:end])  # scaled=True par défaut
                x = _chunk_time_axis(inc, offset, end - offset)
                df = pd.DataFrame({"x": x, "y": y})
                df.to_csv(full_fh, header=False, index=False)
                rows += len(df)
                if split_rows:
                    pos = 0
                    while pos < len(df):
                        if part_fh is None:
                            part_idx += 1
                            part_path = out_csv.with_name(
                                f"{out_csv.stem}_part{part_idx}.csv")
                            part_fh = open(part_path, "w", newline="",
                                           encoding="utf-8")
                            part_fh.write("x,y\n")
                            part_rows = 0
                            parts.append({"file": str(part_path), "rows": 0})
                        space = split_rows - part_rows
                        take = df.iloc[pos:pos + space]
                        take.to_csv(part_fh, header=False, index=False)
                        part_rows += len(take)
                        parts[-1]["rows"] = part_rows
                        pos += len(take)
                        if part_rows >= split_rows:
                            part_fh.close()
                            part_fh = None
        finally:
            full_fh.close()
            if part_fh is not None:
                part_fh.close()
    return {"file": str(out_csv), "rows": rows, "parts": parts,
            "split_rows": split_rows,
            "group": group, "channel": channel, **meta}


def export_file(path: str | Path, out_dir: str | Path,
                chunk_size: int = 100_000,
                only_group: str | None = None,
                only_channel: str | None = None,
                split_rows: int | None = None) -> dict:
    """Exporte tous les canaux (ou un seul) d'un .tdms vers CSV + manifest.

    Arborescence : <out_dir>/<stem>/<groupe>_<canal>.csv (+ _partN.csv si split) + manifest.json
    """
    import json

    path = Path(path)
    out_sub = Path(out_dir) / _safe_name(path.stem)
    out_sub.mkdir(parents=True, exist_ok=True)
    struct = get_structure(path)
    exported = []
    for gname, g in struct["groups"].items():
        if only_group and gname != only_group:
            continue
        for cname in g["channels"]:
            if only_channel and cname != only_channel:
                continue
            dest = out_sub / f"{_safe_name(gname)}_{_safe_name(cname)}.csv"
            info = export_channel_to_csv(path, gname, cname, dest,
                                         chunk_size=chunk_size,
                                         split_rows=split_rows)
            exported.append(info)
    manifest = {
        "source": str(path),
        "file_properties": struct["file_properties"],
        "exported": exported,
    }
    with open(out_sub / "manifest.json", "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, default=str)
    return manifest


def export_batch(input_path: str | Path, out_dir: str | Path,
                 recursive: bool = False,
                 chunk_size: int = 100_000,
                 only_group: str | None = None,
                 only_channel: str | None = None,
                 split_rows: int | None = None) -> list[dict]:
    """Exporte un fichier .tdms ou tout un dossier (glob *.tdms).

    Retourne la liste des manifests (un par fichier source).
    Lève FileNotFoundError si rien trouvé.
    """
    src = Path(input_path)
    if src.is_file():
        files = [src]
    elif src.is_dir():
        pattern = "**/*.tdms" if recursive else "*.tdms"
        files = sorted(src.glob(pattern))
    else:
        # accepte aussi un glob direct type "data/*.tdms"
        files = sorted(Path().glob(str(input_path)))
    files = [f for f in files if f.suffix.lower() == ".tdms"]
    if not files:
        raise FileNotFoundError(f"Aucun .tdms trouvé pour : {input_path}")
    return [export_file(f, out_dir, chunk_size=chunk_size,
                        only_group=only_group,
                        only_channel=only_channel,
                        split_rows=split_rows) for f in files]
