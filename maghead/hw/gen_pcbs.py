#!/usr/bin/env python3
"""
Generador parametrico de las PCBs experimentales MagHead rev A.

Escribe archivos .kicad_pcb (formato KiCad 8, se abren y regraban con KiCad 9):
  coupon_H/maghead_H.kicad_pcb     cupon hibrido: 2 sitios, bobinas gemelas en 3 capas + ranuras
  coupon_A/maghead_A.kicad_pcb     cupon de pistas al aire (referencia / fluxometro)
  fixture/maghead_base.kicad_pcb   placa base: lenguetas de presion + 2 compuertas opticas
  fixture/maghead_spacer.kicad_pcb separador / guia de canto (define la altura de ranura)

Sistema de coordenadas de diseno (mm):
  x = direccion de deslizamiento de la tarjeta
  z = transversal; z = 0 es el canto de referencia de la tarjeta (borde de la guia),
      la tarjeta ocupa z < 0.  Pista 1 en z = -7.06, pista 2 en z = -10.36 (lineas centrales).
  KiCad: X = 100 + x ; Y = 100 - z.   F.Cu = cara que mira a la tarjeta.

Ademas del DRC de KiCad se hace aqui una verificacion geometrica propia de las bobinas,
porque toda la bobina es UNA red y el DRC no puede ver cortos entre espiras.
"""
import json, math, os, uuid, itertools

HERE = os.path.dirname(os.path.abspath(__file__))
X0, Y0 = 100.0, 100.0
T1_Z, T2_Z = -7.06, -10.36           # lineas centrales ISO 7811 (Q-Card / MagTek: 0.278" y 0.408")
TRACK_PITCH = 3.30


def U():
    return str(uuid.uuid4())


def kx(x): return round(X0 + x, 4)
def ky(z): return round(Y0 - z, 4)


