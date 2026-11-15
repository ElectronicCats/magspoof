"""Agrega una carpeta de pasadas en un CSV por pasada y una tabla resumen.

  python -m maghead.report <carpeta> [--out <dir>] [--l1-snr 12]

Salidas (en --out, por defecto la propia carpeta):
  swipes.csv    una fila por pasada con todas las metricas de metrics.analyze()
  summary.csv   agrupado por variante de cabezal / tramo de velocidad / calza
  summary.md    la misma tabla en Markdown

Columnas del resumen: N, % L1, % L2, % L3 con intervalo de Wilson al 95 %, mediana del
SNR y mediana de la amplitud normalizada (uV*s/m).
"""
from __future__ import annotations

import argparse
import csv
import math
import os
import sys
import numpy as np

from . import metrics, swipefile

SPEED_BINS = [0.0, 0.1, 0.2, 0.4, 0.8, 1.6, float("inf")]   # m/s


def speed_bin(v_m_s: float) -> str:
    if v_m_s is None or not np.isfinite(v_m_s):
        return "desconocida"
    for lo, hi in zip(SPEED_BINS[:-1], SPEED_BINS[1:]):
        if lo <= v_m_s < hi:
            return f"{lo:g}-{hi:g} m/s" if np.isfinite(hi) else f">={lo:g} m/s"
    return "desconocida"


def swipe_speed(row: dict) -> float:
    """Velocidad para agrupar: barreras > periodo de bit > nominal."""
    for k, sc in (("speed_gates_mm_s", 1e-3), ("speed_bits_mm_s", 1e-3), ("nominal_speed_m_s", 1.0)):
        v = row.get(k)
        if v is not None and isinstance(v, (int, float)) and np.isfinite(v) and v > 0:
            return float(v) * sc
    return float("nan")


def analyze_folder(folder: str, l1_snr_db: float = metrics.L1_SNR_DB, decoder: str = "auto",
                   verbose: bool = False) -> list[dict]:
    rows = []
    for base in swipefile.list_swipes(folder):
        try:
            sw = swipefile.load(base)
            row = metrics.analyze(sw, l1_snr_db=l1_snr_db, decoder=decoder)
        except Exception as e:                    # una pasada corrupta no para el informe
            print(f"AVISO: {base}: {e}", file=sys.stderr)
            continue
        row["file"] = os.path.relpath(base, folder)
        row["speed_m_s"] = swipe_speed(row)
        row["speed_bin"] = speed_bin(row["speed_m_s"])
        rows.append(row)
        if verbose:
            print(f"{row['file']}: {row['status']} L1={row['L1']} L2={row['L2']} L3={row['L3']}")
    return rows


def summarize(rows: list[dict]) -> list[dict]:
    groups: dict[tuple, list[dict]] = {}
    for r in rows:
        key = (str(r.get("head_variant", "")), r["speed_bin"], r.get("spacing_shim_um"))
        groups.setdefault(key, []).append(r)

    def nmed(vals):
        v = [float(x) for x in vals if x is not None and np.isfinite(float(x))]
        return float(np.median(v)) if v else float("nan")

    def order(k):
        lo = k[1].split("-")[0].replace(">=", "").replace(" m/s", "")
        try:
            lo = float(lo)
        except ValueError:
            lo = 1e9
        return (k[0], lo, -1.0 if k[2] is None else float(k[2]))

    out = []
    for key in sorted(groups, key=order):
        g = groups[key]
        n = len(g)
        s = dict(head_variant=key[0], speed_bin=key[1], spacing_shim_um=key[2], N=n)
        for lv in ("L1", "L2", "L3"):
            k = sum(int(r[lv]) for r in g)
            lo, hi = metrics.wilson(k, n)
            s[f"{lv}_pct"] = 100.0 * k / n
            s[f"{lv}_lo"] = 100.0 * lo
            s[f"{lv}_hi"] = 100.0 * hi
        s["snr_db_median"] = nmed(r["snr_db"] for r in g)
        s["amp_norm_uV_s_per_m_median"] = nmed(r["amp_norm_uV_s_per_m"] for r in g)
        out.append(s)
    return out


def write_csv(path: str, rows: list[dict]) -> None:
    if not rows:
        open(path, "w").close()
        return
    keys = list(rows[0].keys())
    for r in rows:
        keys += [k for k in r if k not in keys]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow({k: (f"{v:.6g}" if isinstance(v, float) else v) for k, v in r.items()})


def summary_markdown(summary: list[dict]) -> str:
    def f(x, fmt="{:.1f}"):
        return "n/d" if x is None or (isinstance(x, float) and not math.isfinite(x)) else fmt.format(x)
    lines = ["| Variante | Velocidad | Calza (um) | N | % L1 senal [IC95] | % L2 transiciones [IC95] | "
             "% L3 decodificacion [IC95] | SNR mediana (dB) | Amp. norm. mediana (uV*s/m) |",
             "|---|---|---|---|---|---|---|---|---|"]
    for s in summary:
        cells = [s["head_variant"], s["speed_bin"], f(s["spacing_shim_um"], "{:g}"), str(s["N"])]
        for lv in ("L1", "L2", "L3"):
            cells.append(f"{s[lv + '_pct']:.0f} [{s[lv + '_lo']:.0f}-{s[lv + '_hi']:.0f}]")
        cells += [f(s["snr_db_median"]), f(s["amp_norm_uV_s_per_m_median"], "{:.0f}")]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Informe agregado de una carpeta de pasadas")
    ap.add_argument("folder")
    ap.add_argument("--out")
    ap.add_argument("--l1-snr", type=float, default=metrics.L1_SNR_DB)
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)
    out = a.out or a.folder
    os.makedirs(out, exist_ok=True)
    rows = analyze_folder(a.folder, a.l1_snr, verbose=a.verbose)
    if not rows:
        print("no se encontraron pasadas (.npz + .json)", file=sys.stderr)
        return 1
    summ = summarize(rows)
    write_csv(os.path.join(out, "swipes.csv"), rows)
    write_csv(os.path.join(out, "summary.csv"), summ)
    md = (f"# Resumen de pasadas\n\nCarpeta: `{a.folder}` - {len(rows)} pasadas - umbral L1: "
          f"SNR > {a.l1_snr:g} dB\n\n"
          "L1 = senal detectada; L2 = 100 % de las transiciones esperadas de la zona de datos, sin "
          "sobrantes; L3 = cadena correcta con paridad y LRC. IC95 = intervalo de Wilson.\n\n"
          + summary_markdown(summ))
    with open(os.path.join(out, "summary.md"), "w", encoding="utf-8") as f:
        f.write(md)
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
