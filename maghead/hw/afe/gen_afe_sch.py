#!/usr/bin/env python3
"""Generador del esquematico KiCad 9 del AFE de 2 canales para cabezales magneticos.

Emite maghead_afe.kicad_sch (+ maghead_afe.kicad_pro) a partir de los simbolos de
stock de KiCad extraidos en afe_symbols.kicad_sym (ver extract_syms.py).

Convenciones:
  - Todas las coordenadas de colocacion van en unidades G = 2.54 mm (se permiten
    medios, rejilla real de 1.27 mm).
  - Posicion de pin = centro + T(pin de libreria), con Y de libreria invertida.
  - Las uniones (junction) se calculan automaticamente.
Uso: python3 gen_afe_sch.py
"""
import math
import uuid as _uuid
import json
import os
from sexpr import parse, dump, find, find1, Sym

G = 2.54
PROJECT = "maghead_afe"
HERE = os.path.dirname(os.path.abspath(__file__))
NS = _uuid.UUID("6d616768-6561-645f-6166-655f72657641")
_uid_n = [0]


def uid(tag=""):
    """UUID determinista (salida reproducible entre ejecuciones)."""
    _uid_n[0] += 1
    return str(_uuid.uuid5(NS, "%s#%d" % (tag, _uid_n[0])))


ROOT_UUID = str(_uuid.uuid5(NS, "root"))

# --------------------------------------------------------------------------
# Libreria de simbolos
# --------------------------------------------------------------------------
LIB = {}
for _s in find(parse(open(os.path.join(HERE, "afe_symbols.kicad_sym")).read()), "symbol"):
    LIB[_s[1]] = _s


def lib_pins(lib_id):
    """-> {unidad: [(numero, x, y, tipo, oculto)]}; la unidad 0 es comun."""
    out = {}
    s = LIB[lib_id]
    for sub in find(s, "symbol"):
        unit = int(sub[1].rsplit("_", 2)[1])
        for p in find(sub, "pin"):
            at = find1(p, "at")
            out.setdefault(unit, []).append(
                (find1(p, "number")[1], float(at[1]), float(at[2]), str(p[1]), find1(p, "hide") is not None))
    return out


def lib_prop(lib_id, name):
    for p in find(LIB[lib_id], "property"):
        if p[1] == name:
            return p[2]
    return ""


# --------------------------------------------------------------------------
# Datos de componentes: footprint / MPN / fabricante
# --------------------------------------------------------------------------
FP_R = "Resistor_SMD:R_0603_1608Metric"
FP_C = "Capacitor_SMD:C_0603_1608Metric"
FP_C08 = "Capacitor_SMD:C_0805_2012Metric"
FP_SO8 = "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm"

R_MPN = {  # Yageo RC0603, 1 % (0R: jumper)
    "0R": "RC0603JR-070RL", "10R": "RC0603FR-0710RL", "11R": "RC0603FR-0711RL",
    "47R": "RC0603FR-0747RL", "100R": "RC0603FR-07100RL", "1k": "RC0603FR-071KL",
    "2k": "RC0603FR-072KL", "10k": "RC0603FR-0710KL", "47k": "RC0603FR-0747KL",
    "49.9k": "RC0603FR-0749K9L", "100k": "RC0603FR-07100KL", "200k": "RC0603FR-07200KL",
}
C_MPN = {  # Samsung CL10 (0603) / CL21 (0805); C0G en todo lo que fija respuesta
    "18pF": "CL10C180JB8NNNC", "82pF": "CL10C820JB8NNNC", "390pF": "CL10C391JB8NNNC",
    "470pF": "CL10C471JB8NNNC", "1nF": "CL10C102JB8NNNC", "2.2nF": "CL10C222JB8NNNC",
    "4.7nF": "CL10C472JB8NNNC", "100nF": "CL10B104KB8NNNC", "1uF": "CL10B105KA8NNNC",
    "10uF": "CL21A106KOQNNNE",
}

# --------------------------------------------------------------------------
# Modelo del esquematico
# --------------------------------------------------------------------------
symbols = []      # dicts
wires = []        # ((x1,y1),(x2,y2)) en mm
labels = []       # (name, x, y, angle)
texts = []        # (text, x, y, size, bold, justify)
rects = []        # (x1,y1,x2,y2)
_pwr_n = [0]
_flg_n = [0]


def mm(v):
    return round(v * G, 4)


def P(x, y):
    return (mm(x), mm(y))


class Part:
    def __init__(self, d):
        self.d = d

    def pin(self, num):
        """Extremo electrico del pin (mm)."""
        return self.d["pins"][str(num)]

    def fields(self, ref=None, val=None):
        """ref/val = (dx_mm, dy_mm, justify) relativo al centro, texto horizontal; None = oculto."""
        self.d["ref_at"] = ref
        self.d["val_at"] = val
        return self


def xform(px, py, rot, mirror):
    """Coordenada de libreria (Y arriba) -> desplazamiento en hoja (Y abajo)."""
    if mirror == "x":
        py = -py
    elif mirror == "y":
        px = -px
    a = math.radians(rot)
    c, s = round(math.cos(a)), round(math.sin(a))
    rx = px * c - py * s
    ry = px * s + py * c
    return rx, -ry


