"""Export PDF : metadonnees + courbe temporelle + spectre (ASCII-safe ReportLab)."""
import tempfile
from pathlib import Path
from xml.sax.saxutils import escape
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors


LABELS = {
    "author": "Auteur",
    "description": "Description",
    "sampling_rate": "Frequence (Hz)",
    "sensor": "Capteur",
    "unit_string": "Unite",
    "unit": "Unite",
    "wf_increment": "Pas (s)",
    "wf_start_time": "Debut",
    "taille_fichier": "Taille fichier",
    "echantillons": "Echantillons",
}


def pretty_value(k: str, v) -> str:
    if k == "sampling_rate":
        try:
            return f"{float(v):.1f} Hz"
        except Exception:
            pass
    if k == "wf_increment":
        try:
            dt = float(v)
            return f"{dt} s (={1.0/dt:.1f} Hz)"
        except Exception:
            pass
    if k == "taille_fichier":
        try:
            return f"{float(v)/1e6:.0f} Mo"
        except Exception:
            pass
    if k == "echantillons":
        try:
            return f"{int(v):,}".replace(",", " ")
        except Exception:
            pass
    return str(v)


def clean(v, maxlen: int = 100) -> str:
    """Texte ASCII-safe + echappe XML pour ReportLab Paragraph (Helvetica WinAnsi)."""
    s = str(v).replace("\n", " ").replace("\r", " ")
    repl = {"—": "-", "–": "-", "≈": "=", "→": "->", "←": "<-",
            "µ": "u", "²": "^2", "³": "^3", "°": "deg", "…": "..."}
    for a, b in repl.items():
        s = s.replace(a, b)
    s = "".join(c if ord(c) < 128 or c in "éèêàâîôûçÉÈÀÙ" else "?" for c in s)
    if len(s) > maxlen:
        s = s[:maxlen] + "..."
    return escape(s)


def _save_time_plot(x, y, peaks, title, out: Path):
    fig, ax = plt.subplots(figsize=(8, 3))
    ax.plot(x, y, linewidth=0.6)
    if len(peaks):
        peaks = np.asarray(peaks)
        peaks = peaks[peaks < len(x)]
        ax.plot(np.asarray(x)[peaks], np.asarray(y)[peaks], "ro", markersize=3)
    ax.set_title(str(title)[:80])
    ax.set_xlabel("temps (s) / index")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


def _save_spec_plot(freqs, mag, out: Path):
    fig, ax = plt.subplots(figsize=(8, 2.6))
    ax.semilogy(np.asarray(freqs), np.asarray(mag) + 1e-12, linewidth=0.8)
    ax.set_title("Spectre FFT (amplitude)")
    ax.set_xlabel("Hz")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


def build_pdf(output: str | Path, file_props: dict, channel_label: str,
              channel_props: dict, fs: float, x, y, peaks,
              freqs, mag, note: str = "") -> Path:
    output = Path(output)
    tmpdir = Path(tempfile.mkdtemp())
    t_png = tmpdir / "time.png"
    s_png = tmpdir / "spec.png"
    _save_time_plot(np.asarray(x), np.asarray(y), np.asarray(peaks), channel_label, t_png)
    _save_spec_plot(np.asarray(freqs), np.asarray(mag), s_png)

    doc = SimpleDocTemplate(str(output), pagesize=A4,
                            leftMargin=15 * mm, rightMargin=15 * mm)
    styles = getSampleStyleSheet()
    cell_style = ParagraphStyle("cell", parent=styles["Normal"], fontSize=8, leading=10)

    story = [Paragraph("TDMS Viewer - Rapport", styles["Title"]),
             Spacer(1, 6),
             Paragraph(f"Canal : {clean(channel_label)} - fs = {float(fs):.1f} Hz - "
                       f"{len(np.asarray(y))} pts affiches", styles["Normal"]),
             Spacer(1, 6)]
    if note:
        story += [Paragraph(clean(note, 300), styles["Normal"]), Spacer(1, 6)]

    def row(k, v):
        return [Paragraph(clean(LABELS.get(k, k), 40), cell_style),
                Paragraph(clean(pretty_value(k, v), 90), cell_style)]

    rows = [[Paragraph("<b>cle</b>", cell_style), Paragraph("<b>valeur</b>", cell_style)]]
    rows.append([Paragraph("== fichier ==", cell_style), Paragraph("", cell_style)])
    for k, v in list(file_props.items())[:14]:
        rows.append(row(k, v))
    rows.append([Paragraph("== canal ==", cell_style), Paragraph("", cell_style)])
    for k, v in list(channel_props.items())[:14]:
        rows.append(row(k, v))
    t = Table(rows, colWidths=[55 * mm, 120 * mm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                           ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                           ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story += [t, Spacer(1, 8),
              Image(str(t_png), width=170 * mm, height=64 * mm), Spacer(1, 6),
              Image(str(s_png), width=170 * mm, height=55 * mm)]
    doc.build(story)
    return output
