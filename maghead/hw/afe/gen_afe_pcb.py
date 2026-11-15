#!/usr/bin/env python3
"""Genera maghead_afe.kicad_pcb (KiCad 9, 4 capas) a partir de maghead_afe.net.

Se ejecuta DENTRO del contenedor kicad/kicad:9.0 (necesita el modulo pcbnew):

    docker run --rm -v <maghead>:/work -w /work/hw/afe kicad/kicad:9.0 python3 gen_afe_pcb.py

Variables de entorno de depuracion: AFE_NOROUTE=1 (solo colocacion), AFE_DBG=<net> (traza el ruteo).

Pasos:
  1. carga las huellas de stock indicadas en el netlist y asigna net a cada pad;
  2. colocacion determinista por coordenadas explicitas (canal B = espejo del A);
  3. ruteo propio: A* sobre rejilla de 0.1 mm, 2 capas de senal (F.Cu/B.Cu) + vias,
     obstaculos inflados por clearance + medio ancho;
  4. GND y +3V3A bajan a los planos internos con una via junto a cada pad SMD;
  5. zonas (In1 GND, In2 +3V3A, B.Cu GND), serigrafia, reglas en .kicad_pro.
Coordenadas "locales" en mm con origen en la esquina superior izquierda de la placa.
"""
import heapq
import json
import math
import os
import sys
import time

import numpy as np
import pcbnew

from sexpr import parse, find, find1

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = "maghead_afe"
FPDIR = "/usr/share/kicad/footprints"

W, H = 90.0, 60.0          # placa
OX, OY = 100.0, 80.0       # origen de la placa en la hoja
RC = 3.0                   # radio de esquina
HOLES = [(4.0, 4.0), (W - 4.0, 4.0), (4.0, H - 4.0), (W - 4.0, H - 4.0)]

CLR = 0.20                 # clearance cobre-cobre
EDGE = 0.30                # cobre a borde
W_SIG, W_PWR = 0.25, 0.40
VIA_D, VIA_DRILL = 0.60, 0.30
PLANE_NETS = ("GND", "+3V3A")

# ----------------------------------------------------------------------------- colocacion
# ref: (x, y, rot)   -- canal A (mitad superior) y partes comunes
PL = {
    "U1": (24.0, 30.0, 270), "U2": (46.0, 30.0, 270), "U3": (34.1, 30.0, 270), "U4": (66.0, 30.0, 270),
    "C10": (28.0, 31.2, 90), "C11": (30.05, 31.2, 90),
    "C12": (50.0, 31.2, 90), "C13": (52.05, 31.2, 90),
    "R30": (38.1, 28.2, 270), "C32": (38.1, 31.9, 90), "C30": (40.99, 28.2, 90), "R31": (40.99, 32.0, 270),
    "C41": (70.0, 31.3, 90), "C40": (72.05, 31.3, 90), "R40": (74.1, 31.3, 270),
    "U5": (78.7, 12.5, 180), "C20": (82.3, 12.5, 90), "C21": (75.3, 12.5, 90), "C22": (73.0, 12.5, 90),
    "TP3": (75.0, 8.3, 0),
    "J4": (85.0, 21.11, 0), "C111": (77.0, 26.19, 180), "C211": (77.0, 31.27, 180),
    "C23": (77.0, 38.89, 180), "D3": (77.4, 42.3, 270),
    "J3": (74.0, H - 4.5, 0), "R113": (82.0, 49.5, 270), "R213": (66.0, 49.5, 270),
    "TP1": (9.5, 30.0, 0), "TP2": (36.5, 20.5, 0),
    "J1": (4.0, 24.0, 180),
}
PL_A = {
    "R101": (8.0, 22.7, 90), "C101": (10.1, 22.7, 90), "R100": (12.9, 21.5, 0), "D101": (14.5, 26.3, 90),
    "R102": (19.7, 23.4, 0), "C102": (22.5, 24.2, 270),
    "R103": (25.27, 25.0, 0), "C103": (25.27, 22.95, 0),
    "R104": (24.2, 20.15, 90), "R105": (26.25, 20.15, 90), "JP101": (26.25, 16.0, 90),
    "TP101": (31.0, 20.6, 0), "C104": (30.5, 24.0, 0), "R106": (40.3, 25.0, 0),
    "R108": (43.8, 25.0, 180), "C108": (43.8, 22.95, 180), "R109": (43.8, 20.9, 180), "C109": (43.8, 18.85, 180),
    "R107": (47.3, 25.0, 0), "C107": (47.3, 22.95, 0), "R110": (47.3, 20.9, 0), "C110": (47.3, 18.85, 0),
    "JP102": (41.0, 15.5, 180), "JP103": (45.1, 15.5, 180), "JP104": (49.2, 15.5, 180),
    "R111": (51.5, 25.0, 0), "C112": (52.0, 22.6, 0), "R112": (56.2, 22.6, 0), "TP102": (54.5, 19.0, 0),
    "R114": (62.5, 24.6, 0), "R115": (65.365, 24.0, 90), "RV101": (64.5, 18.5, 180),
}
B_SHIFT = -1.27            # los pines del canal B de los SOIC-8 quedan 1 paso a la izquierda
B_NOSHIFT = {"R201", "C201", "R200", "D201"}


def mirror_b():
    out = {}
    for ref, (x, y, rot) in PL_A.items():
        pre = ref.rstrip("0123456789")
        rb = pre + str(int(ref[len(pre):]) + 100)
        nrot = (180 - rot) % 360 if pre == "JP" else (-rot) % 360
        out[rb] = (x + (0 if rb in B_NOSHIFT else B_SHIFT), H - y, nrot)
    return out


# todo lo que esta a la derecha de U3 se desplaza +2 mm (hueco para las referencias de la red de U2)
X2 = 2.0
for _d in (PL, PL_A):
    for _r, (_x, _y, _a) in list(_d.items()):
        if _x >= 41.0:
            _d[_r] = (_x + X2, _y, _a)
PL_A.update({
    "R101": (9.6, 22.7, 90), "C101": (11.7, 22.7, 90), "R100": (14.5, 21.5, 0),
    "JP101": (26.25, 14.5, 90), "C104": (32.2, 24.0, 0), "TP101": (32.5, 20.6, 0),
    "R106": (39.0, 25.0, 0),
    "R111": (57.0, 25.0, 0), "C112": (57.5, 22.5, 0), "R112": (61.7, 22.5, 0), "TP102": (58.0, 19.0, 0),
})
PL["TP2"] = (38.0, 20.0, 0)
PL.update(PL_A)
PL.update(mirror_b())
PL["J2"] = (4.0, 36.0, 0)