def place(ref, lib_id, x, y, rot=0, mirror=None, unit=1, value=None, fp=None,
          mpn="", mfr="", dnp=False, ref_at=None, val_at=None):
    cx, cy = P(x, y)
    pins = {}
    allp = lib_pins(lib_id)
    for u in (0, unit):
        for num, px, py, typ, hid in allp.get(u, []):
            dx, dy = xform(px, py, rot, mirror)
            pins[num] = (round(cx + dx, 4), round(cy + dy, 4))
    d = dict(ref=ref, lib_id=lib_id, x=cx, y=cy, rot=rot, mirror=mirror, unit=unit,
             value=value if value is not None else lib_prop(lib_id, "Value"),
             fp=fp if fp is not None else lib_prop(lib_id, "Footprint"),
             mpn=mpn, mfr=mfr, dnp=dnp, pins=pins, ref_at=ref_at, val_at=val_at,
             allpins=[n for u in sorted(allp) for (n, *_r) in allp[u]])
    symbols.append(d)
    return Part(d)


def wire(*pts):
    """Polilinea ortogonal; los puntos son tuplas en mm (p.ej. de Part.pin o P())."""
    for a, b in zip(pts, pts[1:]):
        assert abs(a[0] - b[0]) < 1e-6 or abs(a[1] - b[1]) < 1e-6, ("wire no ortogonal", a, b)
        if a != b:
            wires.append((a, b))


def label(name, pt, angle=0):
    labels.append((name, pt[0], pt[1], angle))


def text(s, x, y, size=1.27, bold=False, just="left top"):
    texts.append((s, mm(x), mm(y), size, bold, just))


def block(title, x1, y1, x2, y2):
    rects.append((mm(x1), mm(y1), mm(x2), mm(y2)))
    text(title, x1 + 0.6, y1 + 0.5, size=2.2, bold=True)


def power(net, pt):
    """Simbolo de alimentacion con su pin en pt. GND apunta abajo; el resto arriba."""
    lib = {"GND": "power:GND", "+3V3A": "power:+3.3VA", "VBUS": "power:VBUS"}[net]
    _pwr_n[0] += 1
    p = place("#PWR%03d" % _pwr_n[0], lib, pt[0] / G, pt[1] / G, value=net)
    p.fields(ref=None, val=(0, 3.81, "c") if net == "GND" else (0, -3.556, "c"))
    return p


def pwr_flag(pt):
    _flg_n[0] += 1
    p = place("#FLG%03d" % _flg_n[0], "power:PWR_FLAG", pt[0] / G, pt[1] / G)
    p.fields(ref=None, val=(0, -3.81, "c"))
    return p


# ---- ayudantes de componentes ------------------------------------------------
def R(ref, val, x, y, horiz=True, dnp=False):
    """Resistencia con pin 1 en (x,y); pin 2 a la derecha (horiz) o abajo."""
    if horiz:
        p = place(ref, "Device:R", x + 1.5, y, rot=90, value=val, fp=FP_R,
                  mpn=R_MPN[val], mfr="Yageo", dnp=dnp)
        p.fields(ref=(-0.5, -2.5, "r"), val=(0.5, -2.5, "l"))
    else:
        p = place(ref, "Device:R", x, y + 1.5, rot=0, value=val, fp=FP_R,
                  mpn=R_MPN[val], mfr="Yageo", dnp=dnp)
        p.fields(ref=(2.0, -1.2, "l"), val=(2.0, 1.2, "l"))
    return p


def C(ref, val, x, y, horiz=True, dnp=False):
    fp = FP_C08 if val == "10uF" else FP_C
    if horiz:
        p = place(ref, "Device:C", x + 1.5, y, rot=90, value=val, fp=fp,
                  mpn=C_MPN[val], mfr="Samsung Electro-Mechanics", dnp=dnp)
        p.fields(ref=(-0.5, -3.4, "r"), val=(0.5, -3.4, "l"))
    else:
        p = place(ref, "Device:C", x, y + 1.5, rot=0, value=val, fp=fp,
                  mpn=C_MPN[val], mfr="Samsung Electro-Mechanics", dnp=dnp)
        p.fields(ref=(2.8, -1.2, "l"), val=(2.8, 1.2, "l"))
    return p


def Cgnd(ref, val, x, ytop, dnp=False):
    """Condensador vertical colgado de (x,ytop) con GND debajo. Devuelve Part."""
    c = C(ref, val, x, ytop + 1, horiz=False, dnp=dnp)
    wire(P(x, ytop), c.pin(1))
    power("GND", c.pin(2))
    return c


OPA = dict(fp=FP_SO8)
IC = {
    "U1": dict(lib="Amplifier_Operational:AD8656", value="AD8656ARZ", mpn="AD8656ARZ", mfr="Analog Devices"),
    "U2": dict(lib="Amplifier_Operational:AD8656", value="AD8656ARZ", mpn="AD8656ARZ", mfr="Analog Devices"),
    "U3": dict(lib="Amplifier_Operational:MCP6002-xSN", value="MCP6002-I/SN", mpn="MCP6002-I/SN", mfr="Microchip"),
    "U4": dict(lib="Comparator:MCP6562", value="MCP6562-E/SN", mpn="MCP6562-E/SN", mfr="Microchip"),
}