class Board:
    def __init__(self, name, layers=2, thickness=1.6):
        self.name, self.layers, self.thickness = name, layers, thickness
        self.nets = [""]
        self.items = []
        self.segs = []      # (layer, (x1,z1),(x2,z2), w, net, chain_id, idx)
        self.vias = []      # (x,z,d,drill,net)

    def net(self, n):
        if n not in self.nets:
            self.nets.append(n)
        return self.nets.index(n)

    def seg(self, layer, p1, p2, w, net, chain=None, idx=None):
        if abs(p1[0] - p2[0]) < 1e-9 and abs(p1[1] - p2[1]) < 1e-9:
            return
        self.segs.append((layer, p1, p2, w, net, chain, idx))
        self.items.append(f'(segment (start {kx(p1[0])} {ky(p1[1])}) (end {kx(p2[0])} {ky(p2[1])}) (width {w}) '
                          f'(layer "{layer}") (net {self.net(net)}) (uuid "{U()}"))')

    def path(self, layer, pts, w, net, chain=None):
        for i in range(len(pts) - 1):
            self.seg(layer, pts[i], pts[i + 1], w, net, chain, i)

    def via(self, p, net, d=0.6, drill=0.3):
        self.vias.append((p[0], p[1], d, drill, net))
        self.items.append(f'(via (at {kx(p[0])} {ky(p[1])}) (size {d}) (drill {drill}) (layers "F.Cu" "B.Cu") '
                          f'(net {self.net(net)}) (uuid "{U()}"))')

    def line(self, layer, p1, p2, w=0.1):
        self.items.append(f'(gr_line (start {kx(p1[0])} {ky(p1[1])}) (end {kx(p2[0])} {ky(p2[1])}) '
                          f'(stroke (width {w}) (type solid)) (layer "{layer}") (uuid "{U()}"))')

    def poly_outline(self, layer, pts, w=0.1):
        for i in range(len(pts)):
            self.line(layer, pts[i], pts[(i + 1) % len(pts)], w)

    def fill_poly(self, layer, pts):
        s = " ".join(f"(xy {kx(x)} {ky(z)})" for x, z in pts)
        self.items.append(f'(gr_poly (pts {s}) (stroke (width 0) (type solid)) (fill solid) (layer "{layer}") (uuid "{U()}"))')

    def rect_fill(self, layer, x1, z1, x2, z2):
        self.fill_poly(layer, [(x1, z1), (x2, z1), (x2, z2), (x1, z2)])

    def text(self, layer, txt, p, size=1.0, mirror=None, rot=0):
        if mirror is None:
            mirror = layer.startswith("B.")
        j = " (justify mirror)" if mirror else ""
        r = f" {rot}" if rot else ""
        self.items.append(f'(gr_text "{txt}" (at {kx(p[0])} {ky(p[1])}{r}) (layer "{layer}") (uuid "{U()}") '
                          f'(effects (font (size {size} {size}) (thickness {round(size*0.15,3)})){j}))')

    def footprint(self, ref, value, p, pads, side="B", extra="", attr="smd", refvis=True):
        """pads: lista de strings '(pad ...)' en coordenadas locales KiCad (x derecha, y abajo)"""
        cu = f"{side}.Cu"; silk = f"{side}.SilkS"; fab = f"{side}.Fab"
        mir = " (justify mirror)" if side == "B" else ""
        hide = "" if refvis else " (hide yes)"
        self.items.append(
            f'(footprint "maghead:{value}" (layer "{cu}") (uuid "{U()}") (at {kx(p[0])} {ky(p[1])}) (attr {attr})\n'
            f'  (property "Reference" "{ref}" (at 0 -2.6) (layer "{silk}"){hide} (uuid "{U()}") (effects (font (size 0.8 0.8) (thickness 0.12)){mir}))\n'
            f'  (property "Value" "{value}" (at 0 2.6) (layer "{fab}") (hide yes) (uuid "{U()}") (effects (font (size 0.8 0.8) (thickness 0.12)){mir}))\n'
            + "\n".join("  " + s for s in pads) + ("\n  " + extra if extra else "") + "\n)")

    def smd_pad(self, num, lx, ly, sx, sy, net, side="B"):
        n = f' (net {self.net(net)} "{net}")' if net else ""
        return (f'(pad "{num}" smd roundrect (at {lx} {ly}) (size {sx} {sy}) (layers "{side}.Cu" "{side}.Mask" "{side}.Paste") '
                f'(roundrect_rratio 0.15){n} (uuid "{U()}"))')

    def wire_pad(self, ref, p, sx, sz, net, label=None):
        n = f' (net {self.net(net)} "{net}")' if net else ""
        pad = (f'(pad "1" smd roundrect (at 0 0) (size {sx} {sz}) (layers "B.Cu" "B.Mask") (roundrect_rratio 0.15){n} (uuid "{U()}"))')
        self.footprint(ref, "WirePad", p, [pad], refvis=False, attr="smd exclude_from_pos_files")
        if label:
            self.text("B.SilkS", label, (p[0], p[1] + sz / 2 + 0.9), 0.8)

    def npth(self, p, d, d2=None, ref="H"):
        """taladro o ranura no metalizada; d2 = longitud en z (ovalo) si se da; d2x = en x"""
        if d2 is None:
            pad = f'(pad "" np_thru_hole circle (at 0 0) (size {d} {d}) (drill {d}) (layers "*.Cu" "*.Mask") (uuid "{U()}"))'
        else:
            pad = f'(pad "" np_thru_hole oval (at 0 0) (size {d} {d2}) (drill oval {d} {d2}) (layers "*.Cu" "*.Mask") (uuid "{U()}"))'
        self.footprint(ref, "NPTH", p, [pad], side="F", refvis=False, attr="exclude_from_pos_files exclude_from_bom")

    def outline_rect(self, x1, z1, x2, z2, r=1.5):
        pts = [(x1 + r, z1), (x2 - r, z1), (x2, z1 + r), (x2, z2 - r), (x2 - r, z2), (x1 + r, z2), (x1, z2 - r), (x1, z1 + r)]
        cs = [(x2 - r, z1 + r), (x2 - r, z2 - r), (x1 + r, z2 - r), (x1 + r, z1 + r)]
        for i in range(4):
            self.line("Edge.Cuts", pts[2 * i], pts[2 * i + 1])
            a, b, c = pts[2 * i + 1], pts[(2 * i + 2) % 8], cs[i]
            ang = math.atan2(a[1] - c[1], a[0] - c[0]) + math.atan2(b[1] - c[1], b[0] - c[0])
            am = math.atan2(math.sin(ang / 2) if False else (a[1] + b[1] - 2 * c[1]), (a[0] + b[0] - 2 * c[0]))
            m = (c[0] + r * math.cos(am), c[1] + r * math.sin(am))
            self.items.append(f'(gr_arc (start {kx(a[0])} {ky(a[1])}) (mid {kx(m[0])} {ky(m[1])}) (end {kx(b[0])} {ky(b[1])}) '
                              f'(stroke (width 0.1) (type solid)) (layer "Edge.Cuts") (uuid "{U()}"))')

    def write(self, path, title, comment=""):
        cu = [(0, "F.Cu")] + ([(1, "In1.Cu"), (2, "In2.Cu")] if self.layers == 4 else []) + [(31, "B.Cu")]
        lay = "\n".join(f'    ({i} "{n}" signal)' for i, n in cu)
        lay += """
    (34 "B.Paste" user) (35 "F.Paste" user) (36 "B.SilkS" user "B.Silkscreen") (37 "F.SilkS" user "F.Silkscreen")
    (38 "B.Mask" user) (39 "F.Mask" user) (40 "Dwgs.User" user "User.Drawings") (41 "Cmts.User" user "User.Comments")
    (44 "Edge.Cuts" user) (45 "Margin" user) (46 "B.CrtYd" user "B.Courtyard") (47 "F.CrtYd" user "F.Courtyard")
    (48 "B.Fab" user) (49 "F.Fab" user)"""
        nets = "\n".join(f'  (net {i} "{n}")' for i, n in enumerate(self.nets))
        body = "\n".join("  " + s for s in self.items)
        txt = f"""(kicad_pcb (version 20240108) (generator "maghead_gen_pcbs") (generator_version "8.0")
  (general (thickness {self.thickness}) (legacy_teardrops no))
  (paper "A4")
  (title_block (title "{title}") (rev "A") (company "Electronic Cats") (comment 1 "{comment}") (comment 2 "Generado por hw/gen_pcbs.py - prototipo de laboratorio"))
  (layers
{lay}
  )
  (setup (pad_to_mask_clearance 0.05) (allow_soldermask_bridges_in_footprints no))
{nets}
{body}
)
"""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "w").write(txt)