# posiciones manuales de referencias (x, y, angulo); canal B por espejo
REFPOS_A = {
    "R104": (22.9, 17.5, 0), "R105": (27.7, 17.5, 0), "C102": (22.5, 21.0, 90),
    "C103": (28.5, 22.95, 0), "R103": (28.5, 25.0, 0), "R102": (19.7, 24.9, 0),
    "R101": (9.6, 19.4, 90), "C101": (11.7, 19.4, 90),
    "R108": (42.25, 25.0, 0), "C108": (42.25, 22.95, 0), "R109": (42.25, 20.9, 0), "C109": (42.25, 18.85, 0),
    "R107": (52.8, 25.0, 0), "C107": (52.8, 22.95, 0), "R110": (52.8, 20.9, 0), "C110": (52.8, 18.85, 0),
}
REFPOS = {"U3": (34.4, 34.65, 0), "C32": (39.45, 31.9, 90), "C10": (28.0, 28.0, 90), "C11": (30.05, 28.0, 90), "C12": (52.0, 28.0, 90), "C13": (54.05, 28.0, 90),
          "C41": (72.0, 28.1, 90), "C40": (74.05, 28.1, 90), "R40": (76.1, 28.1, 90)}
REFPOS.update(REFPOS_A)
for _r, (_x, _y, _a) in REFPOS_A.items():
    _pre = _r.rstrip("0123456789")
    _rb = _pre + str(int(_r[len(_pre):]) + 100)
    REFPOS[_rb] = (_x + (0 if _rb in B_NOSHIFT else B_SHIFT), H - _y, _a)

# ----------------------------------------------------------------------------- ruteo: plan
SENSITIVE = ["/INA_P", "/INB_P", "/FB1A", "/FB1B", "/HEAD_A_P", "/HEAD_B_P", "/HEAD_A_N", "/HEAD_B_N"]
ORDER_1 = SENSITIVE + ["/G1A_J", "/G1B_J", "/S1A", "/S1B",
                       "/FB2A", "/FB2B", "/FB2A_J1", "/FB2B_J1", "/FB2A_J2", "/FB2B_J2", "/FB2A_J3", "/FB2B_J3",
                       "/AC_A", "/AC_B", "/U3B_NC", "/VREF_DIV", "/CMPA_P", "/CMPB_P", "/CMPA_H", "/CMPB_H",
                       "/MON_A_C", "/MON_B_C", "/ADC_VREF"]
ORDER_PWR = ["/+3V3C", "VBUS"]
ORDER_2 = ["/S2A", "/S2B", "/VREF", "/ADC_A", "/ADC_B", "/CMP_A", "/CMP_B", "/MON_A", "/MON_B"]
F_ONLY = set(SENSITIVE) | {"/G1A_J", "/G1B_J", "/U3B_NC", "/AC_A", "/AC_B", "/MON_A_C", "/MON_B_C",
                           "/CMPA_P", "/CMPB_P", "/FB2A", "/FB2B"}
XMIN = {"/CMP_A": 60.0, "/CMP_B": 60.0, "/CMPA_H": 60.0, "/CMPB_H": 60.0,
        "/ADC_A": 48.0, "/ADC_B": 48.0, "/MON_A": 48.0, "/MON_B": 48.0, "VBUS": 62.0, "/+3V3C": 62.0}
# enlaces locales en F.Cu de las nets de plano (pin de alimentacion <-> desacoplo)
PWR_LINKS = [("+3V3A", ["U1.8", "C10.1", "C11.1"]), ("+3V3A", ["U2.8", "C12.1", "C13.1"]),
             ("+3V3A", ["U3.8", "C32.1"]), ("+3V3A", ["U5.5", "C21.1", "C22.1"])]

# ----------------------------------------------------------------------------- rejilla
STEP = 0.1
NX = int(round(W / STEP)) + 1
NY = int(round(H / STEP)) + 1
NXY = NX * NY
XS = np.arange(NX) * STEP
YS = np.arange(NY) * STEP
MARG = 0.02
HALF = {"S": W_SIG / 2, "P": W_PWR / 2, "V": VIA_D / 2}
OWN = {c: [np.zeros((NY, NX), np.int16), np.zeros((NY, NX), np.int16)] for c in HALF}
NOVIA = np.zeros((NY, NX), bool)
DIRS = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]
TURN = [0.0, 0.6, 1.5]
VIA_COST = 30.0


def _apply(arr, m, sl, net):
    sub = arr[sl]
    if net < 0:
        sub[m] = -1
    else:
        conflict = m & (sub != 0) & (sub != net)
        sub[m & (sub == 0)] = net
        sub[conflict] = -1


def _window(x0, y0, x1, y1, r):
    ix0 = max(0, int(math.floor((x0 - r) / STEP)))
    ix1 = min(NX - 1, int(math.ceil((x1 + r) / STEP)))
    iy0 = max(0, int(math.floor((y0 - r) / STEP)))
    iy1 = min(NY - 1, int(math.ceil((y1 + r) / STEP)))
    return (slice(iy0, iy1 + 1), slice(ix0, ix1 + 1)), XS[ix0:ix1 + 1][None, :], YS[iy0:iy1 + 1][:, None]


def dist_rect(X, Y, x0, y0, x1, y1):
    dx = np.maximum(np.maximum(x0 - X, X - x1), 0)
    dy = np.maximum(np.maximum(y0 - Y, Y - y1), 0)
    return np.sqrt(dx * dx + dy * dy)


def dist_seg(X, Y, xa, ya, xb, yb):
    vx, vy = xb - xa, yb - ya
    L2 = vx * vx + vy * vy
    if L2 < 1e-12:
        return np.hypot(X - xa, Y - ya)
    t = np.clip(((X - xa) * vx + (Y - ya) * vy) / L2, 0, 1)
    return np.hypot(X - (xa + t * vx), Y - (ya + t * vy))


def mark_rect(layers, x0, y0, x1, y1, net, extra=0.0):
    for c, h in HALF.items():
        r = CLR + h + MARG + extra
        sl, X, Y = _window(x0, y0, x1, y1, r)
        m = dist_rect(X, Y, x0, y0, x1, y1) <= r
        for l in layers:
            _apply(OWN[c][l], m, sl, net)


def mark_seg(layers, xa, ya, xb, yb, rad, net, extra=0.0):
    for c, h in HALF.items():
        r = rad + CLR + h + MARG + extra
        sl, X, Y = _window(min(xa, xb), min(ya, yb), max(xa, xb), max(ya, yb), r)
        m = dist_seg(X, Y, xa, ya, xb, yb) <= r
        for l in layers:
            _apply(OWN[c][l], m, sl, net)


def novia_circle(x, y, r):
    sl, X, Y = _window(x, y, x, y, r)
    NOVIA[sl] |= np.hypot(X - x, Y - y) <= r


