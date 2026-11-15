#!/usr/bin/env python3
"""Verifica el netlist exportado por KiCad (formato kicadsexpr) contra la tabla de
nets PREVISTA, escrita a mano desde la especificacion (independiente del generador).

Comprueba:
  1. cada net prevista existe y contiene EXACTAMENTE los pines previstos;
  2. no hay nets extra (salvo pines no_connect declarados);
  3. todo pin de todo componente aparece en alguna net prevista;
  4. cada componente tiene Footprint, MPN y Manufacturer; valores y DNP previstos.
Uso: check_netlist.py [maghead_afe.net]   (sale con codigo != 0 si falla)
"""
import sys
from sexpr import parse, find, find1


def chan(ch, n, ua, ub):
    """Nets de un canal. n = 100/200. ua = pines (+,-,out) de la unidad usada."""
    plus, minus, out = ua
    R = lambda k: "R%d" % (n + k)
    C = lambda k: "C%d" % (n + k)
    JP = lambda k: "JP%d" % (n + k)
    D = "D%d" % (n + 1)
    J = {"A": "J1", "B": "J2"}[ch]
    TPa, TPb = "TP%d" % (n + 1), "TP%d" % (n + 2)
    RV = "RV%d" % (n + 1)
    adc_pin, cmp_pin, mon_pin = {"A": ("3", "6", "T"), "B": ("5", "7", "R")}[ch]
    nets = {
        "HEAD_%s_P" % ch: [J + ".1", R(1) + ".1", C(1) + ".1", D + ".3", R(2) + ".1"],
        "HEAD_%s_N" % ch: [J + ".2", R(1) + ".2", C(1) + ".2", R(0) + ".1"],
        "IN%s_P" % ch: [R(2) + ".2", C(2) + ".1", "U1." + plus],
        "FB1%s" % ch: ["U1." + minus, R(3) + ".1", C(3) + ".1", R(4) + ".1", R(5) + ".1"],
        "G1%s_J" % ch: [R(5) + ".2", JP(1) + ".1"],
        "S1%s" % ch: ["U1." + out, R(3) + ".2", C(3) + ".2", C(4) + ".1", TPa + ".1"],
        "AC_%s" % ch: [C(4) + ".2", R(6) + ".1"],
        "FB2%s" % ch: [R(6) + ".2", "U2." + minus] + [x + ".1" for k in (7, 8, 9, 10) for x in (R(k), C(k))],
        "FB2%s_J1" % ch: [R(8) + ".2", C(8) + ".2", JP(2) + ".1"],
        "FB2%s_J2" % ch: [R(9) + ".2", C(9) + ".2", JP(3) + ".1"],
        "FB2%s_J3" % ch: [R(10) + ".2", C(10) + ".2", JP(4) + ".1"],
        "S2%s" % ch: ["U2." + out, R(7) + ".2", C(7) + ".2", JP(2) + ".2", JP(3) + ".2", JP(4) + ".2",
                      TPb + ".1", R(11) + ".1", C(12) + ".1", R(14) + ".1"],
        "ADC_%s" % ch: [R(11) + ".2", C(11) + ".1", "J4." + adc_pin],
        "MON_%s_C" % ch: [C(12) + ".2", R(12) + ".1"],
        "MON_%s" % ch: [R(12) + ".2", R(13) + ".1", "J3." + mon_pin],
        "CMP%s_P" % ch: [R(14) + ".2", "U4." + plus, R(15) + ".1"],
        "CMP%s_H" % ch: [R(15) + ".2", RV + ".1"],          # nodo interno R115-RV101 (nombre anadido)
        "CMP_%s" % ch: ["U4." + out, RV + ".2", RV + ".3", "J4." + cmp_pin],
    }
    vref = [R(0) + ".2", D + ".1", D + ".2", C(2) + ".2", R(4) + ".2", JP(1) + ".2",
            "U2." + plus, "U4." + minus]
    gnd = [J + ".3", C(11) + ".2", R(13) + ".2"]
    return nets, vref, gnd


EXPECT = {
    "VBUS": ["J4.1", "U5.1", "U5.3", "C20.1"],
    "+3V3A": ["U5.5", "C21.1", "C22.1", "R30.1", "U3.8", "C32.1", "U1.8", "C10.1", "C11.1",
              "U2.8", "C12.1", "C13.1", "R40.1", "TP3.1"],
    "+3V3C": ["R40.2", "C40.1", "C41.1", "U4.8"],
    "ADC_VREF": ["J4.8", "D3.1", "C23.1"],
    "VREF_DIV": ["R30.2", "R31.1", "C30.1", "U3.3"],
    "VREF": ["U3.1", "U3.2", "U3.5", "TP2.1"],
    "U3B_NC": ["U3.6", "U3.7"],
    "GND": ["J4.2", "J4.4", "U5.2", "C20.2", "C21.2", "C22.2", "D3.2", "C23.2", "R31.2", "C30.2",
            "U3.4", "C32.2", "U1.4", "C10.2", "C11.2", "U2.4", "C12.2", "C13.2", "U4.4", "C40.2",
            "C41.2", "J3.S", "TP1.1"],
}
for ch, n, ua in (("A", 100, ("3", "2", "1")), ("B", 200, ("5", "6", "7"))):
    nets, vref, gnd = chan(ch, n, ua, None)
    EXPECT.update(nets)
    EXPECT["VREF"] += vref
    EXPECT["GND"] += gnd

NO_CONNECT = {"U5.4", "D3.3"}          # pines NC del propio encapsulado