def opamp(ref, unit, x, y, minus_top=False):
    """Unidad A/B (1/2) centrada en (x,y). Pines: '+', '-', 'o' via .p()."""
    i = IC[ref]
    p = place(ref, i["lib"], x, y, mirror="x" if minus_top else None, unit=unit,
              value=i["value"], fp=FP_SO8, mpn=i["mpn"], mfr=i["mfr"])
    p.fields(ref=(1.5, -5.8, "l"), val=(1.5, -3.8, "l"))
    nums = {1: ("3", "2", "1"), 2: ("5", "6", "7")}[unit]
    p.plus, p.minus, p.out = p.pin(nums[0]), p.pin(nums[1]), p.pin(nums[2])
    return p


def opamp_pwr(ref, x, y):
    i = IC[ref]
    p = place(ref, i["lib"], x, y, unit=3, value=i["value"], fp=FP_SO8, mpn=i["mpn"], mfr=i["mfr"])
    p.fields(ref=(1.5, -1.3, "l"), val=(1.5, 1.3, "l"))
    p.vp, p.vn = p.pin("8"), p.pin("4")
    return p


def jumper(ref, x, y, horiz=True):
    """Jumper de 2 pines (tira 1x02 2.54) con pin 1 en (x,y)."""
    kw = dict(value="Jumper 1x02", fp="Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical",
              mpn="61300211121", mfr="Wurth Elektronik")
    p = place(ref, "Jumper:Jumper_2_Open", x + 2, y, **kw)
    p.fields(ref=(0, -3.0, "c"), val=None)
    return p


def testpoint(ref, pt, name):
    p = place(ref, "Connector:TestPoint", pt[0] / G, pt[1] / G, value="TP " + name,
              fp="TestPoint:TestPoint_Keystone_5019_Miniature", mpn="5019", mfr="Keystone Electronics")
    p.fields(ref=(1.6, -3.3, "l"), val=None)
    return p


# --------------------------------------------------------------------------
# BLOQUES
# --------------------------------------------------------------------------
def blk_alimentacion(ox, oy):
    def L(x, y):
        return P(ox + x, oy + y)
    block("ALIMENTACION  (VBUS 5 V -> +3V3A, referencia ADC, desacoplos)", ox, oy, ox + 96, oy + 33)
    # --- regulador
    y = 10
    power("VBUS", L(4, y))
    pwr_flag(L(7, y))
    u5 = place("U5", "Regulator_Linear:AP2112K-3.3", ox + 17, oy + y + 1,
               value="AP2112K-3.3", mpn="AP2112K-3.3TRG1", mfr="Diodes Incorporated")
    u5.fields(ref=(0, -8.3, "c"), val=(0, -6.2, "c"))
    wire(L(4, y), u5.pin(1))
    wire(u5.pin(3), L(13, y + 1), L(13, y))
    Cgnd("C20", "1uF", ox + 10, oy + y)
    power("GND", u5.pin(2))
    wire(u5.pin(5), L(36, y))
    Cgnd("C21", "1uF", ox + 24, oy + y)
    Cgnd("C22", "10uF", ox + 28, oy + y)
    testpoint("TP3", L(32, y), "+3V3A")
    power("+3V3A", L(36, y))
    text("LDO 600 mA, ruido tip. 50 uVrms.\nEntrada: VBUS del MCU (J4-1).", ox + 3, oy + 16.5)
    # --- referencia ADC opcional (DNP)
    d3 = place("D3", "Reference_Voltage:LM4040DBZ-3", ox + 48, oy + y + 1.5, rot=90,
               value="LM4040DBZ-3.0", mpn="LM4040C30IDBZR", mfr="Texas Instruments", dnp=True)
    d3.fields(ref=(3.0, -1.2, "l"), val=(3.0, 1.2, "l"))
    wire(L(42, y), L(58, y))
    label("ADC_VREF", L(42, y))
    wire(d3.pin(2), L(48, y + 4))
    power("GND", L(48, y + 4))
    Cgnd("C23", "100nF", ox + 58, oy + y, dnp=True)
    text("Referencia shunt 3.0 V opcional (DNP) para ADC_VREF.\n"
         "Usa la resistencia de 200 ohm que ya existe en la\n"
         "Raspberry Pi Pico entre 3V3 y ADC_VREF.", ox + 42, oy + 16.5)
    # --- desacoplos
    yr, yg = 23, 29

    def group(gx, uref, caps):
        power("+3V3A", L(gx, yr))
        xs = [gx + 2 + 4 * k for k in range(len(caps))]
        xu = xs[-1] + 4
        u = opamp_pwr(uref, ox + xu + 1, oy + yr + 3)
        wire(L(gx, yr), u.vp)
        wire(L(xs[0], yg), u.vn)
        for (cref, cval), xc in zip(caps, xs):
            c = C(cref, cval, ox + xc, oy + yr + 1, horiz=False)
            wire(L(xc, yr), c.pin(1))
            wire(c.pin(2), L(xc, yg))
        wire(L(xs[0], yg), L(xs[0], yg + 1))
        power("GND", L(xs[0], yg + 1))

    group(4, "U1", [("C10", "100nF"), ("C11", "1uF")])
    group(22, "U2", [("C12", "100nF"), ("C13", "1uF")])
    group(40, "U3", [("C32", "100nF")])
    # U4 con filtro RC propio (+3V3C)
    gx = 56
    power("+3V3A", L(gx - 2, yr))
    r40 = R("R40", "10R", ox + gx + 1, oy + yr)
    wire(L(gx - 2, yr), r40.pin(1))
    u4 = opamp_pwr("U4", ox + gx + 23, oy + yr + 3)
    wire(r40.pin(2), u4.vp)
    label("+3V3C", L(gx + 4.5, yr))
    pwr_flag(L(gx + 10, yr))
    for cref, cval, xc in (("C40", "1uF", gx + 13), ("C41", "100nF", gx + 17)):
        c = C(cref, cval, ox + xc, oy + yr + 1, horiz=False)
        wire(L(xc, yr), c.pin(1))
        wire(c.pin(2), L(xc, yg))
    wire(L(gx + 13, yg), u4.vn)
    wire(L(gx + 13, yg), L(gx + 13, yg + 1))
    power("GND", L(gx + 13, yg + 1))
    # TP1 GND + PWR_FLAG
    tp = testpoint("TP1", L(88, yr + 2), "GND")
    wire(L(88, yr + 2), L(88, yr + 5))
    power("GND", L(88, yr + 5))
    wire(L(88, yr + 4), L(92.5, yr + 4), L(92.5, yr + 2))
    pwr_flag(L(92.5, yr + 2))


