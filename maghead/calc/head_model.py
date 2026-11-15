#!/usr/bin/env python3
"""
Modelo de primer orden del cabezal lector experimental (MagHead).

Que es cada cosa:
  * Tabla ISO (densidad, longitudes de onda, frecuencias): HECHO (aritmetica sobre 210/75 bpi).
  * Funcion de sensibilidad h_x(x,y): SIMULACION 2D ideal (polos equipotenciales, mu->inf,
    sin efectos 3D ni de borde de pista). Resuelve Laplace por diferencias finitas.
  * Formas de onda F2F: reciprocidad + medio con transiciones arctan (parametros a, delta ASUMIDOS).
  * Amplitud absoluta: ESTIMACION; depende de Mr*delta del medio (NO verificado, se barre).
  * Red de reluctancias (eficiencia): ESTIMACION 1D; mu_r de la cinta tras cortar/doblar NO verificado.

Uso: python3 head_model.py   -> escribe out/*.png y out/results.json
"""
import json, os
import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spl
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
MU0 = 4e-7 * np.pi
UM = 1e-6
res = {}

# ---------------------------------------------------------------- 1. ISO 7811
tracks = {"T1": dict(bpi=210, bits=7, chars=79), "T2": dict(bpi=75, bits=5, chars=40),
          "T3": dict(bpi=210, bits=5, chars=107)}
speeds = [0.05, 0.10, 0.25, 0.50, 1.00, 1.50, 2.54]          # m/s (2.54 m/s = 100 ips, tope AN5094)
iso = {}
for k, t in tracks.items():
    cell = 25.4e-3 / t["bpi"]
    iso[k] = dict(bit_cell_um=cell / UM, min_transition_um=cell / 2 / UM,
                  lambda_ones_um=cell / UM, lambda_zeros_um=2 * cell / UM,
                  data_len_mm=t["chars"] * t["bits"] * cell * 1e3,
                  f_zeros_Hz={f"{v:g}": v / (2 * cell) for v in speeds},
                  f_ones_Hz={f"{v:g}": v / cell for v in speeds})
res["iso"] = iso

# ---------------------------------------------------------------- 2. Sensibilidad 2D
def solve_head(kind, g=25.0, t=20.0, s=25.0, lov=200.0, h=2.5, X=900.0, Yup=400.0, Ydn=400.0):
    """Potencial escalar magnetico. Unidades um. Devuelve x, y(>0), hx(y,x) por unidad de FMM [1/um].
    kind='butt'    : dos laminas coplanares (espesor t) separadas g  (entrehierro a tope / ranura)
    kind='overlap' : lamina superior termina en x=0; lamina inferior, separada s por debajo,
                     empieza en x=-lov y sigue a +inf (entrehierro = espesor del separador)"""
    xs = np.arange(-X, X + h / 2, h); ys = np.arange(-Ydn, Yup + h / 2, h)
    nx, ny = len(xs), len(ys)
    XX, YY = np.meshgrid(xs, ys)
    fixed = np.zeros((ny, nx), bool); val = np.zeros((ny, nx))
    if kind == "butt":
        m1 = (YY <= 0) & (YY >= -t) & (XX <= -g / 2); m2 = (YY <= 0) & (YY >= -t) & (XX >= g / 2)
    else:
        m1 = (YY <= 0) & (YY >= -t) & (XX <= 0)
        m2 = (YY <= -t - s) & (YY >= -2 * t - s) & (XX >= -lov)
    fixed |= m1 | m2; val[m1] = 0.5; val[m2] = -0.5
    idx = np.arange(nx * ny).reshape(ny, nx)
    rows, cols, dat = [], [], []
    b = np.zeros(nx * ny)
    def add(r, c, v): rows.append(r); cols.append(c); dat.append(v)
    # Laplaciano 5 puntos con Neumann (espejo) en el contorno exterior
    main = np.full((ny, nx), 4.0)
    A = sp.lil_matrix((nx * ny, nx * ny))
    I = idx.ravel()
    for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        jj = np.clip(np.arange(ny)[:, None] + dy, 0, ny - 1) * np.ones((1, nx), int)
        ii = np.clip(np.arange(nx)[None, :] + dx, 0, nx - 1) * np.ones((ny, 1), int)
        # reflejo: si sale del dominio usa el vecino opuesto
        jo = np.arange(ny)[:, None] + dy; io = np.arange(nx)[None, :] + dx
        jj = np.where((jo < 0) | (jo >= ny), np.arange(ny)[:, None] - dy, jo) * np.ones((1, nx), int)
        ii = np.where((io < 0) | (io >= nx), np.arange(nx)[None, :] - dx, io) * np.ones((ny, 1), int)
        rows.append(I); cols.append(idx[jj, ii].ravel()); dat.append(np.full(nx * ny, -1.0))
    rows.append(I); cols.append(I); dat.append(np.full(nx * ny, 4.0))
    A = sp.csr_matrix((np.concatenate(dat), (np.concatenate(rows), np.concatenate(cols))), shape=(nx * ny,) * 2)
    f = fixed.ravel()
    free = np.where(~f)[0]; fx = np.where(f)[0]
    phi = np.zeros(nx * ny); phi[fx] = val.ravel()[fx]
    rhs = -A[free][:, fx] @ phi[fx]
    phi[free] = spl.spsolve(A[free][:, free].tocsc(), rhs)
    phi = phi.reshape(ny, nx)
    hx = -np.gradient(phi, h, axis=1)
    up = ys > 0
    return xs, ys[up], hx[up]

