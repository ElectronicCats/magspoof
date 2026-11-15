#!/usr/bin/env python3
"""Verificacion independiente de maghead_afe.kicad_pcb (sin pcbnew, solo sexpr.py).

  1. net de CADA pad de la placa == net del mismo pin en maghead_afe.net (y viceversa);
     huella (lib:nombre), valor y DNP de cada componente;
  2. longitud de pista por net, vias, tamano de placa;
  3. distancia minima entre las pistas CMP_A/CMP_B y el cobre de los nodos de la etapa 1.
Uso: check_pcb.py [placa.kicad_pcb] [netlist.net]   (codigo != 0 si falla)
"""
import math
import sys
from sexpr import parse, find, find1

SENS = ["/HEAD_A_P", "/HEAD_A_N", "/INA_P", "/FB1A", "/HEAD_B_P", "/HEAD_B_N", "/INB_P", "/FB1B"]
BOARD_ONLY = ("H1", "H2", "H3", "H4")


def main():
    pcbfn = sys.argv[1] if len(sys.argv) > 1 else "maghead_afe.kicad_pcb"
    netfn = sys.argv[2] if len(sys.argv) > 2 else "maghead_afe.net"
    nl = parse(open(netfn).read())
    want = {}
    for n in find(find1(nl, "nets"), "net"):
        for nd in find(n, "node"):
            want[(find1(nd, "ref")[1], find1(nd, "pin")[1])] = find1(n, "name")[1]
    comps = {}
    for c in find(find1(nl, "components"), "comp"):
        comps[find1(c, "ref")[1]] = (find1(c, "value")[1], find1(c, "footprint")[1],
                                    any(p[1][1] == "dnp" for p in find(c, "property")))
    pcb = parse(open(pcbfn).read())
    errs = []
    got = {}
    seen = set()
    padpos = {}
    for fp in find(pcb, "footprint"):
        props = {p[1]: p[2] for p in find(fp, "property")}
        ref = props["Reference"]
        at = find1(fp, "at")
        fx, fy, frot = float(at[1]), float(at[2]), (float(at[3]) if len(at) > 3 else 0.0)
        if ref in BOARD_ONLY:
            continue
        if ref in seen:
            errs.append("referencia duplicada " + ref)
        seen.add(ref)
        if ref not in comps:
            errs.append("huella %s no esta en el netlist" % ref)
            continue
        val, fpn, dnp = comps[ref]
        if fp[1] != fpn:
            errs.append("%s huella %s, netlist %s" % (ref, fp[1], fpn))
        if props["Value"] != val:
            errs.append("%s valor %s, netlist %s" % (ref, props["Value"], val))
        attr = find1(fp, "attr") or []
        if ("dnp" in attr) != dnp:
            errs.append("%s DNP difiere" % ref)
        for pad in find(fp, "pad"):
            num = pad[1]
            net = find1(pad, "net")
            if pad[2] == "np_thru_hole":
                continue
            name = net[2] if net else None
            if (ref, num) in got and got[(ref, num)] != name:
                errs.append("%s.%s con dos nets" % (ref, num))
            got[(ref, num)] = name
            pa = find1(pad, "at")
            a = math.radians(frot)
            px, py = float(pa[1]), float(pa[2])
            padpos[(ref, num)] = (fx + px * math.cos(a) + py * math.sin(a), fy - px * math.sin(a) + py * math.cos(a))
    for k in sorted(set(want) | set(got)):
        if want.get(k) != got.get(k):
            errs.append("pad %s.%s: placa=%r netlist=%r" % (k[0], k[1], got.get(k), want.get(k)))
    for ref in comps:
        if ref not in seen:
            errs.append("falta la huella de " + ref)
    print("pads comparados: %d (netlist %d)  componentes: %d" % (len(got), len(want), len(seen)))

    # --- geometria
    netname = {n[1]: n[2] for n in find(pcb, "net")}
    segs = {}
    for s in find(pcb, "segment"):
        a, b = find1(s, "start"), find1(s, "end")
        name = netname[find1(s, "net")[1]]
        segs.setdefault(name, []).append((float(a[1]), float(a[2]), float(b[1]), float(b[2]),
                                          float(find1(s, "width")[1]), find1(s, "layer")[1]))
    vias = {}
    for v in find(pcb, "via"):
        vias.setdefault(netname[find1(v, "net")[1]], []).append((float(find1(v, "at")[1]), float(find1(v, "at")[2])))
    xs, ys = [], []
    for kind in ("gr_line", "gr_arc"):
        for g in find(pcb, kind):
            if find1(g, "layer")[1] == "Edge.Cuts":
                for key in ("start", "mid", "end"):
                    p = find1(g, key)
                    if p:
                        xs.append(float(p[1]))
                        ys.append(float(p[2]))
    print("placa: %.2f x %.2f mm   pistas: %d   vias: %d (senal %d)" % (
        max(xs) - min(xs), max(ys) - min(ys), sum(len(v) for v in segs.values()),
        sum(len(v) for v in vias.values()),
        sum(len(v) for k, v in vias.items() if k not in ("GND", "+3V3A"))))
    wmin = min(s[4] for v in segs.values() for s in v)
    print("ancho minimo de pista: %.2f mm" % wmin)
    print("longitud de pista por net (mm) [vias]:")
    for name in SENS + sorted(set(segs) - set(SENS)):
        L = sum(math.hypot(s[2] - s[0], s[3] - s[1]) for s in segs.get(name, []))
        lay = sorted(set(s[5] for s in segs.get(name, [])))
        print("  %-12s %6.1f  [%d] %s%s" % (name, L, len(vias.get(name, [])), ",".join(lay),
                                             "   <- sensible" if name in SENS else ""))
    for name in SENS:
        if vias.get(name) or any(s[5] != "F.Cu" for s in segs.get(name, [])):
            errs.append("net sensible %s usa vias o B.Cu" % name)

    def d_seg_seg(p, q):
        def d_pt(px, py, s):
            vx, vy = s[2] - s[0], s[3] - s[1]
            L2 = vx * vx + vy * vy
            t = 0 if L2 == 0 else max(0, min(1, ((px - s[0]) * vx + (py - s[1]) * vy) / L2))
            return math.hypot(px - s[0] - t * vx, py - s[1] - t * vy)
        return min(d_pt(p[0], p[1], q), d_pt(p[2], p[3], q), d_pt(q[0], q[1], p), d_pt(q[2], q[3], p))

    sens_geo = [s for n in SENS for s in segs.get(n, [])]
    sens_geo += [(x, y, x, y, 0, "") for (k, n) in got.items() if n in SENS for (x, y) in [padpos[k]]]
    for agg in ("/CMP_A", "/CMP_B", "/ADC_A", "/ADC_B", "/MON_A", "/MON_B", "VBUS"):
        geo = segs.get(agg, []) + [(x, y, x, y, 0, "") for (x, y) in vias.get(agg, [])]
        d = min(d_seg_seg(a, b) for a in geo for b in sens_geo)
        print("  distancia minima %-7s -> nodos etapa 1: %.1f mm" % (agg, d))
        if agg.startswith("/CMP") and d < 25:
            errs.append("%s a %.1f mm de la etapa 1" % (agg, d))
    if errs:
        print("ERRORES:")
        for e in errs:
            print("  " + e)
        sys.exit(1)
    print("OK: los pads de la placa coinciden con el netlist")


if __name__ == "__main__":
    main()
