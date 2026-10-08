"""TDMS Viewer : visualisation + analyse FFT/filtres/pics + export CSV/PDF."""
import tempfile
from pathlib import Path
import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import numpy as np

from tdms_utils import get_structure, read_channel_decimated, channel_to_dataframe
from analysis import get_fs, compute_fft, apply_filter, detect_peaks
from report import build_pdf

st.set_page_config(page_title="TDMS Viewer", layout="wide")
st.title("TDMS Viewer & Report")

mode = st.radio("Source du fichier", ["Upload", "Fichier local (gros fichiers)"],
                horizontal=True)
tdms_path = None
if mode == "Upload":
    uploaded = st.file_uploader("Glisser-déposer un fichier .tdms ou .csv (format export x,y)",
                                type=["tdms", "csv"])
    if uploaded:
        suffix = ".csv" if uploaded.name.lower().endswith(".csv") else ".tdms"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(uploaded.read())
            tdms_path = tmp.name
else:
    default_big = "data/big_500mo.tdms"
    local = st.text_input("Chemin local (.tdms ou .csv exporté)", value=default_big)
    if local and Path(local).exists():
        tdms_path = local
        st.caption(f"Fichier local : {Path(local).stat().st_size/1e6:.0f} Mo (pas d'upload, lecture directe)")
    elif local:
        st.error("Fichier introuvable.")
max_points = st.sidebar.slider("Points max / courbe (décimation)", 500, 10000, 2000, 500)

if not tdms_path:
    st.info("En attente d'un fichier. Upload demo ou mode local : `data/big_500mo.tdms`")
    st.stop()