def karlqvist(x, y, g):
    return (np.arctan((g / 2 + x) / y) + np.arctan((g / 2 - x) / y)) / (np.pi * g)

def wire_hx(x, y, w, tc, n=9):
    """Conductor rectangular (pista PCB) ancho w, espesor tc, cara superior en y=0. Por amperio [1/um]."""
    out = np.zeros(np.broadcast(x, y).shape)
    for xo in (np.arange(n) + 0.5) / n * w - w / 2:
        for yo in -(np.arange(4) + 0.5) / 4 * tc:
            out += (y - yo) / ((x - xo) ** 2 + (y - yo) ** 2)
    return out / (2 * np.pi) / (n * 4)

# ---------------------------------------------------------------- 3. Lectura F2F por reciprocidad
def f2f_transitions(bits, cell):
    """posiciones (um) y signo de las transiciones de flujo para una secuencia de bits F2F"""
    pos, x = [], 0.0
    for bta in bits:
        pos.append(x)
        if bta: pos.append(x + cell / 2)
        x += cell
    pos.append(x)
    return np.array(pos)

def readback(xs, ys, hx, pos, d, delta, a, dx=1.0):
    """e(x) normalizada = sum_k (-1)^k * G(x - x_k), G = integral en el espesor del medio de
    h_x convolucionada con la derivada de la transicion arctan (lorentziana de parametro a).
    Devuelve x_cabezal y la FEM por unidad de (mu0*Mr*W*v*N*eta): unidades um/um -> adimensional."""
    sel = (ys >= d) & (ys <= d + delta)
    if not sel.any(): sel = np.argmin(abs(ys - d))[None]
    hbar = hx[sel].sum(axis=0) * (ys[1] - ys[0])           # integral dy  [adimensional]
    xf = np.arange(xs[0], xs[-1], dx)
    hbar = np.interp(xf, xs, hbar)
    lor = (2 / np.pi) * a / (xf ** 2 + a ** 2)             # d/dx de (2/pi)atan(x/a): salto total 2 (de -Mr a +Mr)
    G = np.convolve(hbar, lor, mode="same") * dx           # respuesta a transicion aislada
    xh = np.arange(pos[0] - 300, pos[-1] + 300, dx)
    e = np.zeros_like(xh)
    for k, p in enumerate(pos):
        e += (-1) ** k * np.interp(xh - p, xf, G, left=0, right=0)
    return xh, e, G, xf

rng = np.random.default_rng(1)
geoms = {
    "butt g=12.5": dict(kind="butt", g=12.5, t=20),
    "butt g=25":   dict(kind="butt", g=25.0, t=20),
    "butt g=50":   dict(kind="butt", g=50.0, t=20),
    "overlap s=12.5 t=20": dict(kind="overlap", s=12.5, t=20),
    "overlap s=25 t=20":   dict(kind="overlap", s=25.0, t=20),
}
fields = {k: solve_head(**v) for k, v in geoms.items()}
# verificacion del solver contra Karlqvist (g=25, y=20 um)
xs, ys, hx = fields["butt g=25"]
iy = np.argmin(abs(ys - 20)); kq = karlqvist(xs, ys[iy], 25.0)
res["solver_check_peak_ratio_FD_vs_Karlqvist_y20um"] = float(hx[iy].max() / kq.max())

DELTA, A_TR = 10.0, 8.0     # um  ASUMIDOS (espesor de capa magnetica y parametro de transicion)
cells = {"T1": 25400 / 210, "T2": 25400 / 75}
spacings = [5, 12.5, 25, 37.5, 50, 75, 100]
table = {}
for name, (xs, ys, hx) in fields.items():
    table[name] = {}
    for trk, cell in cells.items():
        row = {}
        for d in spacings:
            amp = {}
            for lab, bits in (("zeros", [0] * 16), ("ones", [1] * 16)):
                xh, e, G, xf = readback(xs, ys, hx, f2f_transitions(bits, cell), d, DELTA, A_TR)
                mid = (xh > 4 * cell) & (xh < 12 * cell)
                amp[lab] = float(np.ptp(e[mid]) / 2)
            half = G >= G.max() / 2
            row[str(d)] = dict(iso_peak=float(G.max()), pw50_um=float(half.sum() * (xf[1] - xf[0])),
                               zeros=amp["zeros"], ones=amp["ones"],
                               resolution=amp["ones"] / amp["zeros"])
        table[name][trk] = row