def blk_vref(ox, oy):
    def L(x, y):
        return P(ox + x, oy + y)
    block("VREF  (1.65 V = +3V3A/2, con buffer)", ox, oy, ox + 40, oy + 33)
    power("+3V3A", L(6, 7))
    r30 = R("R30", "10k", ox + 6, oy + 8, horiz=False)
    r31 = R("R31", "10k", ox + 6, oy + 13, horiz=False)
    wire(L(6, 7), r30.pin(1))
    wire(r30.pin(2), r31.pin(1))
    power("GND", r31.pin(2))
    ua = opamp("U3", 1, ox + 23, oy + 13)
    wire(L(6, 12), ua.plus)
    label("VREF_DIV", L(14, 12))
    Cgnd("C30", "10uF", ox + 12, oy + 12)
    wire(ua.minus, L(19, 14), L(19, 17), L(28, 17), L(28, 13))
    wire(ua.out, L(34, 13))
    testpoint("TP2", L(31, 13), "VREF")
    label("VREF", L(34, 13))
    # unidad B sin uso: seguidor de VREF
    ub = opamp("U3", 2, ox + 23, oy + 25)
    wire(ub.plus, L(17, 24))
    label("VREF", L(17, 24), 180)
    wire(ub.minus, L(19, 26), L(19, 29), L(28, 29), L(28, 25))
    wire(ub.out, L(31, 25))
    label("U3B_NC", L(31, 25))
    text("U3B sin uso: seguidor\nde VREF, salida al aire.", ox + 29.5, oy + 26.5)
    text("Sin condensador en VREF\n(evitar carga capacitiva).", ox + 29.5, oy + 15)


def blk_conectores(ox, oy):
    def L(x, y):
        return P(ox + x, oy + y)
    block("CONECTORES", ox, oy, ox + 46, oy + 33)
    j4 = place("J4", "Connector_Generic:Conn_01x08", ox + 16, oy + 12, value="MCU 1x08",
               fp="Connector_PinHeader_2.54mm:PinHeader_1x08_P2.54mm_Vertical",
               mpn="61300811121", mfr="Wurth Elektronik")
    j4.fields(ref=(0, -10.2, "c"), val=(0, 12.7, "c"))
    wire(j4.pin(1), L(8, 9), L(8, 8))
    power("VBUS", L(8, 8))
    wire(j4.pin(2), L(5, 10), L(5, 18))
    wire(j4.pin(4), L(5, 12))
    power("GND", L(5, 18))
    for n, net in ((3, "ADC_A"), (5, "ADC_B"), (6, "CMP_A"), (7, "CMP_B"), (8, "ADC_VREF")):
        x, y = j4.pin(n)
        wire((x, y), (x - 3 * G, y))
        label(net, (x - 3 * G, y), 180)
    text("J4 (MCU):\n1 VBUS\n2 GND\n3 ADC_A\n4 GND\n5 ADC_B\n6 CMP_A\n7 CMP_B\n8 ADC_VREF", ox + 18.5, oy + 7.5)
    j3 = place("J3", "Connector_Audio:AudioJack3", ox + 31, oy + 12, value="Jack 3.5 mm MONITOR",
               fp="Connector_Audio:Jack_3.5mm_CUI_SJ1-3523N_Horizontal", mpn="SJ1-3523N", mfr="CUI Devices")
    j3.fields(ref=(0, -8.9, "c"), val=(0, -6.4, "c"))
    wire(j3.pin("T"), L(36, 13)); label("MON_A", L(36, 13))
    wire(j3.pin("R"), L(36, 12)); label("MON_B", L(36, 12))
    wire(j3.pin("S"), L(42, 11), L(42, 15))
    power("GND", L(42, 15))
    text("Punta = MON_A, anillo = MON_B,\nmanga = GND.", ox + 27, oy + 16)
    text("J1 / J2 (cabezales A / B) estan dibujados\nen la entrada de cada canal (etapa 1).",
         ox + 3, oy + 26)