# ------------------------------------------------------------------ bobina
COIL = dict(n=12, ax=0.9, az=2.75, p=0.254, w=0.127, zv=2.15, via_d=0.6, via_drill=0.3,
            slot_w=1.0, slot_l=3.0, v3dx=0.8)


def spiral(c=COIL):
    n, ax, az, p, zv = c["n"], c["ax"], c["az"], c["p"], c["zv"]
    pts = [(0.0, zv), (0.0, az)]
    for k in range(n):
        a, b = ax + k * p, az + k * p
        pts += [(a, b), (a, -b), (-a, -b), (-a, b + p)]
    return pts


def tf(pts, mx=False, rot=False, cx=0.0, cz=0.0, flip=False):
    out = []
    for x, z in pts:
        if mx: x = -x
        if rot: x, z = -x, -z
        if flip: x = -x            # espejo de toda la bobina (bobina izquierda)
        out.append((round(cx + x, 4), round(cz + z, 4)))
    return out


def coil(b, cx, cz, net, flip, tag, c=COIL):
    """Bobina de 3 capas (In1, In2, B.Cu) alrededor de una ranura. Devuelve (terminal_In1, via_salida, cadena ordenada)"""
    P = spiral(c)
    n, p = c["n"], c["p"]
    a_out = c["ax"] + (n - 1) * p
    b_n = c["az"] + n * p
    k = dict(cx=cx, cz=cz, flip=flip)
    in1 = tf(P, **k)                       # T .. via1  (recorrido de afuera hacia adentro = invertido)
    in2 = tf(P, mx=True, **k)
    bcu = tf(P, rot=True, **k)
    v1 = tf([(0, c["zv"])], **k)[0]
    v2 = tf([(0, -c["zv"])], **k)[0]
    v3 = tf([(a_out + c["v3dx"], b_n)], **k)[0]
    link = tf([(a_out + c["v3dx"], b_n), (a_out + c["v3dx"], -b_n), (a_out, -b_n)], **k)
    b.path("In1.Cu", in1, c["w"], net, tag + "in1")
    b.path("In2.Cu", in2 + [v3], c["w"], net, tag + "in2")
    b.path("B.Cu", link, c["w"], net, tag + "lk")
    b.path("B.Cu", bcu, c["w"], net, tag + "b")
    for v in (v1, v2, v3):
        b.via(v, net, c["via_d"], c["via_drill"])
    b.npth((cx, cz), c["slot_w"], c["slot_l"], ref="SLOT")
    # cadena electrica ordenada: T -> in1 -> v1 -> in2 -> v3 -> link -> bcu(inv) -> v2
    chain = in1[::-1] + in2[1:] + [v3] + link[1:] + bcu[::-1][1:]
    return in1[-1], v2, chain


