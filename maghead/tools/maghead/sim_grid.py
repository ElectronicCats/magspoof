"""Mapa de exito de decodificacion (L3) frente a SNR y PW50 - SIMULACION.

  python -m maghead.sim_grid [--trials 50] [--out out] [--jobs 4]

Para cada punto (SNR, PW50) y cada pista (1: 210 bpi, 2: 75 bpi) genera pasadas sinteticas
con velocidad aleatoria (log-uniforme 0.1-1.0 m/s), variacion "de mano" de +-30 %, sentido
aleatorio y ruido blanco en la banda del AFE, y las decodifica con el modulo C del firmware
(fw/common/f2f_decode.c, via ctypes). L3 = cadena identica con paridad y LRC correctos.

SNR aqui = pico de un pulso AISLADO a la velocidad media / ruido RMS en la banda completa
del AFE (16 Hz - 40 kHz), en la entrada del ADC. No incluye la perdida de amplitud por
interferencia entre pulsos, que es precisamente el efecto del PW50.

AVISO: es una simulacion del DECODIFICADOR con pulsos lorentzianos ideales; no es una
prediccion del comportamiento de un cabezal real.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import time
import numpy as np

T1 = "%B1234567890123445^MAGHEAD/TEST^99011200000000000000**XXX******?"
T2 = ";1234567890123445=99011200123400000000?"
SNRS = [6, 9, 12, 15, 18, 21, 24, 27, 30, 35, 40]
PW50S = [20, 40, 60, 80, 100, 120, 140, 160, 180, 200]
V_MIN, V_MAX = 0.1, 1.0
LECTURA = ['## Lectura (dentro de los limites de la simulacion)', '', "- El limite por PW50 lo marca la relacion PW50 / celda: el exito cae cuando PW50 se acerca a la celda (los pulsos de '1', separados media celda, se cancelan entre si) y ningun SNR lo arregla por encima de ~1.3 celdas. La pista 1 (celda 121 um) es por tanto la exigente; en la pista 2 toda la rejilla queda por debajo de 0.6 celdas.", '- La columna de PW50 = 20 um necesita MAS SNR que las de 40-60 um: los pulsos estrechos a velocidad alta quedan recortados por el paso bajo de 40 kHz y por el muestreo, y el suavizado del decodificador recupera menos ruido.', '- El SNR necesario depende de la velocidad (el decodificador promedia mas muestras por pulso en las pasadas lentas); la tabla mezcla 0.1-1.0 m/s.', '']


def _point(args):
    track, snr, pw, trials, seed0 = args
    from . import synth, cdecode, decode
    text = T1 if track == 1 else T2
    rng = np.random.default_rng(seed0)
    ok = 0
    for _ in range(trials):
        v = float(math.exp(rng.uniform(math.log(V_MIN), math.log(V_MAX))))
        sw = synth.synthesize(text=text, speed=v, profile="hand", hand_depth=0.30,
                              reverse=bool(rng.integers(2)), snr_db=float(snr), pw50_um=float(pw),
                              gates=False, quiet_ms=20.0, seed=int(rng.integers(1 << 31)))
        r = cdecode.decode(sw.adc, sw.fs, sw.fmt, want_log=False)
        ok += int(r.status == decode.OK and r.text == text)
    return track, snr, pw, ok


def run(trials: int, jobs: int, seed: int = 12345):
    from concurrent.futures import ProcessPoolExecutor
    from . import cdecode
    cdecode.build()
    tasks = []
    ss = np.random.SeedSequence(seed)
    for track in (1, 2):
        for snr in SNRS:
            for pw in PW50S:
                tasks.append((track, snr, pw, trials, ss.spawn(1)[0]))
    res = {1: np.zeros((len(SNRS), len(PW50S)), int), 2: np.zeros((len(SNRS), len(PW50S)), int)}
    with ProcessPoolExecutor(jobs) as ex:
        for track, snr, pw, ok in ex.map(_point, tasks, chunksize=4):
            res[track][SNRS.index(snr), PW50S.index(pw)] = ok
    return res


def min_snr(col: np.ndarray, trials: int, level: float):
    """SNR minima de la rejilla a partir de la cual el exito es >= level en todos los puntos."""
    best = None
    for i in range(len(SNRS) - 1, -1, -1):
        if col[i] / trials >= level:
            best = SNRS[i]
        else:
            break
    return best


def plot(res, trials: int, path: str):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 6.2), constrained_layout=True)
    names = {1: "Pista 1 - 210 bpi (celda 121 um), 7 bits/car.",
             2: "Pista 2 - 75 bpi (celda 339 um), 5 bits/car."}
    for ax, track in zip(axes, (1, 2)):
        pct = 100.0 * res[track] / trials
        im = ax.imshow(pct, origin="lower", aspect="auto", cmap="Blues", vmin=0, vmax=100)
        ax.set_xticks(range(len(PW50S)), [str(p) for p in PW50S])
        ax.set_yticks(range(len(SNRS)), [str(s) for s in SNRS])
        ax.set_xlabel("PW50 del pulso aislado (um)")
        ax.set_ylabel("SNR: pico aislado / ruido RMS en banda (dB)")
        ax.set_title(names[track], fontsize=11, loc="left")
        for i in range(len(SNRS)):
            for j in range(len(PW50S)):
                ax.text(j, i, f"{pct[i, j]:.0f}", ha="center", va="center", fontsize=8,
                        color="white" if pct[i, j] > 55 else "#1a1a1a")
        ax.set_xticks(np.arange(-.5, len(PW50S)), minor=True)
        ax.set_yticks(np.arange(-.5, len(SNRS)), minor=True)
        ax.grid(which="minor", color="white", linewidth=1.5)
        ax.tick_params(which="both", length=0)
        for sp in ax.spines.values():
            sp.set_visible(False)
    cb = fig.colorbar(im, ax=axes, shrink=0.85, pad=0.01)
    cb.set_label("Decodificacion completa correcta, L3 (% de pasadas)")
    cb.outline.set_visible(False)
    fig.suptitle(f"SIMULACION del decodificador con pulsos lorentzianos ideales (no predice un cabezal real) - "
                 f"{trials} pasadas por punto, 0.1-1.0 m/s, mano +-30 %, ambos sentidos", fontsize=10)
    fig.savefig(path, dpi=130)
    plt.close(fig)


def markdown(res, trials: int, elapsed: float) -> str:
    from . import metrics
    lo0, hi0 = metrics.wilson(trials, trials)
    out = ["# Exito de decodificacion (L3) frente a SNR y PW50 - simulacion", "",
           "**Esto es una simulacion del decodificador sobre pulsos idealizados (lorentzianos, ruido "
           "blanco gaussiano, sin saltos de amplitud, sin diafonia entre pistas, sin azimut); NO es una "
           "prediccion del comportamiento de un cabezal real.** Sirve para saber que PW50 y que SNR "
           "necesita el decodificador, no si un cabezal dado los alcanza.", "",
           f"- Decodificador: modulo C del firmware (`fw/common/f2f_decode.c`), configuracion por defecto, "
           f"{len(PW50S) * len(SNRS) * 2} puntos x {trials} pasadas = {len(PW50S) * len(SNRS) * 2 * trials} "
           f"pasadas ({elapsed:.0f} s).",
           "- Cada pasada: velocidad media log-uniforme 0.1-1.0 m/s, variacion de mano +-30 %, sentido "
           "aleatorio, 250 kS/s, AFE 16 Hz - 40 kHz, ADC de 12 bits.",
           "- **SNR** = pico de un pulso AISLADO a la velocidad media / ruido RMS en toda la banda del AFE "
           "(dB). No descuenta la perdida de amplitud por interferencia entre pulsos (eso es el eje PW50).",
           "- **PW50** = anchura a media altura del pulso aislado, en um sobre la tarjeta.",
           "- L3 = cadena identica a la esperada, con paridad y LRC correctos.",
           f"- Con {trials} pasadas por punto, {trials}/{trials} equivale a un intervalo de Wilson al 95 % de "
           f"[{100 * lo0:.0f}, 100] %; las diferencias de pocos puntos entre celdas vecinas no son significativas.",
           "", "![mapa](decode_vs_snr_pw50.png)", ""] + LECTURA
    for track, name, cell in ((1, "Pista 1 (210 bpi)", 25400 / 210), (2, "Pista 2 (75 bpi)", 25400 / 75)):
        out += [f"## {name} - celda {cell:.0f} um, media celda {cell / 2:.0f} um", "",
                "Porcentaje de pasadas con L3:", "",
                "| SNR (dB) \\ PW50 (um) | " + " | ".join(str(p) for p in PW50S) + " |",
                "|---|" + "---|" * len(PW50S)]
        for i in range(len(SNRS) - 1, -1, -1):
            out.append(f"| {SNRS[i]} | " + " | ".join(f"{100 * res[track][i, j] / trials:.0f}"
                                                     for j in range(len(PW50S))) + " |")
        out += ["", "SNR minima de la rejilla a partir de la cual el exito se mantiene por encima del nivel "
                "indicado (\"-\" = no se alcanza ni a 40 dB):", "",
                "| PW50 (um) | PW50 / celda | SNR min. para >= 95 % | SNR min. para >= 50 % |", "|---|---|---|---|"]
        for j, pw in enumerate(PW50S):
            a = min_snr(res[track][:, j], trials, 0.95)
            b = min_snr(res[track][:, j], trials, 0.50)
            out.append(f"| {pw} | {pw / cell:.2f} | {a if a is not None else '-'} | {b if b is not None else '-'} |")
        out.append("")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Mapa L3 vs SNR/PW50 (simulacion)")
    ap.add_argument("--trials", type=int, default=50)
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 1)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "..", "out"))
    ap.add_argument("--seed", type=int, default=12345)
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    t0 = time.time()
    res = run(a.trials, a.jobs, a.seed)
    el = time.time() - t0
    plot(res, a.trials, os.path.join(a.out, "decode_vs_snr_pw50.png"))
    md = markdown(res, a.trials, el)
    with open(os.path.join(a.out, "decode_vs_snr_pw50.md"), "w", encoding="utf-8") as f:
        f.write(md)
    with open(os.path.join(a.out, "decode_vs_snr_pw50.json"), "w", encoding="utf-8") as f:
        json.dump({"trials": a.trials, "seed": a.seed, "snr_db": SNRS, "pw50_um": PW50S,
                   "speed_m_s": [V_MIN, V_MAX], "ok_track1": res[1].tolist(),
                   "ok_track2": res[2].tolist()}, f)
    print(md)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