def blk_canal(ch, ox, ys, u_unit):
    """Canal completo. ch = 'A'/'B'; ys = fila de senal (G); u_unit = 1 (A) o 2 (B)."""
    n = {"A": 100, "B": 200}[ch]
    top, bot = ys - 28, ys + 20

    def rn(k):
        return "R%d" % (n + k)

    def cn(k):
        return "C%d" % (n + k)

    HP, HN = "HEAD_%s_P" % ch, "HEAD_%s_N" % ch
    INP, FB1, GJ, S1 = "IN%s_P" % ch, "FB1%s" % ch, "G1%s_J" % ch, "S1%s" % ch
    AC, FB2, S2 = "AC_%s" % ch, "FB2%s" % ch, "S2%s" % ch

    # ====================== ETAPA 1 ======================
    def L(x, y):
        return P(ox + x, ys + y)
    block("CANAL %s etapa 1  (entrada cabezal + preamplificador x11 / x102)" % ch,
          ox, top, ox + 60, bot)
    j = place("J1" if ch == "A" else "J2", "Connector_Generic:Conn_01x03", ox + 4, ys + 1, mirror="y",
              value="CABEZAL %s" % ch, fp="Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical",
              mpn="61300311121", mfr="Wurth Elektronik")
    j.fields(ref=(0, -5.1, "c"), val=(0, -7.2, "c"))
    r102 = R(rn(2), "47R", ox + 31, ys)
    wire(j.pin(1), r102.pin(1))
    label(HP, L(6.5, 0))
    wire(j.pin(2), L(8, 1), L(8, 10), L(19, 10))
    label(HN, L(8.5, 10))
    wire(j.pin(3), L(6, 4))
    power("GND", L(6, 4))
    text("1 +\n2 -\n3 malla", ox + 1.2, ys + 3.2)
    r101 = R(rn(1), "10k", ox + 13, ys + 3, horiz=False, dnp=True)
    wire(L(13, 0), r101.pin(1)); wire(r101.pin(2), L(13, 10))
    c101 = C(cn(1), "470pF", ox + 18, ys + 3, horiz=False, dnp=True)
    wire(L(18, 0), c101.pin(1)); wire(c101.pin(2), L(18, 10))
    text("R%d / C%d DNP:\namortiguamiento para\ncabezales comerciales" % (n + 1, n + 1), ox + 9.5, ys + 11)
    r100 = R(rn(0), "0R", ox + 19, ys + 10)
    d = place("D%d" % (n + 1), "Diode:BAV99", ox + 25, ys + 4, mirror="x", value="BAV99",
              mpn="BAV99,215", mfr="Nexperia")
    d.fields(ref=(4.0, -6.2, "l"), val=(4.0, -4.2, "l"))
    wire(d.pin(3), L(25, 0))
    wire(d.pin(1), L(22, 7), L(28, 7), d.pin(2))
    wire(L(25, 7), L(25, 10))
    wire(r100.pin(2), L(28, 10))
    label("VREF", L(28, 10))
    text("Recorte antiparalelo\na VREF (+/-0.6 V)", ox + 26.5, ys + 4.6)
    # entrada op-amp
    u = opamp("U1", u_unit, ox + 47, ys + 1)
    wire(r102.pin(2), u.plus)
    label(INP, L(34.5, 0))
    c102 = C(cn(2), "1nF", ox + 38, ys + 2, horiz=False, dnp=True)
    wire(L(38, 0), c102.pin(1))
    wire(c102.pin(2), L(38, 7))
    label("VREF", L(38, 7), 270)
    # realimentacion
    r103 = R(rn(3), "1k", ox + 46, ys + 7)
    c103 = C(cn(3), "1nF", ox + 46, ys + 10)
    wire(u.minus, L(43, 2), L(43, 13))
    wire(L(43, 7), r103.pin(1)); wire(L(43, 10), c103.pin(1))
    wire(r103.pin(2), L(52, 7)); wire(c103.pin(2), L(52, 10), L(52, 1))
    r104 = R(rn(4), "100R", ox + 40, ys + 13, horiz=False)
    r105 = R(rn(5), "11R", ox + 45, ys + 13)
    wire(r104.pin(1), r105.pin(1))
    label(FB1, L(40.5, 13))
    wire(r104.pin(2), L(40, 17))
    label("VREF", L(40, 17), 270)
    jp = jumper("JP%d" % (n + 1), ox + 52, ys + 13)
    wire(r105.pin(2), jp.pin(1))
    label(GJ, L(48.5, 13))
    wire(jp.pin(2), L(57, 13))
    label("VREF", L(57, 13))
    text("JP%d: x102 cerrado / x11 abierto" % (n + 1), ox + 45, ys + 15.2)
    # salida S1 -> etapa 2
    x2 = ox + 61
    testpoint("TP%d" % (n + 1), L(55, 1), S1)
    label(S1, L(52.5, 1))

    # ====================== ETAPA 2 ======================
    y2 = ys + 1

    def M(x, y):
        return P(x2 + x, y2 + y)
    block("CANAL %s etapa 2  (HPF 16 Hz + inversor de ganancia seleccionable)" % ch,
          x2, top, x2 + 59, bot)
    c104 = C(cn(4), "10uF", x2 + 3, y2)
    wire(u.out, c104.pin(1))
    r106 = R(rn(6), "1k", x2 + 10, y2)
    wire(c104.pin(2), r106.pin(1))
    label(AC, M(6.5, 0))
    u2 = opamp("U2", u_unit, x2 + 21, y2 + 1, minus_top=True)
    wire(r106.pin(2), u2.minus)
    label(FB2, M(15.5, 0))
    wire(u2.plus, M(16, 2))
    label("VREF", M(16, 2), 180)
    # ramas de realimentacion
    branches = [(7, "200k", "18pF", None), (8, "49.9k", "82pF", 2), (9, "10k", "390pF", 3),
                (10, "2k", "2.2nF", 4)]
    for i, (k, rv, cv, jk) in enumerate(branches):
        yr_, yc_ = -7 - 6 * i, -4 - 6 * i
        r = R(rn(k), rv, x2 + 18, y2 + yr_)
        c = C(cn(k), cv, x2 + 18, y2 + yc_)
        wire(M(15, yr_), r.pin(1)); wire(M(15, yc_), c.pin(1))
        if jk is None:
            wire(r.pin(2), M(32, yr_)); wire(c.pin(2), M(32, yc_))
        else:
            wire(c.pin(2), M(22, yc_), M(22, yr_))
            jp = jumper("JP%d" % (n + jk), x2 + 27, y2 + yr_)
            wire(r.pin(2), jp.pin(1))
            label("%s_J%d" % (FB2, jk - 1), M(22.5, yr_))
            wire(jp.pin(2), M(32, yr_))
    wire(M(15, 0), M(15, -25))
    wire(M(32, 1), M(32, -25))
    text("Rf fija 200k (x200).\nCerrar jumpers para\nbajar ganancia:\nJP%d: +49.9k || 82pF\nJP%d: +10k || 390pF\nJP%d: +2k || 2.2nF\n(ver tabla en NOTAS)"
         % (n + 2, n + 3, n + 4), x2 + 2, y2 - 24)
    # salida
    r111 = R(rn(11), "1k", x2 + 39, y2 + 1)
    wire(u2.out, r111.pin(1))
    label(S2, M(32.5, 1))
    testpoint("TP%d" % (n + 2), M(35, 1), S2)
    wire(r111.pin(2), M(47, 1))
    label("ADC_%s" % ch, M(47, 1))
    Cgnd(cn(11), "2.2nF", x2 + 44, y2 + 1)
    text("Filtro anti-alias 34 kHz", x2 + 38, y2 + 7.6)
    # monitor
    c112 = C(cn(12), "10uF", x2 + 39, y2 - 6)
    wire(M(37, 1), M(37, -6), c112.pin(1))
    r112 = R(rn(12), "100R", x2 + 47, y2 - 6)
    wire(c112.pin(2), r112.pin(1))
    label("MON_%s_C" % ch, M(42.5, -6))
    wire(r112.pin(2), M(55, -6))
    label("MON_%s" % ch, M(55, -6))
    r113 = R(rn(13), "100k", x2 + 52, y2 - 5, horiz=False)
    wire(M(52, -6), r113.pin(1))
    power("GND", r113.pin(2))
    text("Salida de monitor (jack J3)", x2 + 39, y2 - 11)

    # ====================== COMPARADOR ======================
    x3 = x2 + 60
    yc = ys

    def K(x, y):
        return P(x3 + x, yc + y)
    block("COMPARADOR %s  (histeresis ajustable)" % ch, x3, top, x3 + 34, bot)
    r114 = R(rn(14), "10k", x3 + 6, yc)
    wire(K(2, 0), r114.pin(1))
    label(S2, K(2, 0))
    u4 = opamp("U4", u_unit, x3 + 18, yc + 1)
    wire(r114.pin(2), u4.plus)
    label("CMP%s_P" % ch, K(11.5, 0))
    wire(u4.minus, K(13, 2))
    label("VREF", K(13, 2), 180)
    r115 = R(rn(15), "47k", x3 + 12, yc - 6)
    wire(K(11, 0), K(11, -6), r115.pin(1))
    rv = place("RV%d" % (n + 1), "Device:R_Potentiometer_Trim", x3 + 20.5, yc - 6, rot=90, value="500k",
               fp="Potentiometer_THT:Potentiometer_Bourns_3296W_Vertical", mpn="3296W-1-504LF", mfr="Bourns")
    rv.fields(ref=(0, 3.0, "c"), val=(0, 5.0, "c"))
    wire(r115.pin(2), rv.pin(1))
    label("CMP%s_H" % ch, K(15.5, -6))
    wire(rv.pin(2), K(20.5, -8.5), K(23, -8.5), K(23, -6))
    wire(rv.pin(3), K(25, -6), K(25, 1))
    wire(u4.out, K(29, 1))
    label("CMP_%s" % ch, K(29, 1))
    text("Histeresis (ref. a %s):\n+/-351 mV (RV min) ... +/-30 mV (RV max)\nSalida push-pull directa a J4." % S2,
         x3 + 3, yc + 6)