def signed_area(pts):
    return 0.5 * sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts)))


def head_site(b, x0, zt, net, tag, Xc=6.0, c=COIL, x_exit=1.6):
    """Cabezal: bobina L (espejada) en x0-Xc y bobina R en x0+Xc, en serie y en oposicion
    (flujo que sube por una ranura y baja por la otra se suma; campo uniforme se cancela)."""
    w = c["w"]
    b_n = c["az"] + c["n"] * c["p"]
    TL, v2L, chL = coil(b, x0 - Xc, zt, net, True, tag + "L", c)
    TR, v2R, chR = coil(b, x0 + Xc, zt, net, False, tag + "R", c)
    zl = zt - c["zv"]
    # enlace L->R : F.Cu en x (insensible a magnetizacion longitudinal), B.Cu en z (0.8 mm de profundidad)
    VL = (x0 - x_exit, zl); VT = (TR[0], round(zt + b_n + 0.7, 4))
    b.path("F.Cu", [v2L, VL], w, net, tag + "f1"); b.via(VL, net)
    lk = [VL, (x0 - x_exit, VT[1]), VT]
    b.path("B.Cu", lk, w, net, tag + "lk2"); b.via(VT, net)
    b.path("In1.Cu", [VT, TR], w, net, tag + "t")
    # salida de R
    VR = (x0 + x_exit, zl)
    b.path("F.Cu", [v2R, VR], w, net, tag + "f2"); b.via(VR, net)
    zpad = 2.5
    VP = (x0 + x_exit, zpad); VN = (TL[0], zpad)
    b.path("In2.Cu", [VR, VP], w, net, tag + "p"); b.via(VP, net)
    b.path("In1.Cu", [TL, VN], w, net, tag + "n"); b.via(VN, net)
    b.wire_pad(f"J{tag}N", (x0 - 3.0, zpad), 2.6, 2.6, net, "N")
    b.wire_pad(f"J{tag}P", (x0 + 2.3, zpad), 2.6, 2.6, net, "P")
    # marcas de la linea del entrehierro (cobre flotante bajo mascara, fuera del ancho de la cinta)
    for s in (1, -1):
        b.seg("F.Cu", (x0, zt + s * 3.3), (x0, zt + s * 4.3), 0.15, "", tag + "mk")
    # cadena completa N -> P para metricas
    full = [VN] + chL + [VL] + lk[1:] + [TR] + chR[1:] + [VR, VP]
    area_net = signed_area(full)
    area_L = signed_area(chL); area_R = signed_area(chR)
    length = sum(math.dist(full[i], full[i + 1]) for i in range(len(full) - 1))
    return dict(tag=tag, x0=x0, zt=zt, turns_total=2 * 3 * c["n"], length_mm=round(length, 1),
                turn_area_L_mm2=round(area_L, 1), turn_area_R_mm2=round(area_R, 1),
                net_uncompensated_area_mm2=round(area_net, 2),
                rejection_uniform_field_dB=round(20 * math.log10(abs(area_net) / abs(area_L)), 1) if area_net else None)


# ------------------------------------------------------------------ verificacion geometrica propia
def seg_dist(a1, a2, b1, b2):
    def pd(p, q1, q2):
        vx, vz = q2[0] - q1[0], q2[1] - q1[1]
        L2 = vx * vx + vz * vz
        t = 0 if L2 == 0 else max(0, min(1, ((p[0] - q1[0]) * vx + (p[1] - q1[1]) * vz) / L2))
        return math.hypot(p[0] - q1[0] - t * vx, p[1] - q1[1] - t * vz)
    def cross(o, a, b): return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    d1, d2, d3, d4 = cross(b1, b2, a1), cross(b1, b2, a2), cross(a1, a2, b1), cross(a1, a2, b2)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)) and d1 * d2 != 0 and d3 * d4 != 0:
        return 0.0
    return min(pd(a1, b1, b2), pd(a2, b1, b2), pd(b1, a1, a2), pd(b2, a1, a2))


