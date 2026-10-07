"""Bench gros fichier : prouve le streaming (metadata sans charger, decimation, zoom slice, FFT).

Usage :
  python bench_big.py --file data/big_500mo.tdms --group Vibration --channel accel_x
"""
import argparse
import time
from tdms_utils import get_structure, read_channel_decimated, read_channel_slice
from analysis import compute_fft


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--file", default="data/big_500mo.tdms")
    p.add_argument("--group", default="Vibration")
    p.add_argument("--channel", default="accel_x")
    a = p.parse_args()

    t0 = time.perf_counter()
    s = get_structure(a.file)
    n = s["groups"][a.group]["channels"][a.channel]["length"]
    print(f"1) structure (sans charger donnees) : {time.perf_counter()-t0:.2f}s, {n} pts/canal")

    t0 = time.perf_counter()
    d = read_channel_decimated(a.file, a.group, a.channel, max_points=2000)
    print(f"2) courbe affichee : {time.perf_counter()-t0:.2f}s, {len(d['y'])} pts envoyes "
          f"(decimation x{d['decimation_factor']})")

    mid = max(0, n // 2 - 50_000)
    t0 = time.perf_counter()
    z = read_channel_slice(a.file, a.group, a.channel, offset=mid, length=100_000)
    t_slice = time.perf_counter() - t0
    print(f"3) re-fetch zoom 100k pts pleine reso : {t_slice:.2f}s")

    t0 = time.perf_counter()
    f, m = compute_fft(z, 5000.0)
    print(f"4) FFT 100k pts : {time.perf_counter()-t0:.2f}s, raie dom {float(f[int(m.argmax())]):.1f} Hz")
    print("OK : Excel plante >500 Mo, ici on n'a jamais charge le fichier entier.")


if __name__ == "__main__":
    main()