def notas(x, y):
    block("NOTAS", x, y, x + 66, y + 58)
    sz = 1.5
    row = 1.0          # paso de linea en G para size 1.5 (2.54 mm)

    def para(lines, yy):
        text("\n".join(lines), x + 1.5, yy, size=sz)
        return yy + row * len(lines) + 0.8

    def table(cols, rows, yy):
        for (cx, _h), col in zip(cols, zip(*rows)):
            text("\n".join(col), x + 1.5 + cx, yy, size=sz)
        return yy + row * len(rows) + 0.8

    yy = y + 3.5
    yy = para(["Prototipo de laboratorio rev A - no liberado para fabricacion"], yy)
    yy = para(["AFE de 2 canales para cabezales magneticos experimentales. Alimentacion unica",
               "+3V3A; toda la senal esta referida a VREF = 1.65 V. Una sola masa GND."], yy)
    yy = para(["GANANCIA ETAPA 1 (no inversor, G1 = 1 + R103/Rg); canal B: JP201"], yy) - 0.8
    yy = table([(1, ""), (18, ""), (40, "")],
               [("JP101 abierto", "Rg = R104 = 100R", "G1 = x11.00"),
                ("JP101 cerrado", "Rg = 100R || 11R = 9.910R", "G1 = x101.9  (x102)")], yy)
    yy = para(["GANANCIA ETAPA 2 (inversor, G2 = Rf/R106, R106 = 1k); canal B: JP202/203/204"], yy) - 0.8
    yy = table([(1, ""), (22, ""), (34, ""), (44, ""), (53, "")],
               [("Jumpers cerrados", "Rf (paralelo)", "G2", "Cf total", "Polo LPF"),
                ("ninguno", "200.00k", "x200.0", "18 pF", "44.2 kHz"),
                ("JP102", "39.936k", "x39.94", "100 pF", "39.9 kHz"),
                ("JP103", "9.5238k", "x9.524", "408 pF", "41.0 kHz"),
                ("JP104", "1.9802k", "x1.980", "2218 pF", "36.2 kHz"),
                ("JP102+JP103", "7.9974k", "x7.997", "490 pF", "40.6 kHz"),
                ("JP102+JP103+JP104", "1.5999k", "x1.600", "2690 pF", "37.0 kHz")], yy) - 0.8
    yy = para(["Nominales x200 / x40 / x9.5 / x1.9 = un solo jumper cerrado cada vez.",
               "Acumulando jumpers se obtiene x40 / x8.0 / x1.6."], yy)
    yy = para(["RESPUESTA EN FRECUENCIA"], yy) - 0.8
    yy = table([(1, ""), (12, ""), (44, "")],
               [("Paso alto", "C104 x R106 = 10uF x 1k", "15.9 Hz  (16 Hz)"),
                ("Paso bajo", "Rf x Cf etapa 2 (ver tabla)", "~40 kHz"),
                ("", "R103 x C103 etapa 1 = 1k x 1nF", "159 kHz"),
                ("", "R111 x C111 salida ADC = 1k x 2.2nF", "72.3 kHz")], yy) - 0.8
    yy = para(["Detalle y balance de ruido: afe_analysis.py / afe_analysis.md"], yy)
    yy = para(["COMPARADOR (U4 MCP6562, alimentado de +3V3C = +3V3A via R40/C40/C41)",
               "  Umbrales en S2x = VREF +/- 1.65 V x R114/(R115+RV101)",
               "  RV = 0 : +/-351 mV (702 mV de ancho);  RV = 500k : +/-30.2 mV (60.3 mV de ancho)"], yy)
    yy = para(["DNP (no montar por defecto): R101, C101, C102, R201, C201, C202, D3, C23.",
               "R100/R200 (0R) unen HEAD_x_N a VREF: el cabezal flota sobre VREF.",
               "Condensadores que fijan la respuesta: C0G/NP0. C104/C112 (10uF): X5R."], yy)