def geom_check(b, min_gap, same_net=False):
    """Distancia cobre-cobre minima entre segmentos de la misma capa que NO comparten un extremo,
    y entre vias y segmentos que no terminan en la via. Devuelve (min_encontrado, n_violaciones, lista)."""
    viol = []; mn = 1e9
    by_layer = {}
    for s in b.segs:
        by_layer.setdefault(s[0], []).append(s)
    for layer, ss in by_layer.items():
        for s1, s2 in itertools.combinations(ss, 2):
            if {s1[1], s1[2]} & {s2[1], s2[2]}:
                continue
            if s1[4] == s2[4] and s1[4] and not same_net:
                continue
            g = seg_dist(s1[1], s1[2], s2[1], s2[2]) - (s1[3] + s2[3]) / 2
            mn = min(mn, g)
            if g < min_gap - 1e-6:
                viol.append((layer, s1[1], s1[2], s2[1], s2[2], round(g, 4)))
        for (vx, vz, d, dr, net) in b.vias:
            for s in ss:
                if math.dist((vx, vz), s[1]) < 1e-6 or math.dist((vx, vz), s[2]) < 1e-6:
                    continue
                if net == s[4] and not same_net:
                    continue
                g = seg_dist((vx, vz), (vx, vz), s[1], s[2]) - d / 2 - s[3] / 2
                mn = min(mn, g)
                if g < min_gap - 1e-6:
                    viol.append((layer, "via", (vx, vz), s[1], s[2], round(g, 4)))
    for v1, v2 in itertools.combinations(b.vias, 2):
        g = math.dist(v1[:2], v2[:2]) - (v1[2] + v2[2]) / 2
        mn = min(mn, g)
        if g < min_gap - 1e-6:
            viol.append(("via-via", v1[:2], v2[:2], round(g, 4)))
    return round(mn, 4), len(viol), viol[:10]


# ------------------------------------------------------------------ elementos comunes de montaje
COUPON = dict(x1=-28.0, x2=28.0, z1=-18.0, z2=14.0)
M3_X = (-19.0, 0.0, 19.0); M3_Z = 7.0
DOWEL_X = (-26.0, 26.0); DOWEL_Z = 3.0


def coupon_mech(b, name):
    c = COUPON
    b.outline_rect(c["x1"], c["z1"], c["x2"], c["z2"])
    for x in M3_X:                      # ranuras M3: permiten P1, P2 y ajuste libre
        b.npth((x, 8.65), 3.2, 8.5, ref="M3")
    for x in DOWEL_X:                   # P1 (nominal) y P2 (cupon desplazado -3.30 mm en z)
        b.npth((x, DOWEL_Z), 2.1, ref="P1")
        b.npth((x, DOWEL_Z + TRACK_PITCH), 2.1, ref="P2")
        b.text("B.SilkS", "P1", (x - 2.4 * (1 if x > 0 else -1), DOWEL_Z), 0.8)
        b.text("B.SilkS", "P2", (x - 2.4 * (1 if x > 0 else -1), DOWEL_Z + TRACK_PITCH), 0.8)
    b.text("B.SilkS", name, (9.5, 11.0), 0.8)
    b.text("B.SilkS", "B=arriba F=tarjeta", (-9.5, 11.0), 0.8)
    # linea del canto de la tarjeta en posicion P1 y escala lateral (0.5 mm) en serigrafia superior
    b.line("B.SilkS", (c["x1"] + 2, 0), (c["x1"] + 6, 0), 0.15)
    b.line("B.SilkS", (c["x2"] - 6, 0), (c["x2"] - 2, 0), 0.15)
    b.text("B.SilkS", "z=0 (P1)", (c["x2"] - 9.2, -1.0), 0.8)
    for i in range(-6, 7):
        z = i * 0.5
        b.line("B.SilkS", (c["x1"] + 0.6, z), (c["x1"] + (1.8 if i % 2 == 0 else 1.3), z), 0.1)


# ------------------------------------------------------------------ cupon H
def build_H():
    b = Board("maghead_H", layers=4, thickness=0.8)
    coupon_mech(b, "MagHead-H revA EC")
    m = [head_site(b, -12.5, T1_Z, "COIL_S1", "S1"), head_site(b, 12.5, T2_Z, "COIL_S2", "S2")]
    for s in m:
        b.text("B.SilkS", f"{s['tag']}  72 esp.", (s["x0"], 6.4), 0.8)
        b.line("B.SilkS", (s["x0"], s["zt"] - 4.5), (s["x0"], s["zt"] + 4.5), 0.12)      # linea de entrehierro (vista superior)
        b.text("B.SilkS", "GAP", (s["x0"], s["zt"] - 5.4), 0.8)
    b.text("B.SilkS", "S1: P1=T1 P2=T2", (-12.5, -16.9), 0.8)
    b.text("B.SilkS", "S2: P1=T2 P2=T3", (12.5, -2.3), 0.8)
    mn, nv, v = geom_check(b, 0.127, same_net=True)
    b.write(os.path.join(HERE, "coupon_H", "maghead_H.kicad_pcb"), "MagHead cupon H - cabezal hibrido bobina PCB + cinta magnetica blanda",
            "4 capas, 0.8 mm, pista/espacio 0.127/0.127, ENIG")
    return dict(sites=m, min_copper_gap_mm=mn, violations=nv, detail=v, n_segments=len(b.segs), n_vias=len(b.vias))


