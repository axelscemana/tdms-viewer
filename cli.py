"""Point d'entree CLI : tdms-viewer {serve|generate|bench|info}."""
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


if __name__ == "__main__":
    main()
