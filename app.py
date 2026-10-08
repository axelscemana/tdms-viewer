"""TDMS Viewer : visualisation + analyse FFT/filtres/pics + export CSV/PDF (FR/EN)."""
import tempfile
from pathlib import Path
import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import numpy as np

from tdms_utils import get_structure, read_channel_decimated, channel_to_dataframe
from analysis import get_fs, compute_fft, apply_filter, detect_peaks
from report import build_pdf

T = {
    "fr": {
        "source": "Source du fichier", "upload": "Upload",
        "local": "Fichier local (gros fichiers)",
        "drop": "Glisser-déposer un fichier .tdms ou .csv (format export x;y)",
        "local_path": "Chemin local (.tdms ou .csv exporté)",
        "local_size": "Mo (pas d'upload, lecture directe)",
        "not_found": "Fichier introuvable.",
        "max_pts": "Points max / courbe (décimation)",
        "waiting": "En attente d'un fichier. Upload demo ou mode local : `data/big_500mo.tdms`",
        "csv_title": "Fichier CSV (export x;y)",
        "csv_bad": "CSV illisible :",
        "csv_cols": "CSV sans colonnes x,y (trouvé :",
        "csv_hint": "Utilisez un CSV généré par `tdms-viewer export`.",
        "rows": "lignes", "y_range": "y de", "y_to": "à",
        "analysis": "Analyse", "fs": "Fréquence d'échantillonnage (Hz)",
        "filter": "Filtre", "cutoff": "Cutoff (Hz)", "order": "Ordre",
        "prom": "Prominence pics", "dist": "Distance min pics (pts)",
        "sig_filt": "signal filtré", "peaks": "pics",
        "sig_peaks": "Signal + pics", "spec": "Spectre FFT",
        "amplitude": "amplitude", "found": "pics détectés. Raie dominante :",
        "gen_pdf": "Générer PDF", "dl_pdf": "Télécharger PDF", "pdf_ok": "PDF prêt.",
        "csv_note": "CSV : filtre", "file": "Fichier",
        "group": "Groupe", "channels": "Canaux",
        "col_chan": "canal", "col_pts": "points", "col_unit": "unité",
        "group_of": "Groupe", "of_chans": "canaux",
        "ch_info": "pts, décimation ×", "unit": "unité",
        "x_axis": "temps (s) ou index", "y_axis": "valeur", "legend": "canaux",
        "analysis_v2": "Analyse (V2)", "ana_chan": "Canal analysé",
        "full_res": "pleine résolution", "decimated": "décimé ×",
        "fs_eff": "fs eff.", "analysis_is": "Analyse :",
        "filtered": "filtré", "exports": "Exports", "exp_chan": "Canal à exporter",
        "prep_csv": "Préparer CSV", "dl_csv": "Télécharger CSV",
        "pdf_note": "Filtre", "lang": "Langue / Language",
    },
    "en": {
        "source": "File source", "upload": "Upload",
        "local": "Local file (large files)",
        "drop": "Drag & drop a .tdms or .csv file (x;y export format)",
        "local_path": "Local path (.tdms or exported .csv)",
        "local_size": "MB (no upload, direct read)",
        "not_found": "File not found.",
        "max_pts": "Max points / trace (decimation)",
        "waiting": "Waiting for a file. Demo upload or local mode: `data/big_500mo.tdms`",
        "csv_title": "CSV file (x;y export)",
        "csv_bad": "Unreadable CSV:",
        "csv_cols": "CSV without x,y columns (found:",
        "csv_hint": "Use a CSV made by `tdms-viewer export`.",
        "rows": "rows", "y_range": "y from", "y_to": "to",
        "analysis": "Analysis", "fs": "Sampling rate (Hz)",
        "filter": "Filter", "cutoff": "Cutoff (Hz)", "order": "Order",
        "prom": "Peak prominence", "dist": "Min peak distance (pts)",
        "sig_filt": "filtered signal", "peaks": "peaks",
        "sig_peaks": "Signal + peaks", "spec": "FFT spectrum",
        "amplitude": "amplitude", "found": "peaks found. Dominant tone:",
        "gen_pdf": "Generate PDF", "dl_pdf": "Download PDF", "pdf_ok": "PDF ready.",
        "csv_note": "CSV: filter", "file": "File",
        "group": "Group", "channels": "Channels",
        "col_chan": "channel", "col_pts": "points", "col_unit": "unit",
        "group_of": "Group", "of_chans": "channels",
        "ch_info": "pts, decimation ×", "unit": "unit",
        "x_axis": "time (s) or index", "y_axis": "value", "legend": "channels",
        "analysis_v2": "Analysis (V2)", "ana_chan": "Channel analyzed",
        "full_res": "full resolution", "decimated": "decimated ×",
        "fs_eff": "eff. fs", "analysis_is": "Analysis:",
        "filtered": "filtered", "exports": "Exports", "exp_chan": "Channel to export",
        "prep_csv": "Prepare CSV", "dl_csv": "Download CSV",
        "pdf_note": "Filter", "lang": "Langue / Language",
    },
}