# ------------------------------------------------------------------ cupon A (pistas al aire)
def build_A():
    b = Board("maghead_A", layers=2, thickness=0.8)
    coupon_mech(b, "MagHead-A revA EC")
    zt = T1_Z
    zpad = 2.5
    info = []

    def leads(xs, va, vb, net, tag):
        # va y vb: vias de los dos extremos del elemento sensor (ambas arriba o arriba/abajo)
        b.via(va, net); b.via(vb, net)
        xa, xb = xs - 0.35, xs + 0.35
        if abs(va[1] - vb[1]) < 1e-6:        # ambos arriba (meandro)
            xa, xb = va[0], vb[0]
            b.path("B.Cu", [va, (xa, 1.0), (xs - 1.5, 1.0), (xs - 1.5, zpad)], 0.15, net, tag + "a")
            b.path("B.Cu", [vb, (xb, 1.0), (xs + 2.2, 1.0), (xs + 2.2, zpad)], 0.15, net, tag + "b")
        else:                                # va arriba, vb abajo: retorno por B.Cu desplazado 0.7 mm en x
            b.path("B.Cu", [va, (va[0], 1.0), (xs - 1.5, 1.0), (xs - 1.5, zpad)], 0.15, net, tag + "a")
            b.path("B.Cu", [vb, (vb[0] + 0.7, vb[1]), (vb[0] + 0.7, 1.0), (xs + 2.2, 1.0), (xs + 2.2, zpad)], 0.15, net, tag + "b")
        b.wire_pad(f"J{tag}A", (xs - 1.5, zpad), 2.2, 2.6, net)
        b.wire_pad(f"J{tag}B", (xs + 2.2, zpad), 2.2, 2.6, net)
        b.text("B.SilkS", tag, (xs + 0.35, 5.0), 0.8)

    def single(xs, w, bare, tag):
        net = "AIR_" + tag
        va, vb = (xs, zt + 1.9), (xs, zt - 1.9)
        b.seg("F.Cu", va, vb, w, net, tag, 0)
        if bare:
            b.rect_fill("F.Mask", xs - 1.0, zt - 1.5, xs + 1.0, zt + 1.5)
        leads(xs, va, vb, net, tag)
        info.append(dict(tag=tag, tipo="pista unica", ancho_mm=w, mascara=not bare, long_sensible_mm=3.8))

    single(-21.0, 0.10, True, "A1")
    single(-14.0, 0.10, False, "A2")
    single(-7.0, 0.20, True, "A3")
    # A4: meandro adaptado a la secuencia de ceros de pista 2 (lambda = 2*25.4/75 = 0.6773 mm -> paso 0.33867)
    xs, N, pitch, w, net = 3.0, 10, 25.4 / 75, 0.15, "AIR_A4"
    xl = [round(xs + (i - (N - 1) / 2) * pitch, 4) for i in range(N)]
    zt_hi, zt_lo = zt + 1.6, zt - 1.6
    pts = [(xl[0], zt + 2.3)]
    for i in range(N):
        pts += [(xl[i], zt_lo), ] if i % 2 == 0 else [(xl[i], zt_hi)]
        if i < N - 1:
            pts += [(xl[i + 1], zt_lo)] if i % 2 == 0 else [(xl[i + 1], zt_hi)]
    pts += [(xl[-1], zt + 2.3)]
    b.path("F.Cu", pts, w, net, "A4")
    b.rect_fill("F.Mask", xl[0] - 0.6, zt - 1.4, xl[-1] + 0.6, zt + 1.4)
    leads(xs, pts[0], pts[-1], net, "A4")
    info.append(dict(tag="A4", tipo="meandro adaptado a ceros de T2", conductores=N, paso_mm=round(pitch, 4), ancho_mm=w, mascara=False))
    b.line("B.SilkS", (-25, zt), (-23.5, zt), 0.12); b.line("B.SilkS", (8, zt), (12, zt), 0.12)
    b.text("B.SilkS", "eje pista: P1=T1 P2=T2", (16.5, zt + 1.2), 0.8)
    b.text("B.SilkS", "A1 0.10 sin masc / A2 0.10 con masc / A3 0.20 sin masc / A4 meandro T2", (0, -15.5), 0.8)
    mn, nv, v = geom_check(b, 0.10)
    b.write(os.path.join(HERE, "coupon_A", "maghead_A.kicad_pcb"), "MagHead cupon A - pistas impresas sin nucleo (referencia absoluta de flujo)",
            "2 capas, 0.8 mm, pista minima 0.10 mm, ENIG obligatorio")
    return dict(patterns=info, min_copper_gap_mm=mn, violations=nv, detail=v)


