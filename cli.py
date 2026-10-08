"""Point d'entree CLI : tdms-viewer {serve|generate|bench|info|export}."""
import argparse
import json
import subprocess
import sys
from pathlib import Path


def main() -> None:
    p = argparse.ArgumentParser(prog="tdms-viewer")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("serve", help="lance le dashboard")
    s.add_argument("--port", type=int, default=8501)

    g = sub.add_parser("generate", help="genere un .tdms synthetique")
    g.add_argument("--output", default="data/demo.tdms")
    g.add_argument("--duration", type=float, default=10.0)
    g.add_argument("--fs", type=float, default=1000.0)
    g.add_argument("--chunk", type=int, default=100_000)

    b = sub.add_parser("bench", help="bench streaming gros fichier")
    b.add_argument("--file", default="data/big_500mo.tdms")
    b.add_argument("--group", default="Vibration")
    b.add_argument("--channel", default="accel_x")

    i = sub.add_parser("info", help="affiche groupes/canaux d'un .tdms")
    i.add_argument("file")

    e = sub.add_parser("export", help="exporte .tdms -> CSV (fichier ou dossier)")
    e.add_argument("--input", required=True,
                   help="fichier .tdms ou dossier contenant des .tdms")
    e.add_argument("--out", default="exports",
                   help="dossier de sortie (defaut: exports/)")
    e.add_argument("--chunk", type=int, default=100_000,
                   help="taille bloc streaming (defaut: 100000)")
    e.add_argument("--recursive", action="store_true",
                   help="scanne les sous-dossiers")
    e.add_argument("--group", default=None, help="ne garde que ce groupe")
    e.add_argument("--channel", default=None, help="ne garde que ce canal")
    e.add_argument("--split", type=int, default=None, metavar="LIGNES",
                   help="découpe aussi en morceaux _partN.csv de LIGNES max "
                        "(ex. 500000, compatible Excel limité à 1048576 lignes)")
    e.add_argument("--format", choices=["csv", "xlsx"], default="csv",
                   help="csv : un fichier par canal (+ morceaux si --split). "
                        "xlsx : un classeur par .tdms (onglets par canal + Infos)")

    a = p.parse_args()
    if a.cmd == "serve":
        subprocess.run([sys.executable, "-m", "streamlit", "run", "app.py",
                        "--server.port", str(a.port)], check=True)
    elif a.cmd == "generate":
        from generate_test_tdms import write_tdms
        write_tdms(Path(a.output), a.duration, a.fs, a.chunk)
    elif a.cmd == "bench":
        from tdms_utils import get_structure, read_channel_decimated, read_channel_slice
        import time
        t0 = time.perf_counter()
        s = get_structure(a.file)
        n = s["groups"][a.group]["channels"][a.channel]["length"]
        print(f"structure : {time.perf_counter()-t0:.2f}s, {n} pts/canal")
        t0 = time.perf_counter()
        d = read_channel_decimated(a.file, a.group, a.channel)
        print(f"courbe : {time.perf_counter()-t0:.2f}s, x{d['decimation_factor']}")
        z = read_channel_slice(a.file, a.group, a.channel, n // 2, 100_000)
        print(f"zoom 100k : {len(z)} pts ok")
    elif a.cmd == "info":
        from tdms_utils import get_structure
        print(json.dumps(get_structure(a.file), default=str, indent=1)[:2000])
    elif a.cmd == "export":
        from tdms_utils import export_batch
        manifests = export_batch(a.input, a.out, recursive=a.recursive,
                                 chunk_size=a.chunk,
                                 only_group=a.group,
                                 only_channel=a.channel,
                                 split_rows=a.split,
                                 out_format=a.format)
        if a.format == "xlsx":
            total_wb = len(manifests)
            total_rows = sum(e["rows"] for m in manifests for e in m["exported"])
            print(f"OK {len(manifests)} fichier(s) .tdms -> "
                  f"{total_wb} classeur(s) XLSX, {total_rows} lignes dans {a.out}/")
            for m in manifests:
                print(f" - {m['source']}\n    -> {m['workbook']}")
            return
        total_files = sum(len(m["exported"]) for m in manifests)
        total_rows = sum(e["rows"] for m in manifests for e in m["exported"])
        total_parts = sum(len(e.get("parts", [])) for m in manifests for e in m["exported"])
        print(f"OK {len(manifests)} fichier(s) .tdms -> "
              f"{total_files} CSV complets"
              f"{f' + {total_parts} morceaux Excel' if total_parts else ''}, "
              f"{total_rows} lignes au total dans {a.out}/")
        for m in manifests:
            print(f" - {m['source']}")
            for e in m["exported"]:
                scale = (f"scales={','.join(e.get('scale_types', [])) or 'aucun'}"
                         f" unit={e.get('unit', '')}")
                print(f"    -> {e['file']} ({e['rows']} lignes, {scale})")
                for p in e.get("parts", []):
                    print(f"       + {p['file']} ({p['rows']} lignes)")


if __name__ == "__main__":
    main()