st.set_page_config(page_title="TDMS Viewer", layout="wide")
lang_choice = st.sidebar.selectbox("Langue / Language", ["Français", "English"], index=0)
lang = "en" if lang_choice == "English" else "fr"
t = T[lang]

st.title("TDMS Viewer & Report")

mode = st.radio(t["source"], [t["upload"], t["local"]], horizontal=True)
tdms_path = None
if mode == t["upload"]:
    uploaded = st.file_uploader(t["drop"], type=["tdms", "csv"])
    if uploaded:
        suffix = ".csv" if uploaded.name.lower().endswith(".csv") else ".tdms"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(uploaded.read())
            tdms_path = tmp.name
else:
    default_big = "data/big_500mo.tdms"
    local = st.text_input(t["local_path"], value=default_big)
    if local and Path(local).exists():
        tdms_path = local
        st.caption(f"Fichier local : {Path(local).stat().st_size/1e6:.0f} {t['local_size']}")
    elif local:
        st.error(t["not_found"])
max_points = st.sidebar.slider(t["max_pts"], 500, 10000, 2000, 500)

if not tdms_path:
    st.info(t["waiting"])
    st.stop()

if tdms_path.lower().endswith(".csv"):
    st.subheader(t["csv_title"])
    try:
        from tdms_utils import read_export_csv
        df_csv = read_export_csv(tdms_path)
    except Exception as e:
        st.error(f"{t['csv_bad']} {e}")
        st.stop()
    if not {"x", "y"}.issubset(df_csv.columns):
        st.error(f"{t['csv_cols']} {list(df_csv.columns)}). {t['csv_hint']}")
        st.stop()
    x_all = df_csv["x"].to_numpy(dtype=float)
    y_all = df_csv["y"].to_numpy(dtype=float)
    st.caption(f"{Path(tdms_path).name} : {len(df_csv)} {t['rows']}, "
               f"{t['y_range']} {y_all.min():.3f} {t['y_to']} {y_all.max():.3f}")
    st.dataframe(df_csv.head(10), use_container_width=True)
    dx = float(np.median(np.diff(x_all))) if len(x_all) > 1 else 0.0
    fs_guess = float(1.0 / dx) if dx > 0 else 1000.0
    st.header(f"{t['analysis']} CSV")
    fs_c = st.number_input(t["fs"], value=float(fs_guess), min_value=1.0)
    c1, c2, c3 = st.columns(3)
    with c1:
        fkind_c = st.selectbox(t["filter"], ["none", "lowpass", "highpass"], index=0)
    with c2:
        cutoff_c = st.number_input(t["cutoff"], value=100.0, min_value=0.0)
    with c3:
        order_c = st.slider(t["order"], 2, 8, 4)
    prom_c = st.slider(t["prom"], 0.0, 5.0, 0.5, 0.1)
    dist_c = st.slider(t["dist"], 1, 2000, 100)
    y_filt_c = apply_filter(y_all, fs_c, fkind_c, cutoff_c, order_c)
    peaks_c = detect_peaks(y_filt_c, prominence=prom_c, distance=dist_c)
    freqs_c, mag_c = compute_fft(y_filt_c, fs_c)
    step_c = max(1, len(x_all) // 2000)
    fig_c = go.Figure()
    fig_c.add_trace(go.Scatter(x=x_all[::step_c], y=y_filt_c[::step_c],
                               mode="lines", name=t["sig_filt"]))
    if len(peaks_c):
        pk = peaks_c[peaks_c < len(x_all)]
        fig_c.add_trace(go.Scatter(x=x_all[pk], y=y_filt_c[pk],
                                   mode="markers", name=f"{len(pk)} {t['peaks']}",
                                   marker={"color": "red", "size": 7}))
    fig_c.update_layout(height=350, title=f"CSV {t['sig_peaks'].split(' ', 1)[-1]}")
    st.plotly_chart(fig_c, use_container_width=True)
    fig_c2 = go.Figure()
    fig_c2.add_trace(go.Scatter(x=freqs_c, y=mag_c, mode="lines", name="FFT"))
    fig_c2.update_layout(height=300, title=t["spec"], xaxis_title="Hz",
                         yaxis_title=t["amplitude"], yaxis_type="log")
    st.plotly_chart(fig_c2, use_container_width=True)
    st.caption(f"{len(peaks_c)} {t['found']} "
               f"{freqs_c[int(np.argmax(mag_c))]:.1f} Hz")
    if st.button(t["gen_pdf"]):
        out = Path(tempfile.mkdtemp()) / f"{Path(tdms_path).stem}.pdf"
        build_pdf(out, {"source": Path(tdms_path).name, "lignes": len(df_csv),
                        "sampling_rate": fs_c},
                  Path(tdms_path).stem, {"unit_string": ""}, fs_c,
                  x_all[::step_c], y_filt_c[::step_c], peaks_c, freqs_c, mag_c,
                  note=f"{t['csv_note']} {fkind_c} {cutoff_c}Hz, {len(peaks_c)} {t['peaks']}.",
                  lang=lang)
        st.download_button(t["dl_pdf"], out.read_bytes(),
                           out.name, "application/pdf")
        st.success(t["pdf_ok"])
    st.stop()

struct = get_structure(tdms_path)
st.subheader(t["file"])
st.json(struct["file_properties"])

groups = list(struct["groups"].keys())
group = st.sidebar.selectbox(t["group"], groups)
channels = list(struct["groups"][group]["channels"].keys())
selected = st.sidebar.multiselect(t["channels"], channels, default=channels[:2])

rows = [{t["col_chan"]: n, t["col_pts"]: i["length"], "dtype": i["dtype"],
         t["col_unit"]: i["unit"]}
        for n, i in struct["groups"][group]["channels"].items()]
st.subheader(f"{t['group_of']} {group} — {len(channels)} {t['of_chans']}")
st.dataframe(pd.DataFrame(rows), use_container_width=True)

# --- visualisation ---
fig = go.Figure()
cache = {}
for ch_name in selected:
    d = read_channel_decimated(tdms_path, group, ch_name, max_points=max_points)
    cache[ch_name] = d
    fig.add_trace(go.Scatter(x=d["x"], y=d["y"], mode="lines", name=ch_name))
    st.caption(f"{ch_name} : {d['full_length']} pts, {t['ch_info']}{d['decimation_factor']}, "
               f"{t['unit']} {d['unit']}")
fig.update_layout(xaxis_title=t["x_axis"], yaxis_title=t["y_axis"],
                  legend_title=t["legend"], height=450)
fig.update_xaxes(rangeslider_visible=True)
st.plotly_chart(fig, use_container_width=True)

# --- analyse : FFT / filtre / pics ---
st.header(t["analysis_v2"])
ana_ch = st.selectbox(t["ana_chan"], channels,
                      index=channels.index(selected[0]) if selected else 0)
d = cache.get(ana_ch) or read_channel_decimated(tdms_path, group, ana_ch, max_points=max_points)
props = d["properties"]
fs_default = get_fs(props, 1000.0)
fs = st.number_input(t["fs"], value=float(fs_default), min_value=1.0)
# Analyse en pleine résolution si raisonnable, sinon signal décimé + fs effective
from tdms_utils import read_channel_slice
n_full = struct["groups"][group]["channels"][ana_ch]["length"]
if n_full <= 500_000:
    from nptdms import TdmsFile
    with TdmsFile.open(tdms_path) as _f:
        _ch = _f[group][ana_ch]
        y_ana = _ch[:]
        _t = None
        try:
            if "wf_increment" in _ch.properties:
                _t = np.arange(n_full) * float(_ch.properties["wf_increment"])
        except Exception:
            pass
    x_ana = _t if _t is not None else np.arange(n_full)
    fs_ana, dec_note = fs, t["full_res"]
else:
    y_ana, x_ana = d["y"], d["x"]
    fs_ana = fs / max(1, d["decimation_factor"])
    dec_note = f"{t['decimated']}{d['decimation_factor']} ({t['fs_eff']} {fs_ana:.1f} Hz)"
st.caption(f"{t['analysis_is']} {dec_note}")
col1, col2, col3 = st.columns(3)
with col1:
    fkind = st.selectbox(t["filter"], ["none", "lowpass", "highpass"], index=0)
with col2:
    cutoff = st.number_input(t["cutoff"], value=100.0, min_value=0.0)
with col3:
    order = st.slider(t["order"], 2, 8, 4)
prom = st.slider(t["prom"], 0.0, 5.0, 0.5, 0.1)
dist = st.slider(t["dist"], 1, 2000, 100)

y_filt = apply_filter(y_ana, fs_ana, fkind, cutoff, order)
peaks = detect_peaks(y_filt, prominence=prom, distance=dist)
freqs, mag = compute_fft(y_filt, fs_ana)

fig2 = go.Figure()
fig2.add_trace(go.Scatter(x=x_ana, y=y_filt, mode="lines", name=f"{ana_ch} {t['filtered']}"))
if len(peaks):
    fig2.add_trace(go.Scatter(x=x_ana[peaks], y=y_filt[peaks],
                             mode="markers", name=f"{len(peaks)} {t['peaks']}",
                             marker={"color": "red", "size": 7}))
fig2.update_layout(height=350, title=t["sig_peaks"])
st.plotly_chart(fig2, use_container_width=True)

fig3 = go.Figure()
fig3.add_trace(go.Scatter(x=freqs, y=mag, mode="lines", name="FFT"))
fig3.update_layout(height=300, title=t["spec"], xaxis_title="Hz",
                   yaxis_title=t["amplitude"], yaxis_type="log")
st.plotly_chart(fig3, use_container_width=True)
st.caption(f"{len(peaks)} {t['found']} {freqs[int(np.argmax(mag))]:.1f} Hz")

# --- exports ---
st.header(t["exports"])
exp_channel = st.selectbox(t["exp_chan"], channels, key="exp")
c1, c2 = st.columns(2)
with c1:
    if st.button(t["prep_csv"]):
        df = channel_to_dataframe(tdms_path, group, exp_channel)
        st.download_button(t["dl_csv"], df.to_csv(index=False, sep=";").encode(),
                           f"{group}_{exp_channel}.csv", "text/csv")
with c2:
    if st.button(t["gen_pdf"]):
        out = Path(tempfile.mkdtemp()) / f"{group}_{ana_ch}.pdf"
        fp = dict(struct["file_properties"])
        try:
            fp["taille_fichier"] = Path(tdms_path).stat().st_size
        except Exception:
            pass
        fp["echantillons"] = n_full
        build_pdf(out, fp, f"{group}/{ana_ch}",
                  d["properties"], fs_ana, x_ana, y_filt, peaks, freqs, mag,
                  note=f"{t['pdf_note']} {fkind} {cutoff}Hz, {len(peaks)} {t['peaks']}.",
                  lang=lang)
        st.download_button(t["dl_pdf"], out.read_bytes(),
                           out.name, "application/pdf")
        st.success(t["pdf_ok"])