# ------------------------------------------------------------------ base y separador
BASE = dict(x1=-60.0, x2=60.0, z1=-30.0, z2=14.0)
FIX_M3_X = (-50.0, -19.0, 0.0, 19.0, 50.0)
GATE_X = (-55.0, -35.0); GATE_Z = -19.0
TONGUE = dict(L=20.0, tip=2.0, hw=2.5, slot=1.2, zp=-8.7)


def fixture_holes(b):
    for x in FIX_M3_X:
        b.npth((x, M3_Z), 3.2, ref="M3")
    for x in DOWEL_X:
        b.npth((x, DOWEL_Z), 2.0, ref="DW")


def build_base():
    b = Board("maghead_base", layers=2, thickness=1.0)
    c = BASE
    b.outline_rect(c["x1"], c["z1"], c["x2"], c["z2"], r=2.0)
    fixture_holes(b)
    t = TONGUE
    tongues = []
    for xp in (-12.5, 12.5):            # punto de presion bajo cada sitio del cupon
        xr, xt, zp, hw, s = xp - t["L"], xp + t["tip"], t["zp"], t["hw"], t["slot"]
        pts = [(xr, zp + hw), (xt, zp + hw), (xt, zp - hw), (xr, zp - hw), (xr, zp - hw - s),
               (xt + s, zp - hw - s), (xt + s, zp + hw + s), (xr, zp + hw + s)]
        b.poly_outline("Edge.Cuts", pts)
        b.line("B.SilkS", (xp - 1.5, zp), (xp + 1.5, zp), 0.12); b.line("B.SilkS", (xp, zp - 1.5), (xp, zp + 1.5), 0.12)
        b.text("B.SilkS", "PAD", (xp - 4.5, zp), 0.8)
        E, wd, th = 22e9, 2 * hw * 1e-3, 1.0e-3
        k = E * wd * th ** 3 / (4 * (t["L"] * 1e-3) ** 3)
        tongues.append(dict(x_pad=xp, z_pad=zp, largo_mm=t["L"], ancho_mm=2 * hw, k_N_per_mm_estimada=round(k / 1000, 2)))
    # compuertas opticas ITR8307 montaje inverso (cuerpo abajo, mira hacia arriba por el recorte).
    # Sin buses: 3 pads de cable por compuerta (V = +3V3 via R LED, GND, G = colector).
    # El pull-up del colector se pone en el MCU (pull-up interno o 10k externo).
    for i, gx in enumerate(GATE_X, 1):
        gz = GATE_Z
        cut = [(gx - 1.85, gz - 1.8), (gx + 1.85, gz - 1.8), (gx + 1.85, gz + 1.8), (gx - 1.85, gz + 1.8)]
        b.poly_outline("Edge.Cuts", cut)
        la, out, vin, gnd = f"LED{i}_A", f"GATE{i}", f"V{i}", f"GND{i}"
        # huella vista desde F (KiCad): componente en B => patron de libreria espejado en x.
        # libreria (vista del componente): 1=K (0.9, 2.8) 2=A (0.9,-2.8) 3=C (-0.9, 2.8) 4=E (-0.9,-2.8)
        pads = [b.smd_pad("1", -0.9, 2.8, 1.2, 1.4, gnd), b.smd_pad("2", -0.9, -2.8, 1.2, 1.4, la),
                b.smd_pad("3", 0.9, 2.8, 1.2, 1.4, out), b.smd_pad("4", 0.9, -2.8, 1.2, 1.4, gnd)]
        b.footprint(f"U{i}", "ITR8307_Reverse", (gx, gz), pads)
        pA = (gx - 0.9, gz + 2.8); pK = (gx - 0.9, gz - 2.8); pC = (gx + 0.9, gz - 2.8); pE = (gx + 0.9, gz + 2.8)
        rp = [b.smd_pad("1", 0, -0.825, 0.95, 0.8, vin), b.smd_pad("2", 0, 0.825, 0.95, 0.8, la)]
        b.footprint(f"R{i}", "R_0603_150R", (gx - 0.9, gz + 5.6), rp)
        b.path("B.Cu", [(gx - 0.9, gz + 5.6 - 0.825), pA], 0.3, la)
        b.wire_pad(f"JV{i}", (gx - 0.9, gz + 8.6), 2.2, 2.6, vin, "3V3")
        b.path("B.Cu", [(gx - 0.9, gz + 5.6 + 0.825), (gx - 0.9, gz + 8.6)], 0.3, vin)
        b.wire_pad(f"JK{i}", (gx - 2.3, gz - 5.6), 2.2, 2.6, gnd)
        b.wire_pad(f"JC{i}", (gx + 2.3, gz - 5.6), 2.2, 2.6, out)
        b.text("B.SilkS", "GND", (gx - 3.2, gz - 7.9 - 1.2), 0.8); b.text("B.SilkS", f"G{i}", (gx + 2.3, gz - 3.4), 0.8)
        b.path("B.Cu", [pK, (gx - 0.9, gz - 4.6), (gx - 2.3, gz - 5.6)], 0.3, gnd)
        b.path("B.Cu", [pC, (gx + 0.9, gz - 4.6), (gx + 2.3, gz - 5.6)], 0.3, out)
        b.path("B.Cu", [pE, (gx + 4.4, gz + 2.8), (gx + 4.4, gz - 8.2), (gx - 2.3, gz - 8.2), (gx - 2.3, gz - 5.6)], 0.3, gnd)
    b.text("B.SilkS", "compuertas ITR8307 a 20.00 mm", (-45, -6.5), 0.8)
    b.text("B.SilkS", "MagHead BASE revA  EC   cara B = abajo (componentes); cara F lisa = tarjeta", (12, -27.5), 1.0)
    b.text("B.SilkS", "sentido de deslizamiento  -x  >>>  +x", (25, 11.5), 0.9)
    mn, nv, v = geom_check(b, 0.2)
    b.write(os.path.join(HERE, "fixture", "maghead_base.kicad_pcb"), "MagHead base - lenguetas de presion y compuertas opticas", "2 capas, 1.0 mm")
    return dict(tongues=tongues, gate_spacing_mm=GATE_X[1] - GATE_X[0], min_copper_gap_mm=mn, violations=nv, detail=v)