if tdms_path.lower().endswith(".csv"):
    st.subheader("Fichier CSV (export x;y)")
    try:
        from tdms_utils import read_export_csv
        df_csv = read_export_csv(tdms_path)
    except Exception as e:
        st.error(f"CSV illisible : {e}")
        st.stop()
    if not {"x", "y"}.issubset(df_csv.columns):
        st.error(f"CSV sans colonnes x,y (trouvé : {list(df_csv.columns)}). "
                 "Utilisez un CSV généré par `tdms-viewer export`.")
        st.stop()
    x_all = df_csv["x"].to_numpy(dtype=float)
    y_all = df_csv["y"].to_numpy(dtype=float)
    st.caption(f"{Path(tdms_path).name} : {len(df_csv)} lignes, "
               f"y de {y_all.min():.3f} à {y_all.max():.3f}")
    st.dataframe(df_csv.head(10), use_container_width=True)
    dx = float(np.median(np.diff(x_all))) if len(x_all) > 1 else 0.0
    fs_guess = float(1.0 / dx) if dx > 0 else 1000.0
    st.header("Analyse CSV")
    fs_c = st.number_input("Fréquence d'échantillonnage (Hz)", value=float(fs_guess), min_value=1.0)
    c1, c2, c3 = st.columns(3)
    with c1:
        fkind_c = st.selectbox("Filtre", ["none", "lowpass", "highpass"], index=0)
    with c2:
        cutoff_c = st.number_input("Cutoff (Hz)", value=100.0, min_value=0.0)
    with c3:
        order_c = st.slider("Ordre", 2, 8, 4)
    prom_c = st.slider("Prominence pics", 0.0, 5.0, 0.5, 0.1)
    dist_c = st.slider("Distance min pics (pts)", 1, 2000, 100)
    y_filt_c = apply_filter(y_all, fs_c, fkind_c, cutoff_c, order_c)
    peaks_c = detect_peaks(y_filt_c, prominence=prom_c, distance=dist_c)
    freqs_c, mag_c = compute_fft(y_filt_c, fs_c)
    step_c = max(1, len(x_all) // 2000)
    fig_c = go.Figure()
    fig_c.add_trace(go.Scatter(x=x_all[::step_c], y=y_filt_c[::step_c],
                               mode="lines", name="signal filtré"))
    if len(peaks_c):
        pk = peaks_c[peaks_c < len(x_all)]
        fig_c.add_trace(go.Scatter(x=x_all[pk], y=y_filt_c[pk],
                                   mode="markers", name=f"{len(pk)} pics",
                                   marker={"color": "red", "size": 7}))
    fig_c.update_layout(height=350, title="Signal CSV + pics")
    st.plotly_chart(fig_c, use_container_width=True)
    fig_c2 = go.Figure()
    fig_c2.add_trace(go.Scatter(x=freqs_c, y=mag_c, mode="lines", name="FFT"))
    fig_c2.update_layout(height=300, title="Spectre FFT", xaxis_title="Hz",
                         yaxis_title="amplitude", yaxis_type="log")
    st.plotly_chart(fig_c2, use_container_width=True)
    st.caption(f"{len(peaks_c)} pics détectés. Raie dominante : "
               f"{freqs_c[int(np.argmax(mag_c))]:.1f} Hz")
    if st.button("Générer PDF"):
        out = Path(tempfile.mkdtemp()) / f"{Path(tdms_path).stem}.pdf"
        build_pdf(out, {"source": Path(tdms_path).name, "lignes": len(df_csv),
                        "sampling_rate": fs_c},
                  Path(tdms_path).stem, {"unit_string": ""}, fs_c,
                  x_all[::step_c], y_filt_c[::step_c], peaks_c, freqs_c, mag_c,
                  note=f"CSV : filtre {fkind_c} {cutoff_c}Hz, {len(peaks_c)} pics.")
        st.download_button("Télécharger PDF", out.read_bytes(),
                           out.name, "application/pdf")
        st.success("PDF prêt.")
    st.stop()

struct = get_structure(tdms_path)
st.subheader("Fichier")
st.json(struct["file_properties"])

groups = list(struct["groups"].keys())
group = st.sidebar.selectbox("Groupe", groups)
channels = list(struct["groups"][group]["channels"].keys())
selected = st.sidebar.multiselect("Canaux", channels, default=channels[:2])

rows = [{"canal": n, "points": i["length"], "dtype": i["dtype"], "unité": i["unit"]}
        for n, i in struct["groups"][group]["channels"].items()]
st.subheader(f"Groupe {group} — {len(channels)} canaux")
st.dataframe(pd.DataFrame(rows), use_container_width=True)

# --- visualisation ---
fig = go.Figure()
cache = {}
for ch_name in selected:
    d = read_channel_decimated(tdms_path, group, ch_name, max_points=max_points)
    cache[ch_name] = d
    fig.add_trace(go.Scatter(x=d["x"], y=d["y"], mode="lines", name=ch_name))
    st.caption(f"{ch_name} : {d['full_length']} pts, décimation ×{d['decimation_factor']}, unité {d['unit']}")
fig.update_layout(xaxis_title="temps (s) ou index", yaxis_title="valeur",
                  legend_title="canaux", height=450)
fig.update_xaxes(rangeslider_visible=True)
st.plotly_chart(fig, use_container_width=True)

# --- analyse : FFT / filtre / pics ---
st.header("Analyse (V2)")
ana_ch = st.selectbox("Canal analysé", channels,
                      index=channels.index(selected[0]) if selected else 0)
d = cache.get(ana_ch) or read_channel_decimated(tdms_path, group, ana_ch, max_points=max_points)
props = d["properties"]
fs_default = get_fs(props, 1000.0)
fs = st.number_input("Fréquence d'échantillonnage (Hz)", value=float(fs_default), min_value=1.0)
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
    fs_ana, dec_note = fs, "pleine résolution"
else:
    y_ana, x_ana = d["y"], d["x"]
    fs_ana = fs / max(1, d["decimation_factor"])
    dec_note = f"décimé ×{d['decimation_factor']} (fs eff. {fs_ana:.1f} Hz)"
st.caption(f"Analyse : {dec_note}")
col1, col2, col3 = st.columns(3)
with col1:
    fkind = st.selectbox("Filtre", ["none", "lowpass", "highpass"], index=0)
with col2:
    cutoff = st.number_input("Cutoff (Hz)", value=100.0, min_value=0.0)
with col3:
    order = st.slider("Ordre", 2, 8, 4)
prom = st.slider("Prominence pics", 0.0, 5.0, 0.5, 0.1)
dist = st.slider("Distance min pics (pts)", 1, 2000, 100)

y_filt = apply_filter(y_ana, fs_ana, fkind, cutoff, order)
peaks = detect_peaks(y_filt, prominence=prom, distance=dist)
freqs, mag = compute_fft(y_filt, fs_ana)

fig2 = go.Figure()
fig2.add_trace(go.Scatter(x=x_ana, y=y_filt, mode="lines", name=f"{ana_ch} filtré"))
if len(peaks):
    fig2.add_trace(go.Scatter(x=x_ana[peaks], y=y_filt[peaks],
                             mode="markers", name=f"{len(peaks)} pics",
                             marker={"color": "red", "size": 7}))
fig2.update_layout(height=350, title="Signal + pics")
st.plotly_chart(fig2, use_container_width=True)

fig3 = go.Figure()
fig3.add_trace(go.Scatter(x=freqs, y=mag, mode="lines", name="FFT"))
fig3.update_layout(height=300, title="Spectre FFT", xaxis_title="Hz",
                   yaxis_title="amplitude", yaxis_type="log")
st.plotly_chart(fig3, use_container_width=True)
st.caption(f"{len(peaks)} pics détectés. Raie dominante : {freqs[int(np.argmax(mag))]:.1f} Hz")

# --- exports ---
st.header("Exports")
exp_channel = st.selectbox("Canal à exporter", channels, key="exp")
c1, c2 = st.columns(2)
with c1:
    if st.button("Préparer CSV"):
        df = channel_to_dataframe(tdms_path, group, exp_channel)
        st.download_button("Télécharger CSV", df.to_csv(index=False).encode(),
                           f"{group}_{exp_channel}.csv", "text/csv")
with c2:
    if st.button("Générer PDF"):
        out = Path(tempfile.mkdtemp()) / f"{group}_{ana_ch}.pdf"
        fp = dict(struct["file_properties"])
        try:
            fp["taille_fichier"] = Path(tdms_path).stat().st_size
        except Exception:
            pass
        fp["echantillons"] = n_full
        build_pdf(out, fp, f"{group}/{ana_ch}",
                  d["properties"], fs_ana, x_ana, y_filt, peaks, freqs, mag,
                  note=f"Filtre {fkind} {cutoff}Hz, {len(peaks)} pics.")
        st.download_button("Télécharger PDF", out.read_bytes(),
                           out.name, "application/pdf")
        st.success("PDF prêt.")