# --------------------------------------------------------------------------
def build():
    blk_alimentacion(6, 6)
    blk_vref(103, 6)
    blk_conectores(144, 6)
    blk_canal("A", 6, 70, 1)
    blk_canal("B", 6, 120, 2)
    notas(162, 42)


# --------------------------------------------------------------------------
# Emision
# --------------------------------------------------------------------------
def junctions():
    """Uniones donde concurren >=3 conexiones (extremos de hilo, pines, paso de hilo)."""
    pts = {}
    for a, b in wires:
        for p in (a, b):
            pts.setdefault(p, [0, 0])[0] += 1
    for s in symbols:
        for num, p in s["pins"].items():
            pts.setdefault(p, [0, 0])[1] += 1
    out = []
    for p, (nw, npin) in pts.items():
        interior = 0
        for a, b in wires:
            if p == a or p == b:
                continue
            if a[0] == b[0] == p[0] and min(a[1], b[1]) < p[1] < max(a[1], b[1]):
                interior += 1
            elif a[1] == b[1] == p[1] and min(a[0], b[0]) < p[0] < max(a[0], b[0]):
                interior += 1
        if nw + npin + 2 * interior >= 3:
            out.append(p)
    return out


def split_wires(extra_pts):
    """Parte cada hilo en todo punto de conexion interior (pines, extremos de otros hilos)."""
    pts = set(extra_pts)
    for a, b in wires:
        pts.add(a); pts.add(b)
    for s in symbols:
        pts.update(s["pins"].values())
    out = []
    for a, b in wires:
        if a[0] == b[0]:
            mid = sorted(p for p in pts if p[0] == a[0] and min(a[1], b[1]) < p[1] < max(a[1], b[1]))
        else:
            mid = sorted(p for p in pts if p[1] == a[1] and min(a[0], b[0]) < p[0] < max(a[0], b[0]))
        chain = sorted([a, b] + mid)
        out += list(zip(chain, chain[1:]))
    return out


JUST = {"l": "left", "r": "right", "c": None}


def field_fx(s, at, hide=False):
    """(at ...) + (effects ...) de un campo. El angulo guardado es relativo al simbolo."""
    S = Sym
    font = [S("font"), [S("size"), 1.27, 1.27]]
    if at is None or hide:
        return [S("at"), s["x"], s["y"], 0], [S("effects"), font, [S("hide"), S("yes")]]
    dx, dy, j = at
    ang = 90 if s["rot"] in (90, 270) else 0
    eff = [S("effects"), font]
    if JUST[j]:
        jj = JUST[j]
        if s["mirror"] == "y" or s["rot"] in (90, 180):
            jj = {"left": "right", "right": "left"}[jj]
        eff.append([S("justify"), S(jj)])
    return [S("at"), round(s["x"] + dx, 4), round(s["y"] + dy, 4), ang], eff


