#!/usr/bin/env python3
"""Resume drc.json (kicad-cli pcb drc --schematic-parity --format json).
Sale con 1 si hay errores, items sin conectar o diferencias con el esquematico. -v lista todo."""
import collections
import json
import sys

args = [a for a in sys.argv[1:] if not a.startswith("-")]
d = json.load(open(args[0] if args else "drc.json"))
c = collections.Counter()
for sec in ("violations", "unconnected_items", "schematic_parity"):
    for v in d.get(sec, []):
        c[(sec, v["severity"], v["type"])] += 1
        if "-v" in sys.argv or v["severity"] == "error" or sec != "violations":
            print(v["severity"], v["type"], "|", v["description"], "|",
                  "; ".join("%s @(%.2f,%.2f)" % (i["description"], i["pos"]["x"], i["pos"]["y"]) for i in v["items"]))
for k, n in sorted(c.items()):
    print("%-18s %-8s %-28s %d" % (k[0], k[1], k[2], n))
ne = sum(n for k, n in c.items() if k[0] == "violations" and k[1] == "error")
nw = sum(n for k, n in c.items() if k[0] == "violations" and k[1] != "error")
nu = len(d.get("unconnected_items", []))
npar = len(d.get("schematic_parity", []))
print("TOTAL DRC errores=%d advertencias=%d sin_conectar=%d paridad_esquematico=%d" % (ne, nw, nu, npar))
sys.exit(1 if (ne or nu or npar) else 0)