def novia_rect(x0, y0, x1, y1, r):
    sl, X, Y = _window(x0, y0, x1, y1, r)
    NOVIA[sl] |= dist_rect(X, Y, x0, y0, x1, y1) <= r


def mark_outline():
    X, Y = XS[None, :], YS[:, None]
    # distancia al interior del rectangulo redondeado
    qx = np.maximum(np.maximum(RC - X, X - (W - RC)), 0)
    qy = np.maximum(np.maximum(RC - Y, Y - (H - RC)), 0)
    inside_depth = RC - np.sqrt(qx * qx + qy * qy)      # >0 dentro; = distancia al borde cerca de el
    edge_d = np.minimum(np.minimum(X, W - X), np.minimum(Y, H - Y))
    depth = np.minimum(inside_depth + 0 * edge_d, np.where((qx > 0) & (qy > 0), inside_depth, edge_d))
    for c, h in HALF.items():
        m = depth < EDGE + h + MARG
        for l in (0, 1):
            OWN[c][l][m] = -1


# ----------------------------------------------------------------------------- A*
def astar(src, tgt, ok, viaok, hf, allow_via, layers, lcost=(1.0, 1.0), maxexp=1500000):
    g = {}
    par = {}
    heap = []
    for (l, ix, iy) in src:
        if l not in layers:
            continue
        idx = iy * NX + ix
        if not ok[l][idx]:
            continue
        s = (l * NXY + idx) * 9 + 8
        g[s] = 0.0
        heapq.heappush(heap, (hf[idx], 0.0, s))
    nexp = 0
    while heap:
        f, gc, s = heapq.heappop(heap)
        if g.get(s, 1e18) < gc:
            continue
        d = s % 9
        ci = s // 9
        l = ci // NXY
        idx = ci % NXY
        if tgt[l][idx]:
            path = []
            while True:
                ci = s // 9
                path.append((ci // NXY, (ci % NXY) % NX, (ci % NXY) // NX))
                if s not in par:
                    break
                s = par[s]
            path.reverse()
            return path
        nexp += 1
        if nexp > maxexp:
            return None
        ix = idx % NX
        iy = idx // NX
        okl = ok[l]
        lc = lcost[l]
        for nd in range(8):
            if d < 8:
                t = abs(nd - d)
                if t > 4:
                    t = 8 - t
                if t > 2:
                    continue
                pen = TURN[t]
            else:
                pen = 0.0
            dx, dy = DIRS[nd]
            nx_ = ix + dx
            ny_ = iy + dy
            if nx_ < 0 or ny_ < 0 or nx_ >= NX or ny_ >= NY:
                continue
            nidx = ny_ * NX + nx_
            if not okl[nidx]:
                continue
            ng = gc + (lc if nd % 2 == 0 else 1.4142 * lc) + pen
            ns = (l * NXY + nidx) * 9 + nd
            if ng < g.get(ns, 1e18):
                g[ns] = ng
                par[ns] = s
                heapq.heappush(heap, (ng + hf[nidx], ng, ns))
        if allow_via and viaok[idx]:
            ol = 1 - l
            if ol in layers and ok[ol][idx]:
                ns = (ol * NXY + idx) * 9 + 8
                ng = gc + VIA_COST
                if ng < g.get(ns, 1e18):
                    g[ns] = ng
                    par[ns] = s
                    heapq.heappush(heap, (ng + hf[idx], ng, ns))
    return None


class Router:
    def block_under_passives(self):
        """Sin pistas ni vias entre los dos pads de un 0603/0805 (soldadura a mano)."""
        byref = {}
        for p in self.pads:
            byref.setdefault(p["ref"], []).append(p)
        for ref, pl in byref.items():
            if ref[0] in "RC" and ref[1].isdigit() and len(pl) == 2:
                a, b = pl
                x0, x1 = sorted((a["cx"], b["cx"]))
                y0, y1 = sorted((a["cy"], b["cy"]))
                if x1 - x0 > y1 - y0:
                    box = (x0 + 0.3, a["y0"] + 0.1, x1 - 0.3, a["y1"] - 0.1)
                else:
                    box = (a["x0"] + 0.1, y0 + 0.3, a["x1"] - 0.1, y1 - 0.3)
                for c in ("S", "P"):
                    sl, X, Y = _window(*box, 0)
                    m = dist_rect(X, Y, *box) <= 0.11
                    OWN[c][0][sl][m] = -1
                novia_rect(*box, 0.3)

    def __init__(self, pads, netid):
        self.pads = pads                # lista de dicts
        self.netid = netid
        self.tracks = []                # (net, layer, x1, y1, x2, y2, w)
        self.vias = []                  # (net, x, y)
        self.fail = []
        self.padcell = {}               # (net, l, idx) -> (cx, cy)
        self.tgt = {}                   # net -> [bytearray, bytearray]
        self.pts = {}                   # net -> lista de puntos (x, y) del arbol
        for p in pads:
            self.mark_pad(p)
        self.block_under_passives()

    # --- obstaculos
    def mark_pad(self, p):
        nid = self.netid.get(p["net"], -1)
        layers = (0, 1) if p["tht"] else (0,)
        if p["npth"]:
            mark_seg((0, 1), p["cx"], p["cy"], p["cx"], p["cy"], p["drill"] / 2 + 0.06, -1)
            novia_circle(p["cx"], p["cy"], p["drill"] / 2 + 0.6)
            return
        if p["round"]:
            mark_seg(layers, *p["seg"], p["rad"], nid)
        else:
            mark_rect(layers, p["x0"], p["y0"], p["x1"], p["y1"], nid)
        novia_rect(p["x0"], p["y0"], p["x1"], p["y1"], VIA_D / 2 + (0.25 if p["tht"] else 0.10))

    def pad_cells(self, p, half):
        if p["round"]:
            sx = (p["x1"] - p["x0"]) * 0.22
            sy = (p["y1"] - p["y0"]) * 0.22
        else:
            sx = sy = half - 0.005
        x0, x1, y0, y1 = p["x0"] + sx, p["x1"] - sx, p["y0"] + sy, p["y1"] - sy
        ixs = range(int(math.ceil(x0 / STEP - 1e-9)), int(math.floor(x1 / STEP + 1e-9)) + 1)
        iys = range(int(math.ceil(y0 / STEP - 1e-9)), int(math.floor(y1 / STEP + 1e-9)) + 1)
        cells = [(ix, iy) for ix in ixs for iy in iys]
        if not cells:
            cells = [(int(round(p["cx"] / STEP)), int(round(p["cy"] / STEP)))]
        layers = (0, 1) if p["tht"] else (0,)
        return [(l, ix, iy) for l in layers for (ix, iy) in cells]

    def passable(self, nid, cls, xmin=None):
        ok = []
        for l in (0, 1):
            a = OWN[cls][l]
            m = (a == 0) | (a == nid)
            if xmin is not None:
                m[:, :int(xmin / STEP)] = False
            ok.append(m.tobytes())
        v = ((OWN["V"][0] == 0) | (OWN["V"][0] == nid)) & ((OWN["V"][1] == 0) | (OWN["V"][1] == nid)) & ~NOVIA
        return ok, v

    def hfield(self, pts):
        f = np.full((NY, NX), 1e9, np.float32)
        X, Y = XS[None, :], YS[:, None]
        for (x, y) in pts:
            np.minimum(f, np.hypot(X - x, Y - y), out=f)
        return (f / STEP).ravel().tolist()

    # --- emision
    def emit_path(self, net, path, w, start_pad_xy=None):
        nid = self.netid[net]
        tg = self.tgt.setdefault(net, [bytearray(NXY), bytearray(NXY)])
        pts = self.pts.setdefault(net, [])
        segs = []
        # tramo pad -> primera celda y ultima celda -> pad
        l0, ix0, iy0 = path[0]
        c0 = self.padcell.get((net, l0, iy0 * NX + ix0))
        if c0 and math.hypot(c0[0] - ix0 * STEP, c0[1] - iy0 * STEP) > 1e-4:
            segs.append((l0, c0[0], c0[1], ix0 * STEP, iy0 * STEP))
        l1, ix1, iy1 = path[-1]
        c1 = self.padcell.get((net, l1, iy1 * NX + ix1))
        if c1 and math.hypot(c1[0] - ix1 * STEP, c1[1] - iy1 * STEP) > 1e-4:
            segs.append((l1, ix1 * STEP, iy1 * STEP, c1[0], c1[1]))
        run = [path[0]]
        for a, b in zip(path, path[1:]):
            tg[a[0]][a[2] * NX + a[1]] = 1
            if a[0] != b[0]:
                self.add_via(net, a[1] * STEP, a[2] * STEP)
                self._flush(run, segs)
                run = [b]
            else:
                run.append(b)
        tg[path[-1][0]][path[-1][2] * NX + path[-1][1]] = 1
        self._flush(run, segs)
        for (l, xa, ya, xb, yb) in segs:
            self.tracks.append((net, l, xa, ya, xb, yb, w))
            mark_seg((l,), xa, ya, xb, yb, w / 2, nid)
            n = max(1, int(math.hypot(xb - xa, yb - ya) / 0.8))
            for k in range(n + 1):
                pts.append((xa + (xb - xa) * k / n, ya + (yb - ya) * k / n))

    @staticmethod
    def _flush(run, segs):
        if len(run) < 2:
            return
        s = run[0]
        prev = run[0]
        dprev = None
        for q in run[1:]:
            d = (q[1] - prev[1], q[2] - prev[2])
            if dprev is not None and d != dprev:
                segs.append((s[0], s[1] * STEP, s[2] * STEP, prev[1] * STEP, prev[2] * STEP))
                s = prev
            dprev = d
            prev = q
        segs.append((s[0], s[1] * STEP, s[2] * STEP, prev[1] * STEP, prev[2] * STEP))

    def add_via(self, net, x, y):
        nid = self.netid[net]
        self.vias.append((net, x, y))
        mark_seg((0, 1), x, y, x, y, VIA_D / 2, nid)
        novia_circle(x, y, VIA_D + 0.25)
        tg = self.tgt.setdefault(net, [bytearray(NXY), bytearray(NXY)])
        idx = int(round(y / STEP)) * NX + int(round(x / STEP))
        tg[0][idx] = 1
        tg[1][idx] = 1

    def add_pad_to_tree(self, net, p, half):
        tg = self.tgt.setdefault(net, [bytearray(NXY), bytearray(NXY)])
        for (l, ix, iy) in self.pad_cells(p, half):
            tg[l][iy * NX + ix] = 1
        self.pts.setdefault(net, []).append((p["cx"], p["cy"]))

    # --- net completa (arbol de Prim sobre los pads)
    def route_net(self, net, padlist=None, w=W_SIG, cls="S", allow_via=True, layers=(0, 1), xmin=None,
                  fresh=False):
        nid = self.netid[net]
        pads = padlist if padlist is not None else [p for p in self.pads if p["net"] == net]
        half = w / 2
        for p in pads:
            for (l, ix, iy) in self.pad_cells(p, half):
                self.padcell[(net, l, iy * NX + ix)] = (p["cx"], p["cy"])
        if fresh:
            self.tgt[net] = [bytearray(NXY), bytearray(NXY)]
            self.pts[net] = []
        todo = list(pads)
        # semilla: el par de pads mas cercano
        best = None
        for i, a in enumerate(todo):
            for b in todo[i + 1:]:
                d = math.hypot(a["cx"] - b["cx"], a["cy"] - b["cy"])
                if best is None or d < best[0]:
                    best = (d, a)
        seed = best[1]
        todo.remove(seed)
        self.add_pad_to_tree(net, seed, half)
        tree = [seed]
        ok_all = True
        while todo:
            best = None
            for p in todo:
                for (x, y) in self.pts[net]:
                    d = math.hypot(p["cx"] - x, p["cy"] - y)
                    if best is None or d < best[0]:
                        best = (d, p)
            p = best[1]
            todo.remove(p)
            ok, vok = self.passable(nid, cls, xmin)
            hf = self.hfield(self.pts[net])
            path = astar(self.pad_cells(p, half), self.tgt[net], ok, vok.tobytes(), hf, allow_via, layers)
            if path is None:
                self.fail.append((net, p["ref"] + "." + p["num"]))
                ok_all = False
                print("  FALLO %s %s.%s" % (net, p["ref"], p["num"]))
                continue
            if os.environ.get("AFE_DBG") == net:
                print("DBG", p["ref"], p["num"], [(l, round(ix * STEP, 1), round(iy * STEP, 1)) for (l, ix, iy) in path[:3]], "...", [(l, round(ix * STEP, 1), round(iy * STEP, 1)) for (l, ix, iy) in path[-4:]], len(path))
            self.emit_path(net, path, w)
            self.add_pad_to_tree(net, p, half)
            tree.append(p)
        return ok_all

    # --- via a plano junto a un pad SMD
    def fanout(self, p, w=W_PWR):
        net = p["net"]
        nid = self.netid[net]
        half = w / 2
        for (l, ix, iy) in self.pad_cells(p, half):
            self.padcell[(net, l, iy * NX + ix)] = (p["cx"], p["cy"])
        ok, vok = self.passable(nid, "P")
        okarr = np.frombuffer(ok[0], np.uint8).reshape(NY, NX).astype(bool)
        tmask = (vok & okarr)
        # reutilizar una via propia ya existente
        tb = bytearray(tmask.tobytes())
        for (vn, vx, vy) in self.vias:
            if vn == net:
                tb[int(round(vy / STEP)) * NX + int(round(vx / STEP))] = 1
        zero = [0.0] * NXY
        path = astar(self.pad_cells(p, half), [tb, bytearray(NXY)], ok, b"", zero, False, (0,), maxexp=200000)
        if path is None:
            self.fail.append((net, "via " + p["ref"] + "." + p["num"]))
            print("  FALLO via %s %s.%s" % (net, p["ref"], p["num"]))
            return
        l, ix, iy = path[-1]
        x, y = ix * STEP, iy * STEP
        self.emit_path(net, path, w)
        if not any(vn == net and abs(vx - x) < 1e-6 and abs(vy - y) < 1e-6 for (vn, vx, vy) in self.vias):
            self.add_via(net, x, y)


# ----------------------------------------------------------------------------- netlist
def load_netlist(fn):
    t = parse(open(fn).read())
    comps = {}
    for c in find(find1(t, "components"), "comp"):
        ref = find1(c, "ref")[1]
        props = [p[1][1] for p in find(c, "property")]
        fields = {f[1][1]: (f[2] if len(f) > 2 else "") for f in find(find1(c, "fields") or ["fields"], "field")}
        comps[ref] = dict(value=find1(c, "value")[1], fp=find1(c, "footprint")[1],
                          tstamp=find1(c, "tstamps")[1], dnp="dnp" in props, fields=fields)
    padnet = {}
    for n in find(find1(t, "nets"), "net"):
        name = find1(n, "name")[1]
        for nd in find(n, "node"):
            pf = find1(nd, "pinfunction")
            pt = find1(nd, "pintype")
            padnet[(find1(nd, "ref")[1], find1(nd, "pin")[1])] = (name, pf[1] if pf else "", pt[1] if pt else "")
    return comps, padnet


def V(x, y):
    return pcbnew.VECTOR2I(pcbnew.FromMM(OX + x), pcbnew.FromMM(OY + y))


def mm(v):
    return pcbnew.ToMM(v)


# ----------------------------------------------------------------------------- serigrafia
RS = 0.05
RNX = int(round(W / RS)) + 1
RNY = int(round(H / RS)) + 1
OCC = np.zeros((RNY, RNX), bool)


def occ_rect(x0, y0, x1, y1):
    ix0, ix1 = max(0, int(math.floor(x0 / RS))), min(RNX - 1, int(math.ceil(x1 / RS)))
    iy0, iy1 = max(0, int(math.floor(y0 / RS))), min(RNY - 1, int(math.ceil(y1 / RS)))
    OCC[iy0:iy1 + 1, ix0:ix1 + 1] = True


def occ_free(x0, y0, x1, y1):
    ix0, ix1 = max(0, int(math.floor(x0 / RS))), min(RNX - 1, int(math.ceil(x1 / RS)))
    iy0, iy1 = max(0, int(math.floor(y0 / RS))), min(RNY - 1, int(math.ceil(y1 / RS)))
    return not OCC[iy0:iy1 + 1, ix0:ix1 + 1].any()


def text_dims(s, size):
    return len(s) * size * 0.95 + 0.2, size * 1.25 + 0.2


def find_spot(cx, cy, w, h, allow_rot=True, bias=(0.0, 0.0)):
    S = np.zeros((RNY + 1, RNX + 1), np.int32)
    S[1:, 1:] = OCC.cumsum(0).cumsum(1)
    best = None
    for rot, (ww, hh) in ((0, (w, h)), (90, (h, w))):
        if rot and not allow_rot:
            continue
        wi, hi = int(math.ceil(ww / RS)), int(math.ceil(hh / RS))
        tot = S[hi:, wi:] - S[:-hi, wi:] - S[hi:, :-wi] + S[:-hi, :-wi]
        xs = (np.arange(tot.shape[1]) + wi / 2.0) * RS
        ys = (np.arange(tot.shape[0]) + hi / 2.0) * RS
        d = np.hypot(xs[None, :] - cx - bias[0], ys[:, None] - cy - bias[1]) + (0.7 if rot else 0.0)
        d[tot != 0] = 1e9
        k = int(np.argmin(d))
        iy, ix = divmod(k, tot.shape[1])
        if d[iy, ix] < 1e8 and (best is None or d[iy, ix] < best[0]):
            best = (float(d[iy, ix]), float(xs[ix]), float(ys[iy]), rot, ww, hh)
    return best


# ----------------------------------------------------------------------------- principal
def main():
    t0 = time.time()
    comps, padnet = load_netlist(os.path.join(HERE, PROJECT + ".net"))
    missing = sorted(set(comps) - set(PL))
    extra = sorted(set(PL) - set(comps))
    if missing or extra:
        sys.exit("colocacion incompleta: faltan %s sobran %s" % (missing, extra))

    board = pcbnew.BOARD()
    board.SetCopperLayerCount(4)
    bds = board.GetDesignSettings()
    bds.SetBoardThickness(pcbnew.FromMM(1.6))
    bds.m_MinClearance = pcbnew.FromMM(CLR)
    bds.m_TrackMinWidth = pcbnew.FromMM(0.15)
    bds.m_ViasMinSize = pcbnew.FromMM(VIA_D)
    bds.m_MinThroughDrill = pcbnew.FromMM(VIA_DRILL)
    bds.m_CopperEdgeClearance = pcbnew.FromMM(EDGE)
    bds.m_HoleClearance = pcbnew.FromMM(0.25)
    bds.m_HoleToHoleMin = pcbnew.FromMM(0.25)
    bds.m_SolderMaskExpansion = pcbnew.FromMM(0.05)
    tb = board.GetTitleBlock()
    tb.SetTitle("MagHead AFE - front end analogico 2 canales")
    tb.SetRevision("A")
    tb.SetCompany("Electronic Cats")
    tb.SetComment(0, "Prototipo de laboratorio rev A - generado por gen_afe_pcb.py")

    # --- nets
    nets = {}
    netid = {}
    for name in sorted(set(v[0] for v in padnet.values())):
        ni = pcbnew.NETINFO_ITEM(board, name)
        board.Add(ni)
        nets[name] = ni
        netid[name] = len(netid) + 1

    # --- huellas
    pads = []
    fps = {}
    for ref in sorted(comps):
        c = comps[ref]
        lib, name = c["fp"].split(":")
        fp = pcbnew.FootprintLoad(os.path.join(FPDIR, lib + ".pretty"), name)
        if fp is None:
            sys.exit("no se pudo cargar la huella " + c["fp"])
        fp.SetFPID(pcbnew.LIB_ID(lib, name))
        fp.SetReference(ref)
        fp.SetValue(c["value"])
        fp.SetPath(pcbnew.KIID_PATH("/" + c["tstamp"]))
        if c["dnp"]:
            fp.SetDNP(True)
        # la huella de stock del jack viene marcada "exclude_from_bom"; el esquematico SI lo lista
        fp.SetAttributes(fp.GetAttributes() & ~pcbnew.FP_EXCLUDE_FROM_BOM)
        x, y, rot = PL[ref]
        fp.SetPosition(V(x, y))
        fp.SetOrientationDegrees(rot)
        board.Add(fp)
        fps[ref] = fp
        for pad in fp.Pads():
            num = pad.GetNumber()
            npth = pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH
            if not npth:
                if (ref, num) not in padnet:
                    sys.exit("pad %s.%s no esta en el netlist" % (ref, num))
                nname, pf, pt = padnet[(ref, num)]
                pad.SetNet(nets[nname])
                if pf:
                    pad.SetPinFunction(pf)
                if pt:
                    pad.SetPinType(pt)
            else:
                nname = None
            bb = pad.GetBoundingBox()
            x0, y0 = mm(bb.GetLeft()) - OX, mm(bb.GetTop()) - OY
            x1, y1 = mm(bb.GetRight()) - OX, mm(bb.GetBottom()) - OY
            cx, cy = mm(pad.GetPosition().x) - OX, mm(pad.GetPosition().y) - OY
            rnd = pad.GetShape() in (pcbnew.PAD_SHAPE_CIRCLE, pcbnew.PAD_SHAPE_OVAL)
            w_, h_ = x1 - x0, y1 - y0
            rad = min(w_, h_) / 2
            if w_ >= h_:
                seg = (cx - (w_ / 2 - rad), cy, cx + (w_ / 2 - rad), cy)
            else:
                seg = (cx, cy - (h_ / 2 - rad), cx, cy + (h_ / 2 - rad))
            pads.append(dict(ref=ref, num=num, net=nname, cx=cx, cy=cy, x0=x0, y0=y0, x1=x1, y1=y1,
                             tht=pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH, npth=npth, round=rnd,
                             seg=seg, rad=rad, drill=mm(pad.GetDrillSize().x)))
    for (ref, num) in padnet:
        if not any(p["ref"] == ref and p["num"] == num for p in pads):
            sys.exit("el netlist pide el pad %s.%s y la huella no lo tiene" % (ref, num))

    # --- taladros de montaje (solo placa, fuera del esquematico)
    for i, (hx, hy) in enumerate(HOLES):
        fp = pcbnew.FootprintLoad(os.path.join(FPDIR, "MountingHole.pretty"), "MountingHole_3.2mm_M3")
        fp.SetFPID(pcbnew.LIB_ID("MountingHole", "MountingHole_3.2mm_M3"))
        fp.SetReference("H%d" % (i + 1))
        fp.SetValue("M3")
        fp.SetAttributes(pcbnew.FP_BOARD_ONLY | pcbnew.FP_EXCLUDE_FROM_POS_FILES | pcbnew.FP_EXCLUDE_FROM_BOM)
        fp.SetPosition(V(hx, hy))
        fp.Reference().SetVisible(False)
        board.Add(fp)
        fps["H%d" % (i + 1)] = fp
        mark_seg((0, 1), hx, hy, hx, hy, 1.6 + 0.3, -1)
        novia_circle(hx, hy, 1.6 + 0.9)

    # --- contorno
    def line(xa, ya, xb, yb):
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(V(xa, ya))
        s.SetEnd(V(xb, yb))
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(pcbnew.FromMM(0.1))
        board.Add(s)

    def arc(cx, cy, a0):
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_ARC)
        a1, am = math.radians(a0 + 90), math.radians(a0 + 45)
        a0r = math.radians(a0)
        s.SetArcGeometry(V(cx + RC * math.cos(a0r), cy + RC * math.sin(a0r)),
                         V(cx + RC * math.cos(am), cy + RC * math.sin(am)),
                         V(cx + RC * math.cos(a1), cy + RC * math.sin(a1)))
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(pcbnew.FromMM(0.1))
        board.Add(s)

    line(RC, 0, W - RC, 0)
    line(W, RC, W, H - RC)
    # J3 trae en Edge.Cuts su propio tramo de borde (y local = 4.5) con la muesca del casquillo
    jx = PL["J3"][0]
    line(W - RC, H, jx + 6.5, H)
    line(jx - 6.5, H, RC, H)
    mark_rect((0, 1), jx - 2.2, H - 1.4, jx + 2.2, H, -1, extra=EDGE - CLR)
    line(0, H - RC, 0, RC)
    arc(RC, RC, 180)
    arc(W - RC, RC, 270)
    arc(W - RC, H - RC, 0)
    arc(RC, H - RC, 90)
    mark_outline()

    # ------------------------------------------------------------------ ruteo
    R = Router(pads, netid)
    P = {(p["ref"] + "." + p["num"]): p for p in pads if not p["npth"]}

    def do(net):
        pw = net in ORDER_PWR
        ok = R.route_net(net, w=W_PWR if pw else W_SIG, cls="P" if pw else "S",
                         allow_via=net not in F_ONLY, layers=(0,) if net in F_ONLY else (0, 1),
                         xmin=XMIN.get(net))
        print("%-12s %s  (%.0fs)" % (net, "ok" if ok else "FALLO", time.time() - t0))
        sys.stdout.flush()

    noroute = bool(os.environ.get("AFE_NOROUTE"))
    for net in ([] if noroute else ORDER_1):
        do(net)
    for net, plist in ([] if noroute else PWR_LINKS):
        R.route_net(net, padlist=[P[k] for k in plist], w=W_PWR, cls="P", allow_via=False, layers=(0,), fresh=True)
    for net in ([] if noroute else ORDER_PWR):
        do(net)
    for p in pads:
        if p["net"] in PLANE_NETS and not p["tht"] and not noroute:
            R.fanout(p)
    print("fanout hecho (%.0fs)" % (time.time() - t0))
    for net in ([] if noroute else ORDER_2):
        do(net)
    routed = set(ORDER_1 + ORDER_PWR + ORDER_2) | set(PLANE_NETS)
    for name in nets:
        n = sum(1 for p in pads if p["net"] == name)
        if n > 1 and name not in routed:
            sys.exit("net sin plan de ruteo: " + name)

    # --- pistas y vias
    # partir las pistas en las uniones en T (cada union queda como extremo comun)
    ends = {}
    for (net, l, xa, ya, xb, yb, w) in R.tracks:
        for (x, y) in ((xa, ya), (xb, yb)):
            ends.setdefault((net, l), set()).add((round(x, 4), round(y, 4)))
    for (net, x, y) in R.vias:
        for l in (0, 1):
            ends.setdefault((net, l), set()).add((round(x, 4), round(y, 4)))
    split = []
    for (net, l, xa, ya, xb, yb, w) in R.tracks:
        L = math.hypot(xb - xa, yb - ya)
        if L < 1e-6:
            continue
        cuts = [0.0, 1.0]
        for (x, y) in ends[(net, l)]:
            t = ((x - xa) * (xb - xa) + (y - ya) * (yb - ya)) / (L * L)
            if 1e-6 < t < 1 - 1e-6 and math.hypot(xa + t * (xb - xa) - x, ya + t * (yb - ya) - y) < 1e-4:
                cuts.append(t)
        cuts.sort()
        for t0_, t1_ in zip(cuts, cuts[1:]):
            if (t1_ - t0_) * L > 1e-4:
                split.append((net, l, xa + t0_ * (xb - xa), ya + t0_ * (yb - ya),
                              xa + t1_ * (xb - xa), ya + t1_ * (yb - ya), w))
    R.tracks = split
    for (net, l, xa, ya, xb, yb, w) in R.tracks:
        if math.hypot(xb - xa, yb - ya) < 1e-6:
            continue
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(V(xa, ya))
        t.SetEnd(V(xb, yb))
        t.SetWidth(pcbnew.FromMM(w))
        t.SetLayer(pcbnew.F_Cu if l == 0 else pcbnew.B_Cu)
        t.SetNet(nets[net])
        board.Add(t)
    for (net, x, y) in R.vias:
        v = pcbnew.PCB_VIA(board)
        v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetPosition(V(x, y))
        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        v.SetWidth(pcbnew.F_Cu, pcbnew.FromMM(VIA_D))
        v.SetDrill(pcbnew.FromMM(VIA_DRILL))
        v.SetNet(nets[net])
        board.Add(v)

    # --- zonas
    def zone(layer, net, prio):
        z = pcbnew.ZONE(board)
        z.SetLayer(layer)
        z.SetNet(nets[net])
        o = z.Outline()
        o.NewOutline()
        for (x, y) in ((0, 0), (W, 0), (W, H), (0, H)):
            o.Append(pcbnew.FromMM(OX + x), pcbnew.FromMM(OY + y))
        z.SetLocalClearance(pcbnew.FromMM(CLR))
        z.SetMinThickness(pcbnew.FromMM(0.2))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
        z.SetThermalReliefGap(pcbnew.FromMM(0.3))
        z.SetThermalReliefSpokeWidth(pcbnew.FromMM(0.5))
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        z.SetAssignedPriority(prio)
        z.SetZoneName("%s_%s" % (net.strip("/+"), pcbnew.LayerName(layer)))
        board.Add(z)
        return z

    zone(pcbnew.In1_Cu, "GND", 0)
    zone(pcbnew.In2_Cu, "+3V3A", 0)
    zone(pcbnew.B_Cu, "GND", 0)

    # ------------------------------------------------------------------ serigrafia
    OCC[:int(0.7 / RS), :] = True
    OCC[-int(0.7 / RS):, :] = True
    OCC[:, :int(0.7 / RS)] = True
    OCC[:, -int(0.7 / RS):] = True
    for (hx, hy) in HOLES:
        occ_rect(hx - 3.3, hy - 3.3, hx + 3.3, hy + 3.3)
    cyd = {}
    for ref, fp in fps.items():
        bb = None
        for gi in fp.GraphicalItems():
            if gi.GetLayer() in (pcbnew.F_CrtYd, pcbnew.F_SilkS) and gi.GetClass() == "PCB_SHAPE":
                b = gi.GetBoundingBox()
                if bb is None:
                    bb = b
                else:
                    bb.Merge(b)
        box = (mm(bb.GetLeft()) - OX, mm(bb.GetTop()) - OY, mm(bb.GetRight()) - OX, mm(bb.GetBottom()) - OY)
        cyd[ref] = box
        occ_rect(*box)
    for p in pads:
        occ_rect(p["x0"] - 0.15, p["y0"] - 0.15, p["x1"] + 0.15, p["y1"] + 0.15)

    def text(s, x, y, size=0.8, rot=0, just="c", check=True, thick=None):
        t = pcbnew.PCB_TEXT(board)
        t.SetText(s)
        t.SetLayer(pcbnew.F_SilkS)
        t.SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(size), pcbnew.FromMM(size)))
        t.SetTextThickness(pcbnew.FromMM(thick or max(0.12, size * 0.16)))
        t.SetHorizJustify({"c": pcbnew.GR_TEXT_H_ALIGN_CENTER, "l": pcbnew.GR_TEXT_H_ALIGN_LEFT,
                           "r": pcbnew.GR_TEXT_H_ALIGN_RIGHT}[just])
        t.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_CENTER)
        t.SetPosition(V(x, y))
        t.SetTextAngle(pcbnew.EDA_ANGLE(rot, pcbnew.DEGREES_T))
        board.Add(t)
        w, h = text_dims(s, size)
        if rot:
            w, h = h, w
        xc = x + (w / 2 if just == "l" else -w / 2 if just == "r" else 0)
        box = (xc - w / 2, y - h / 2, xc + w / 2, y + h / 2)
        if check and not occ_free(*box):
            print("  AVISO serigrafia: '%s' pisa algo en (%.1f, %.1f)" % (s, x, y))
        occ_rect(*box)

    text("MagHead AFE revA - Electronic Cats", W / 2, 4.2, size=1.5)
    text("CANAL A", 14.0, 13.5, size=1.5)
    text("CANAL B", 14.0, 46.5, size=1.5)
    for ref, names in (("J1", ("P", "N", "GND")), ("J2", ("P", "N", "GND"))):
        for k, nm in enumerate(names):
            p = P["%s.%d" % (ref, k + 1)]
            text(nm, p["x1"] + 1.15, p["cy"], just="l")
    for k, nm in enumerate(("VBUS", "GND", "ADC_A", "GND", "ADC_B", "CMP_A", "CMP_B", "AREF")):
        p = P["J4.%d" % (k + 1)]
        text(nm, p["x0"] - 1.15, p["cy"], just="r")
    for ch, sgn in ((100, -1), (200, 1)):
        for k, nm in ((1, "x102"), (2, "x40"), (3, "x9.5"), (4, "x2")):
            ref = "JP%d" % (ch + k)
            x0, y0, x1, y1 = cyd[ref]
            text(nm, (x0 + x1) / 2, (y0 - 0.75) if sgn < 0 else (y1 + 0.75), size=0.9)
    text("ENTRADAS", 2.3, 30.0, size=0.9, rot=90)
    for ref, nm in (("TP1", "GND"), ("TP2", "VREF"), ("TP3", "+3V3A"), ("TP101", "S1A"), ("TP102", "S2A"),
                    ("TP201", "S1B"), ("TP202", "S2B"), ("J3", "MONITOR"), ("J4", "MCU"),
                    ("RV101", "UMBRAL A"), ("RV201", "UMBRAL B")):
        x0, y0, x1, y1 = cyd[ref]
        w, h = text_dims(nm, 0.9)
        up = (y0 + y1) / 2 < H / 2 or ref in ("J3", "TP1")
        b = find_spot((x0 + x1) / 2, (y0 - h / 2) if up else (y1 + h / 2), w, h, allow_rot=False)
        text(nm, b[1], b[2], size=0.9, check=False)

    # referencias
    order = sorted(fps, key=lambda r: (r not in REFPOS, (cyd[r][2] - cyd[r][0]) * (cyd[r][3] - cyd[r][1])))
    far = []
    for ref in order:
        fp = fps[ref]
        rt = fp.Reference()
        if ref.startswith("H"):
            continue
        x0, y0, x1, y1 = cyd[ref]
        w, h = text_dims(ref, 0.8)
        if ref in REFPOS:
            x, y, rot = REFPOS[ref]
            ww, hh = (h, w) if rot else (w, h)
            if not occ_free(x - ww / 2 + 0.1, y - hh / 2 + 0.1, x + ww / 2 - 0.1, y + hh / 2 - 0.1):
                print("  AVISO serigrafia: ref %s pisa algo" % ref)
        else:
            d, x, y, rot, ww, hh = find_spot((x0 + x1) / 2, (y0 + y1) / 2, w, h)
        rt.SetLayer(pcbnew.F_SilkS)
        rt.SetVisible(True)
        rt.SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(0.8), pcbnew.FromMM(0.8)))
        rt.SetTextThickness(pcbnew.FromMM(0.13))
        rt.SetKeepUpright(True)
        rt.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER)
        rt.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_CENTER)
        rt.SetTextAngle(pcbnew.EDA_ANGLE(rot, pcbnew.DEGREES_T))
        rt.SetPosition(V(x, y))
        occ_rect(x - ww / 2, y - hh / 2, x + ww / 2, y + hh / 2)
        dist = max(0.0, max(x0 - x, x - x1), max(y0 - y, y - y1))
        if dist > 2.5:
            far.append((ref, round(dist, 1)))
    if far:
        print("referencias lejos de su componente:", far)

    # ------------------------------------------------------------------ relleno y guardado
    # ZONE_FILLER revienta sobre un BOARD recien creado: guardar, recargar (con proyecto) y rellenar.
    out = os.path.join(HERE, PROJECT + ".kicad_pcb")
    profn = os.path.join(HERE, PROJECT + ".kicad_pro")
    keep = json.load(open(profn))
    write_project()
    pcbnew.SaveBoard(out, board)
    board = pcbnew.LoadBoard(out)
    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())
    pcbnew.SaveBoard(out, board)
    # SaveBoard reescribe el .kicad_pro (vacia "sheets" y las netclasses): restaurar lo del esquematico
    pro = json.load(open(profn))
    for k in ("sheets", "schematic", "text_variables", "libraries"):
        if k in keep:
            pro[k] = keep[k]
    json.dump(pro, open(profn, "w"), indent=2)
    write_project()
    lens = {}
    for (net, l, xa, ya, xb, yb, w) in R.tracks:
        lens[net] = lens.get(net, 0) + math.hypot(xb - xa, yb - ya)
    print("pistas=%d vias=%d fallos=%d  (%.0fs)" % (len(R.tracks), len(R.vias), len(R.fail), time.time() - t0))
    for net in SENSITIVE:
        print("  %-10s %.1f mm" % (net, lens.get(net, 0)))
    if R.fail:
        print("FALLOS:", R.fail)
        sys.exit(2)


