#!/usr/bin/env python3
"""Extrae (y aplana 'extends') los simbolos de stock de KiCad 9 usados por el AFE.
Uso: extract_syms.py <dir con *.kicad_sym de KiCad> -> afe_symbols.kicad_sym
(Los .kicad_sym de stock estan en la imagen docker kicad/kicad:9.0 en /usr/share/kicad/symbols)"""
import sys, os, copy, re
from sexpr import parse, dump, find, find1, Sym

NEEDED = [
    "Device:R", "Device:C", "Device:R_Potentiometer_Trim",
    "power:GND", "power:+3.3VA", "power:VBUS", "power:PWR_FLAG",
    "Regulator_Linear:AP2112K-3.3", "Reference_Voltage:LM4040DBZ-3",
    "Amplifier_Operational:MCP6002-xSN", "Amplifier_Operational:AD8656",
    "Comparator:MCP6562", "Diode:BAV99",
    "Connector_Generic:Conn_01x08", "Connector_Generic:Conn_01x03",
    "Jumper:Jumper_2_Open", "Connector_Audio:AudioJack3", "Connector:TestPoint",
]

def raw_symbol(text, name):
    """Recorta el bloque (symbol "name" ...) del texto sin parsear toda la libreria."""
    m = re.search(r'\n\t\(symbol "%s"\s' % re.escape(name), text)
    if not m:
        raise KeyError(name)
    i = m.start() + 2
    depth = 0; j = i; instr = False
    while True:
        ch = text[j]
        if instr:
            if ch == '\\': j += 1
            elif ch == '"': instr = False
        elif ch == '"': instr = True
        elif ch == '(': depth += 1
        elif ch == ')':
            depth -= 1
            if depth == 0: break
        j += 1
    return parse(text[i:j + 1])

def load(libdir, lib, name, cache):
    if lib not in cache:
        cache[lib] = open(os.path.join(libdir, lib + ".kicad_sym")).read()
    s = raw_symbol(cache[lib], name)
    ext = find1(s, "extends")
    if ext:
        parent = load(libdir, lib, ext[1], cache)
        pname = parent[1]
        out = copy.deepcopy(parent)
        out[1] = name
        # propiedades del hijo sustituyen a las del padre
        for p in find(s, "property"):
            for k, c in enumerate(out):
                if isinstance(c, list) and c[0] == "property" and c[1] == p[1]:
                    out[k] = p; break
            else:
                idx = max(k for k, c in enumerate(out) if isinstance(c, list) and c[0] == "property")
                out.insert(idx + 1, p)
        for c in out:
            if isinstance(c, list) and c[0] == "symbol":
                c[1] = name + c[1][len(pname):]
        s = out
    return s

def main():
    libdir = sys.argv[1]
    cache = {}
    out = [Sym("kicad_symbol_lib"), [Sym("version"), 20241209], [Sym("generator"), "extract_syms"],
           [Sym("generator_version"), "9.0"]]
    for full in NEEDED:
        lib, name = full.split(":")
        s = load(libdir, lib, name, cache)
        s[1] = full          # nombre con prefijo de libreria (como en lib_symbols)
        out.append(s)
    open("afe_symbols.kicad_sym", "w").write(dump(out) + "\n")
    print("ok", len(NEEDED))

if __name__ == "__main__":
    main()