# pista PCB al aire (por amperio => equivale a N*eta = 1 en la misma formula)
air = {}
for wname, (w, tc, extra) in {"pista 100um, sin mascara": (100, 35, 0), "pista 100um, con mascara 25um": (100, 35, 25),
                              "pista 200um, sin mascara": (200, 35, 0)}.items():
    xs_a = np.arange(-900, 900.5, 2.5); ys_a = np.arange(2.5, 400, 2.5)
    XXa, YYa = np.meshgrid(xs_a, ys_a); hxa = wire_hx(XXa, YYa, w, tc)
    air[wname] = {}
    for trk, cell in cells.items():
        row = {}
        for d in (5, 12.5, 25):
            amp = {}
            for lab, bits in (("zeros", [0] * 16), ("ones", [1] * 16)):
                xh, e, G, xf = readback(xs_a, ys_a, hxa, f2f_transitions(bits, cell), d + extra, DELTA, A_TR)
                mid = (xh > 4 * cell) & (xh < 12 * cell); amp[lab] = float(np.ptp(e[mid]) / 2)
            row[str(d)] = dict(iso_peak=float(G.max()), zeros=amp["zeros"], ones=amp["ones"],
                               resolution=amp["ones"] / amp["zeros"])
        air[wname][trk] = row
res["assumed_medium"] = dict(delta_um=DELTA, a_um=A_TR)
res["readback_norm"] = table
res["air_trace_norm"] = air

# ---------------------------------------------------------------- 4. Reluctancias / eficiencia
def eff(Wp=1.5e-3, tf=18e-6, mur=1e4, path=28e-3, gap="butt", g=25e-6, lov=0.3e-3, backgap=0.0, Abg=6e-6, Lpole=6e-3):
    Rcore = path / (MU0 * mur * Wp * tf)
    if gap == "butt":
        Rg = g / (MU0 * Wp * tf)
        Pfr = MU0 * Wp * (2 / np.pi) * np.log(max(2 * Lpole / g, 2))      # franja entre laminas coplanares (ambas caras)
        Rgap = 1 / (1 / Rg + Pfr)
    else:
        Rgap = 1 / (MU0 * Wp * lov / g + MU0 * Wp * (1 / np.pi) * np.log(max(2 * Lpole / g, 2)))
    Rbg = 2 * backgap / (MU0 * Abg) if backgap else 0.0
    return Rgap / (Rgap + Rcore + Rbg), Rgap, Rcore, Rbg
effs = {}
for mur in (1e3, 1e4, 8e4):
    effs[f"butt g=25um, cinta enhebrada, mur={mur:g}"] = eff(mur=mur)[0]
    effs[f"butt g=25um, back-gap FR4 0.8mm (area 6mm2), mur={mur:g}"] = eff(mur=mur, backgap=0.8e-3)[0]
    for lov in (0.1e-3, 0.3e-3, 1e-3):
        effs[f"overlap s=25um, solape {lov*1e3:g}mm, enhebrada, mur={mur:g}"] = eff(mur=mur, gap="overlap", lov=lov)[0]
res["efficiency"] = effs
_, Rgap, Rcore, _ = eff(mur=1e4)
N = 72
res["inductance_uH_core_only_N72_mur1e4"] = N ** 2 / (Rgap + Rcore) * 1e6

# ---------------------------------------------------------------- 5. Amplitud absoluta (estimacion)
def vpk(norm, v, W, N_eta, Mr):       # norm adimensional de readback()
    return MU0 * Mr * W * v * N_eta * norm
est = {}
norm_h = table["butt g=25"]["T1"]["25"]; norm_h2 = table["butt g=25"]["T2"]["25"]
norm_a = air["pista 100um, sin mascara"]["T2"]["12.5"]
for Mr in (40e3, 80e3, 120e3):        # A/m  barrido: NO verificado
    for v in (0.05, 0.19, 1.0):
        est[f"hibrido N=72 eta=0.4, T1 unos, d=25um, Mr={Mr/1e3:g}kA/m, v={v}"] = vpk(norm_h["ones"], v, 1.5e-3, 72 * 0.4, Mr)
        est[f"hibrido N=72 eta=0.4, T2 ceros, d=25um, Mr={Mr/1e3:g}kA/m, v={v}"] = vpk(norm_h2["zeros"], v, 1.5e-3, 72 * 0.4, Mr)
        est[f"pista al aire 1 conductor, T2 ceros, d=12.5um, Mr={Mr/1e3:g}kA/m, v={v}"] = vpk(norm_a["zeros"], v, 3e-3, 1.0, Mr)