def write_project():
    """Mezcla las reglas de diseno en maghead_afe.kicad_pro sin tocar lo del esquematico."""
    fn = os.path.join(HERE, PROJECT + ".kicad_pro")
    pro = json.load(open(fn))
    b = pro.setdefault("board", {})
    ds = b.setdefault("design_settings", {})
    ds.setdefault("defaults", {})
    ds.setdefault("rules", {}).update({
        "min_clearance": CLR, "min_track_width": 0.15, "min_via_diameter": VIA_D,
        "min_via_annular_width": 0.15, "min_through_hole_diameter": VIA_DRILL,
        "min_copper_edge_clearance": EDGE, "min_hole_clearance": 0.25, "min_hole_to_hole": 0.25,
        "min_connection": 0.0, "min_microvia_diameter": 0.2, "min_microvia_drill": 0.1,
        "min_resolved_spokes": 2, "min_silk_clearance": 0.0, "min_text_height": 0.7,
        "min_text_thickness": 0.1, "solder_mask_to_copper_clearance": 0.0,
        "use_height_for_length_calcs": True,
    })
    ds["track_widths"] = [0.0, W_SIG, W_PWR]
    ds["via_dimensions"] = [{"diameter": 0.0, "drill": 0.0}, {"diameter": VIA_D, "drill": VIA_DRILL}]
    ns = pro.setdefault("net_settings", {})
    classes = ns.setdefault("classes", [])
    default = None
    for c in classes:
        if c.get("name") == "Default":
            default = c
    if default is None:
        default = {"name": "Default"}
        classes.insert(0, default)
    default.update({"clearance": CLR, "track_width": W_SIG, "via_diameter": VIA_D, "via_drill": VIA_DRILL})
    classes[:] = [c for c in classes if c.get("name") != "Power"]
    classes.append({"name": "Power", "clearance": CLR, "track_width": W_PWR, "via_diameter": VIA_D,
                    "via_drill": VIA_DRILL, "priority": 0, "pcb_color": "rgba(0, 0, 0, 0.000)",
                    "schematic_color": "rgba(0, 0, 0, 0.000)", "bus_width": 12, "wire_width": 6,
                    "line_style": 0, "diff_pair_gap": 0.25, "diff_pair_via_gap": 0.25, "diff_pair_width": 0.2,
                    "microvia_diameter": 0.3, "microvia_drill": 0.1})
    ns["netclass_patterns"] = [{"netclass": "Power", "pattern": p} for p in ("GND", "+3V3A", "/+3V3C", "VBUS")]
    ns.setdefault("meta", {"version": 4})
    json.dump(pro, open(fn, "w"), indent=2)


if __name__ == "__main__":
    main()
