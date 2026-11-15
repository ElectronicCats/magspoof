#!/usr/bin/env python3
"""Schematic of maghead-afe, generated from DESIGN.md (run: python3 tools/gen_sch.py; then schematic.py check).

Every pin gets a net, a power port or a no-connect: a forgotten pin stops the run.
"""
import sys
from pathlib import Path
sys.path.insert(0, "/home/user/hardware-design-skill/lib")
from hwkit.schgen import Sch

R = "Resistor_SMD:R_0603_1608Metric"
C = "Capacitor_SMD:C_0603_1608Metric"

s = Sch("maghead-afe", title="maghead-afe", rev="A")

# ---- block 1: power
s.text("POWER", 25, 25)
# s.place("Regulator_Linear", "AMS1117-3.3", "U1", "AMS1117-3.3", 60, 50, {"1": "GND", "2": "+3V3", "3": "+5V"},
#         footprint="Package_TO_SOT_SMD:SOT-223-3_TabPin2", lcsc="C6186")

# ---- rails that come from a connector need a driver for ERC
# s.flag("+5V", 40, 200); s.flag("GND", 60, 200)

bad = s.check_overlaps()
for b in bad:
    print("  OVERLAP:", b)
if bad:
    raise SystemExit("move the parts/labels above: nothing may sit on top of anything")
print(s.write(Path(__file__).resolve().parents[1]))