def emit():
    S = Sym
    used = []
    for s in symbols:
        if s["lib_id"] not in used:
            used.append(s["lib_id"])
    root = [S("kicad_sch"), [S("version"), 20250114], [S("generator"), "eeschema"],
            [S("generator_version"), "9.0"], [S("uuid"), ROOT_UUID], [S("paper"), "A2"],
            [S("title_block"),
             [S("title"), "MagHead AFE - front-end analogico de 2 canales"],
             [S("date"), "2026-11-15"], [S("rev"), "A"],
             [S("comment"), 1, "Prototipo de laboratorio rev A - no liberado para fabricacion"],
             [S("comment"), 2, "Generado por gen_afe_sch.py (no editar a mano sin actualizar el generador)"]],
            [S("lib_symbols")] + [LIB[i] for i in used]]
    juncs = junctions()
    segs = split_wires(juncs + [(x, y) for (_n, x, y, _a) in labels])
    for p in juncs:
        root.append([S("junction"), [S("at"), p[0], p[1]], [S("diameter"), 0], [S("color"), 0, 0, 0, 0],
                     [S("uuid"), uid("j")]])
    for a, b in segs:
        root.append([S("wire"), [S("pts"), [S("xy"), a[0], a[1]], [S("xy"), b[0], b[1]]],
                     [S("stroke"), [S("width"), 0], [S("type"), S("default")]], [S("uuid"), uid("w")]])
    for x1, y1, x2, y2 in rects:
        root.append([S("rectangle"), [S("start"), x1, y1], [S("end"), x2, y2],
                     [S("stroke"), [S("width"), 0.2], [S("type"), S("dash")]],
                     [S("fill"), [S("type"), S("none")]], [S("uuid"), uid("r")]])
    for t, x, y, size, bold, just in texts:
        font = [S("font"), [S("size"), size, size]]
        if bold:
            font.append([S("bold"), S("yes")])
        root.append([S("text"), t, [S("exclude_from_sim"), S("no")], [S("at"), x, y, 0],
                     [S("effects"), font, [S("justify")] + [S(j) for j in just.split()]],
                     [S("uuid"), uid("t")]])
    for name, x, y, ang in labels:
        just = "right bottom" if ang in (180, 270) else "left bottom"
        root.append([S("label"), name, [S("at"), x, y, ang],
                     [S("effects"), [S("font"), [S("size"), 1.27, 1.27]],
                      [S("justify")] + [S(j) for j in just.split()]],
                     [S("uuid"), uid("l")]])
    for s in symbols:
        pwr = s["ref"].startswith("#")
        node = [S("symbol"), [S("lib_id"), s["lib_id"]], [S("at"), s["x"], s["y"], s["rot"]]]
        if s["mirror"]:
            node.append([S("mirror"), S(s["mirror"])])
        node += [[S("unit"), s["unit"]], [S("exclude_from_sim"), S("no")],
                 [S("in_bom"), S("yes")], [S("on_board"), S("yes")],
                 [S("dnp"), S("yes" if s["dnp"] else "no")], [S("uuid"), uid("s")]]

        def prop(name, value, at, hide=False):
            a, e = field_fx(s, at, hide)
            node.append([S("property"), name, value, a, e])
        prop("Reference", s["ref"], s["ref_at"])
        prop("Value", s["value"], s["val_at"])
        prop("Footprint", s["fp"], None)
        prop("Datasheet", lib_prop(s["lib_id"], "Datasheet"), None)
        prop("Description", lib_prop(s["lib_id"], "Description"), None)
        if not pwr:
            prop("MPN", s["mpn"], None)
            prop("Manufacturer", s["mfr"], None)
        for num in s["allpins"]:
            node.append([S("pin"), num, [S("uuid"), uid("p")]])
        node.append([S("instances"), [S("project"), PROJECT,
                                      [S("path"), "/" + ROOT_UUID, [S("reference"), s["ref"]],
                                       [S("unit"), s["unit"]]]]])
        root.append(node)
    root.append([S("sheet_instances"), [S("path"), "/", [S("page"), "1"]]])
    root.append([S("embedded_fonts"), S("no")])
    open(os.path.join(HERE, PROJECT + ".kicad_sch"), "w").write(dump(root) + "\n")
    pro = {
        "board": {}, "libraries": {"pinned_footprint_libs": [], "pinned_symbol_libs": []},
        "meta": {"filename": PROJECT + ".kicad_pro", "version": 3},
        "net_settings": {"classes": [{"name": "Default", "clearance": 0.2, "track_width": 0.2,
                                      "via_diameter": 0.6, "via_drill": 0.3, "wire_width": 6}],
                         "meta": {"version": 4}},
        "schematic": {"legacy_lib_dir": "", "legacy_lib_list": []},
        "sheets": [[ROOT_UUID, "Root"]], "text_variables": {},
    }
    json.dump(pro, open(os.path.join(HERE, PROJECT + ".kicad_pro"), "w"), indent=2)
    n_real = len({s["ref"] for s in symbols if not s["ref"].startswith("#")})
    print("simbolos: %d instancias, %d referencias reales, %d hilos, %d etiquetas, %d uniones"
          % (len(symbols), n_real, len(wires), len(labels), len(junctions())))


if __name__ == "__main__":
    build()
    emit()