def build_spacer():
    b = Board("maghead_spacer", layers=2, thickness=1.0)
    b.outline_rect(BASE["x1"], 0.0, BASE["x2"], BASE["z2"], r=0.6)
    fixture_holes(b)
    b.text("F.SilkS", "MagHead SEPARADOR/GUIA revA  EC   1.0 mm   canto guia = borde largo junto a esta marca  vvv", (0, 11.5), 0.9)
    b.text("F.SilkS", "CANTO GUIA (z=0)", (38, 1.4), 0.9)
    b.write(os.path.join(HERE, "fixture", "maghead_spacer.kicad_pcb"), "MagHead separador / guia de canto", "2 capas sin cobre, 1.0 mm (define la altura de ranura)")
    return dict(ancho_mm=BASE["z2"], largo_mm=BASE["x2"] - BASE["x1"])


if __name__ == "__main__":
    rep = dict(coil=COIL, H=build_H(), A=build_A(), base=build_base(), spacer=build_spacer())
    # estimaciones electricas de la bobina (cobre: capas internas 17.5 um, externa 35 um)
    rho = 1.72e-8
    L = rep["H"]["sites"][0]["length_mm"] * 1e-3
    r_in = rho / (COIL["w"] * 1e-3 * 17.5e-6); r_out = rho / (COIL["w"] * 1e-3 * 35e-6)
    rep["H"]["R_dc_ohm_estimada"] = round(L * (2 * r_in + r_out) / 3, 1)
    json.dump(rep, open(os.path.join(HERE, "gen_report.json"), "w"), indent=1)
    print(json.dumps(rep, indent=1))
