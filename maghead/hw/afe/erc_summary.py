#!/usr/bin/env python3
"""Resume erc.json (kicad-cli sch erc --format json). Sale con 1 si hay errores."""
import json, sys, collections
args = [a for a in sys.argv[1:] if not a.startswith("-")]
d = json.load(open(args[0] if args else "erc.json"))
c = collections.Counter()
for sh in d["sheets"]:
    for v in sh["violations"]:
        c[(v["severity"], v["type"])] += 1
        if "-v" in sys.argv or v["severity"] == "error":
            print(v["severity"], v["type"], "|", v["description"], "|",
                  "; ".join("%s @(%.2f,%.2f)" % (i["description"], i["pos"]["x"] * 100, i["pos"]["y"] * 100)
                            for i in v["items"]))
for k, n in sorted(c.items()):
    print("%-8s %-28s %d" % (k[0], k[1], n))
ne = sum(n for k, n in c.items() if k[0] == "error")
nw = sum(n for k, n in c.items() if k[0] == "warning")
print("TOTAL errores=%d advertencias=%d" % (ne, nw))
sys.exit(1 if ne else 0)