res["vpeak_estimates_V"] = est
# Cabezal comercial TG142 (19 mVpp @210bpi, 7.5 ips, g=30um, W=1.4mm): N*eta implicito para cada Mr supuesto
xs, ys, hx = solve_head("butt", g=30.0, t=200.0)
xh, e, G, xf = readback(xs, ys, hx, f2f_transitions([0] * 16, cells["T1"]), 10, DELTA, A_TR)
normTG = np.ptp(e[(xh > 500) & (xh < 1400)]) / 2
res["TG142_backcalc_N_eta"] = {f"Mr={Mr/1e3:g}kA/m": 9.5e-3 / (MU0 * Mr * 1.4e-3 * 0.1905 * normTG) for Mr in (40e3, 80e3, 120e3)}

# ---------------------------------------------------------------- figuras
fig, ax = plt.subplots(1, 2, figsize=(11, 4))
for name, (xs, ys, hx) in fields.items():
    iy = np.argmin(abs(ys - 20)); ax[0].plot(xs, hx[iy] * 1e3, label=name)
ax[0].plot(xs, karlqvist(xs, 20.0, 25.0) * 1e3, "k:", label="Karlqvist g=25 (analitico)")
ax[0].set_xlim(-200, 200); ax[0].set_xlabel("x (um)"); ax[0].set_ylabel("h_x por unidad de FMM (1/mm)")
ax[0].set_title("Sensibilidad a y = 20 um sobre el polo"); ax[0].legend(fontsize=7); ax[0].grid(alpha=.3)
for name in table:
    ax[1].plot(spacings, [20 * np.log10(table[name]["T1"][str(d)]["ones"] / table["butt g=25"]["T1"]["5"]["ones"]) for d in spacings], "-o", label=name + " T1 unos")
ax[1].plot(spacings, [20 * np.log10(table["butt g=25"]["T2"][str(d)]["ones"] / table["butt g=25"]["T2"]["5"]["ones"]) for d in spacings], "k--s", label="butt g=25 T2 unos")
ax[1].set_xlabel("separacion d cabezal-medio (um)"); ax[1].set_ylabel("dB rel. butt g=25 @ d=5um")
ax[1].set_title("Amplitud de la secuencia de unos vs separacion"); ax[1].legend(fontsize=7); ax[1].grid(alpha=.3)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "sensitivity_spacing.png"), dpi=130)

fig, ax = plt.subplots(2, 2, figsize=(12, 6), sharex="col")
bits = list(rng.integers(0, 2, 24))
for j, (trk, cell) in enumerate(cells.items()):
    for i, d in enumerate((12.5, 50)):
        for name in ("butt g=25", "overlap s=25 t=20"):
            xs, ys, hx = fields[name]
            xh, e, _, _ = readback(xs, ys, hx, f2f_transitions(bits, cell), d, DELTA, A_TR)
            ax[i, j].plot(xh / 1e3, e, label=name)
        ax[i, j].set_title(f"{trk} ({tracks[trk]['bpi']} bpi), d = {d} um", fontsize=9); ax[i, j].grid(alpha=.3)
        ax[i, j].legend(fontsize=7)
    ax[1, j].set_xlabel("posicion (mm)")
fig.suptitle("Forma de onda F2F simulada (normalizada), datos aleatorios; medio: delta=10um, a=8um (ASUMIDOS)")
fig.tight_layout(); fig.savefig(os.path.join(OUT, "waveforms.png"), dpi=130)

json.dump(res, open(os.path.join(OUT, "results.json"), "w"), indent=1)
print(json.dumps({k: res[k] for k in ("solver_check_peak_ratio_FD_vs_Karlqvist_y20um", "efficiency", "inductance_uH_core_only_N72_mur1e4", "TG142_backcalc_N_eta")}, indent=1))
for name in table:
    for trk in cells:
        print(name, trk, {d: (round(v["resolution"], 2), round(v["ones"], 4), round(v["pw50_um"])) for d, v in table[name][trk].items()})
for name in air:
    for trk in cells: print(name, trk, {d: (round(v["resolution"], 2), f'{v["zeros"]:.2e}') for d, v in air[name][trk].items()})
for k, v in est.items():
    if "v=0.19" in k: print(k, f"{v*1e6:.1f} uV")
