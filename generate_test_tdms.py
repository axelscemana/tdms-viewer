"""Génère des fichiers .tdms synthétiques pour tester sans matériel.

Exemples :
  python generate_test_tdms.py --output data/demo.tdms
  python generate_test_tdms.py --output data/big.tdms --duration 600 --fs 5000 --chunk 100000
"""
import argparse
from pathlib import Path
import numpy as np
from nptdms import TdmsWriter, RootObject, GroupObject, ChannelObject


def gen_vibration(n: int, fs: float, rng: np.random.Generator, start: int = 0) -> dict[str, np.ndarray]:
    t = (start + np.arange(n)) / fs
    base = np.sin(2 * np.pi * 50 * t) + 0.5 * np.sin(2 * np.pi * 120 * t)
    noise = 0.15 * rng.standard_normal(n)
    x = base + noise
    y = np.cos(2 * np.pi * 50 * t) + 0.15 * rng.standard_normal(n)
    z = 0.3 * np.sin(2 * np.pi * 30 * t) + 0.15 * rng.standard_normal(n)
    # pics impulsionnels (défauts / chocs)
    for pos in [int(n * 0.3), int(n * 0.7)]:
        w = min(200, n - pos)
        if w > 0:
            x[pos:pos + w] += 3.0 * np.hanning(w)
    return {"accel_x": x, "accel_y": y, "accel_z": z}


def gen_temperature(n: int, rng: np.random.Generator, start: int = 0) -> np.ndarray:
    drift = 20 + 0.005 * (start + np.arange(n)) / 1000.0
    return drift + 0.2 * rng.standard_normal(n)


def write_tdms(output: Path, duration: float, fs: float, chunk: int, seed: int = 0):
    rng = np.random.default_rng(seed)
    n = int(duration * fs)
    output.parent.mkdir(parents=True, exist_ok=True)
    # supprime un vieux cache d'index qui fausserait la relecture nptdms
    for stale in [Path(str(output) + "_index"), output.with_name(output.name + "_index")]:
        try:
            if stale.exists():
                stale.unlink()
        except OSError:
            pass

    root = RootObject(properties={
        "author": "TDMS Viewer demo generator",
        "description": f"Synthetic: {duration}s @ {fs}Hz, {n} samples/ch",
        "sampling_rate": fs,
    })
    vib_group = GroupObject("Vibration", properties={"description": "Accéléromètres tri-axes"})
    temp_group = GroupObject("Temperature", properties={"description": "Sonde lente"})

    with TdmsWriter(str(output)) as writer:
        writer.write_segment([root, vib_group, temp_group])
        # écriture par blocs -> RAM constante, permet fichiers de plusieurs Go
        for start in range(0, n, chunk):
            stop = min(n, start + chunk)
            size = stop - start
            # on régénère de façon déterministe par bloc (seed dérivé du bloc)
            block_rng = np.random.default_rng(seed + start)
            vib = gen_vibration(size, fs, block_rng, start=start)
            temp = gen_temperature(size, block_rng, start=start)
            # NOTE: pics seulement dans le premier bloc pour rester simple ;
            # le pipeline (FFT/pics) reste validé.
            objs = []
            for name, data in vib.items():
                objs.append(ChannelObject("Vibration", name, data,
                                          properties={"unit_string": "g",
                                                      "sensor": f"ACC-{name[-1].upper()}",
                                                      "wf_increment": 1.0 / fs}))
            objs.append(ChannelObject("Temperature", "temp_pt100", temp,
                                      properties={"unit_string": "degC",
                                                  "sensor": "PT100",
                                                  "wf_increment": 1.0 / fs}))
            writer.write_segment(objs)
    size_mb = output.stat().st_size / 1e6
    print(f"OK {output} : {n} ech/canal, {size_mb:.1f} MB")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", default="data/demo.tdms")
    p.add_argument("--duration", type=float, default=10.0, help="secondes")
    p.add_argument("--fs", type=float, default=1000.0, help="Hz")
    p.add_argument("--chunk", type=int, default=100_000)
    p.add_argument("--seed", type=int, default=0)
    a = p.parse_args()
    write_tdms(Path(a.output), a.duration, a.fs, a.chunk, a.seed)


if __name__ == "__main__":
    main()
