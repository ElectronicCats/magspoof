"""Formato de archivo de una pasada: <base>.npz (datos) + <base>.json (metadatos).

.npz (numpy, comprimido):
  chA         int16[N]   codigos ADC del canal A (0..4095, centro 2048)
  chB         int16[N]   canal B, o vacio si no se capturo
  dig         uint8[N]   bits digitales por muestra: b0 barrera 1, b1 barrera 2
                         (1 = tarjeta presente), b2 comparador A, b3 comparador B; o vacio
  fs          float      frecuencia de muestreo POR CANAL (Hz)
  gate_edges  float[K,3] flancos de barrera: [t (s desde la primera muestra), barrera (1|2),
                         nivel (1 = tarjeta presente)]

.json: metadatos segun SCHEMA (ver tools/README.md).
"""
from __future__ import annotations

from dataclasses import dataclass, field
import datetime as _dt
import json
import os
import numpy as np

SCHEMA_VERSION = 1
VOLTS_PER_COUNT = 3.3 / 4096

# clave: (tipo, obligatorio para el analisis, descripcion)
SCHEMA = {
    "schema_version": ("int", True, "Version del esquema (1)."),
    "swipe_id": ("str", False, "Identificador de la pasada (por defecto, el nombre del archivo)."),
    "card_id": ("str", True, "Identificador de la tarjeta de laboratorio."),
    "expected_tracks": ("dict", True, "Cadenas esperadas por pista, con centinelas: {\"1\": \"%...?\", \"2\": \";...?\"}."),
    "track_under_test": ("int", True, "Pista bajo el cabezal del canal analizado: 1, 2 o 3."),
    "channel_under_test": ("str", False, "Canal del cabezal bajo prueba: \"A\" (defecto) o \"B\"."),
    "head_variant": ("str", True, "Identificador de la variante de cabezal."),
    "head_gap_um": ("float|null", False, "Entrehierro nominal (um)."),
    "head_spacer": ("str|null", False, "Material/espesor del separador del entrehierro."),
    "assembly_serial": ("str|null", False, "Numero de serie del montaje."),
    "spacing_shim_um": ("float|null", True, "Calza de separacion cabezal-tarjeta (um); 0 = contacto."),
    "pad_force_N": ("float|null", False, "Fuerza de la almohadilla de presion (N)."),
    "lateral_offset_mm": ("float|null", False, "Desplazamiento lateral respecto al centro de pista (mm)."),
    "azimuth_deg": ("float|null", False, "Angulo de azimut del entrehierro (grados)."),
    "afe_gain_a": ("float|null", True, "Ganancia total del AFE del canal A (V/V); necesaria para uV*s/m."),
    "afe_gain_b": ("float|null", False, "Ganancia total del AFE del canal B (V/V)."),
    "bpi": ("float", False, "Densidad si no es la de la pista (210 / 75 / 210 bpi)."),
    "volts_per_count": ("float", False, "Voltios por cuenta de chA/chB (defecto 3.3/4096)."),
    "nominal_speed_m_s": ("float|null", True, "Velocidad nominal de la pasada (m/s)."),
    "speed_source": ("str", True, "Como se produjo la velocidad: \"hand\", \"motor\" o \"synthetic\"."),
    "operator": ("str|null", False, "Persona que hizo la pasada."),
    "date": ("str", True, "Fecha y hora ISO 8601."),
    "firmware_version": ("str|null", False, "Version del firmware (respuesta a VER)."),
    "capture_source": ("str", False, "\"serial\", \"wav\", \"csv\" o \"synth\"."),
    "dropped_blocks": ("int", False, "Bloques perdidos por el firmware dentro de la pasada."),
    "gaps": ("list", False, "Huecos rellenados con el valor medio: [[muestra_inicial, n_muestras], ...]."),
    "notes": ("str", False, "Texto libre."),
    "synthetic": ("dict", False, "Solo datos sinteticos: verdad-terreno (t_trans, pw50_um, snr_db...)."),
}


def new_meta() -> dict:
    """Plantilla de metadatos con todas las claves del esquema."""
    return {
        "schema_version": SCHEMA_VERSION, "swipe_id": "", "card_id": "", "expected_tracks": {},
        "track_under_test": 2, "channel_under_test": "A", "head_variant": "", "head_gap_um": None,
        "head_spacer": None, "assembly_serial": None, "spacing_shim_um": 0.0, "pad_force_N": None,
        "lateral_offset_mm": None, "azimuth_deg": None, "afe_gain_a": None, "afe_gain_b": None,
        "volts_per_count": VOLTS_PER_COUNT, "nominal_speed_m_s": None, "speed_source": "hand",
        "operator": None, "date": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "firmware_version": None, "capture_source": "", "dropped_blocks": 0, "gaps": [], "notes": "",
    }


def validate_meta(meta: dict) -> list[str]:
    """Devuelve la lista de problemas (vacia si todo bien)."""
    probs = []
    for k, (_, req, _) in SCHEMA.items():
        if req and k not in meta:
            probs.append(f"falta la clave obligatoria '{k}'")
    for k in meta:
        if k not in SCHEMA:
            probs.append(f"clave desconocida '{k}'")
    t = meta.get("track_under_test")
    if t not in (1, 2, 3):
        probs.append("track_under_test debe ser 1, 2 o 3")
    elif str(t) not in (meta.get("expected_tracks") or {}):
        probs.append(f"expected_tracks no contiene la pista {t}")
    if meta.get("speed_source") not in ("hand", "motor", "synthetic"):
        probs.append("speed_source debe ser hand, motor o synthetic")
    return probs


@dataclass
class Swipe:
    chA: np.ndarray
    chB: np.ndarray
    dig: np.ndarray
    fs: float
    gate_edges: np.ndarray
    meta: dict = field(default_factory=new_meta)
    path: str = ""

    def channel(self, name: str = "A") -> np.ndarray:
        return self.chB if name.upper() == "B" else self.chA


def save(swipe: Swipe, base: str) -> str:
    """Escribe <base>.npz y <base>.json. Devuelve la ruta base."""
    for ext in (".npz", ".json"):
        if base.endswith(ext):
            base = base[: -len(ext)]
    os.makedirs(os.path.dirname(os.path.abspath(base)), exist_ok=True)
    np.savez_compressed(
        base + ".npz", chA=np.asarray(swipe.chA, np.int16), chB=np.asarray(swipe.chB, np.int16),
        dig=np.asarray(swipe.dig, np.uint8), fs=np.float64(swipe.fs),
        gate_edges=np.asarray(swipe.gate_edges, float).reshape(-1, 3))
    meta = dict(swipe.meta)
    if not meta.get("swipe_id"):
        meta["swipe_id"] = os.path.basename(base)
    with open(base + ".json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    return base


def load(base: str) -> Swipe:
    for ext in (".npz", ".json"):
        if base.endswith(ext):
            base = base[: -len(ext)]
    with np.load(base + ".npz") as z:
        sw = Swipe(chA=z["chA"], chB=z["chB"], dig=z["dig"], fs=float(z["fs"]),
                   gate_edges=z["gate_edges"].reshape(-1, 3), path=base)
    with open(base + ".json", encoding="utf-8") as f:
        sw.meta = json.load(f)
    return sw


def list_swipes(folder: str) -> list[str]:
    """Rutas base de todas las pasadas (pares .npz + .json) de una carpeta, recursivo."""
    out = []
    for root, _, files in os.walk(folder):
        for fn in sorted(files):
            if fn.endswith(".npz") and os.path.exists(os.path.join(root, fn[:-4] + ".json")):
                out.append(os.path.join(root, fn[:-4]))
    return sorted(out)