DNP = {"R101", "C101", "C102", "R201", "C201", "C202", "D3", "C23"}

VALUES = {  # valores previstos (canal A; el B se deriva sumando 100)
    "R100": "0R", "R101": "10k", "R102": "47R", "R103": "1k", "R104": "100R", "R105": "11R",
    "R106": "1k", "R107": "200k", "R108": "49.9k", "R109": "10k", "R110": "2k", "R111": "1k",
    "R112": "100R", "R113": "100k", "R114": "10k", "R115": "47k", "RV101": "500k",
    "C101": "470pF", "C102": "1nF", "C103": "1nF", "C104": "10uF", "C107": "18pF", "C108": "82pF",
    "C109": "390pF", "C110": "2.2nF", "C111": "2.2nF", "C112": "10uF", "D101": "BAV99",
}
for k, v in list(VALUES.items()):
    pre = k.rstrip("0123456789")
    VALUES[pre + str(int(k[len(pre):]) + 100)] = v
VALUES.update({
    "R30": "10k", "R31": "10k", "R40": "10R", "C10": "100nF", "C11": "1uF", "C12": "100nF",
    "C13": "1uF", "C20": "1uF", "C21": "1uF", "C22": "10uF", "C23": "100nF", "C30": "10uF",
    "C32": "100nF", "C40": "1uF", "C41": "100nF", "U1": "AD8656ARZ", "U2": "AD8656ARZ",
    "U3": "MCP6002-I/SN", "U4": "MCP6562-E/SN", "U5": "AP2112K-3.3", "D3": "LM4040DBZ-3.0",
})
FOOTPRINT_RULES = [
    ("R", lambda r, v: "Resistor_SMD:R_0603_1608Metric"),
    ("C", lambda r, v: "Capacitor_SMD:C_0805_2012Metric" if v == "10uF" else "Capacitor_SMD:C_0603_1608Metric"),
]


def main():
    fn = sys.argv[1] if len(sys.argv) > 1 else "maghead_afe.net"
    t = parse(open(fn).read())
    errs = []
    # ---- componentes
    comps = {}
    for c in find(find1(t, "components"), "comp"):
        ref = find1(c, "ref")[1]
        props = {p[1][1]: (p[2][1] if len(p) > 2 and len(p[2]) > 1 else "") for p in find(c, "property")}
        fields = {f[1][1]: (f[2] if len(f) > 2 else "") for f in find(find1(c, "fields") or ["fields"], "field")}
        fp = find1(c, "footprint")
        comps[ref] = dict(value=find1(c, "value")[1], fp=fp[1] if fp else "", props=props, fields=fields)
    for ref, c in sorted(comps.items()):
        if not c["fp"]:
            errs.append("%s sin Footprint" % ref)
        for f in ("MPN", "Manufacturer"):
            v = c["fields"].get(f) or c["props"].get(f)
            if not v:
                errs.append("%s sin campo %s" % (ref, f))
        isdnp = "dnp" in c["props"]
        if isdnp != (ref in DNP):
            errs.append("%s DNP=%s, previsto %s" % (ref, isdnp, ref in DNP))
        if ref in VALUES and c["value"] != VALUES[ref]:
            errs.append("%s valor %r, previsto %r" % (ref, c["value"], VALUES[ref]))
        if ref[0] in "RC" and ref[1].isdigit():
            want = dict(FOOTPRINT_RULES)[ref[0]](ref, c["value"])
            if c["fp"] != want:
                errs.append("%s huella %s, prevista %s" % (ref, c["fp"], want))
    for ref in VALUES:
        if ref not in comps:
            errs.append("falta el componente %s" % ref)
    # ---- nets
    got = {}
    for n in find(find1(t, "nets"), "net"):
        name = find1(n, "name")[1].lstrip("/")
        got[name] = sorted("%s.%s" % (find1(nd, "ref")[1], find1(nd, "pin")[1]) for nd in find(n, "node"))
    for name, pins in EXPECT.items():
        if len(set(pins)) != len(pins):
            errs.append("tabla prevista: pin duplicado en %s" % name)
        if name not in got:
            errs.append("falta la net %s" % name)
            continue
        miss = sorted(set(pins) - set(got[name]))
        extra = sorted(set(got[name]) - set(pins))
        if miss or extra:
            errs.append("net %s: faltan %s, sobran %s" % (name, miss, extra))
    for name, pins in got.items():
        if name in EXPECT:
            continue
        if len(pins) == 1 and pins[0] in NO_CONNECT and name.startswith("unconnected-"):
            continue
        errs.append("net no prevista %s: %s" % (name, pins))
    # ---- todo pin de la tabla prevista pertenece a un componente existente y viceversa
    exp_pins = [p for pins in EXPECT.values() for p in pins]
    if len(set(exp_pins)) != len(exp_pins):
        errs.append("tabla prevista: un pin aparece en dos nets")
    got_pins = {p for pins in got.values() for p in pins}
    stray = sorted(got_pins - set(exp_pins) - NO_CONNECT)
    if stray:
        errs.append("pines fuera de la tabla prevista: %s" % stray)
    print("componentes: %d   nets en netlist: %d   nets previstas: %d   pines previstos: %d"
          % (len(comps), len(got), len(EXPECT), len(exp_pins)))
    if errs:
        print("FALLO (%d):" % len(errs))
        for e in errs:
            print("  -", e)
        sys.exit(1)
    print("OK: todas las nets previstas tienen exactamente los pines previstos; "
          "campos Footprint/MPN/Manufacturer presentes; DNP y valores correctos.")


if __name__ == "__main__":
    main()
