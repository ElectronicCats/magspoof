"""Configuracion comun de pytest: ruta del paquete y cadenas de prueba."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Cadenas sinteticas de laboratorio (no corresponden a ninguna tarjeta real).
T1 = "%B1234567890123445^MAGHEAD/TEST^99011200000000000000**XXX******?"
# La pista 2 solo admite 0-9 : ; < = > ? (4 bits de datos): el ejemplo original con 'X'
# no es codificable, se usan digitos en su lugar.
T2 = ";1234567890123445=99011200123400000000?"
