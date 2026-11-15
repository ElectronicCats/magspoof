"""Captura: flujo del firmware por puerto serie (USB CDC), WAV de tarjeta de sonido y
CSV de osciloscopio. Todo acaba en el formato de swipefile (.npz + .json).

Uso:
  python -m maghead.capture serial --port /dev/ttyACM0 --out datos/ --meta plantilla.json
  python -m maghead.capture bin flujo.bin --out datos/ --meta plantilla.json   (flujo ya guardado)
  python -m maghead.capture wav pasada.wav --out datos/p1 --meta plantilla.json
  python -m maghead.capture csv scope.csv --out datos/p2 --meta plantilla.json

Formato de trama: ver fw/common/mh_proto.h (cabecera de 32 bytes, palabras de 16 bits, CRC16).
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
import time
import numpy as np

from . import swipefile

MAGIC = b"MHB1"
HDR_LEN = 32
TYPE_SAMPLES, TYPE_EVENTS = 1, 2
FLAG_OVERFLOW, FLAG_TRIGGERED, FLAG_SEG_FIRST, FLAG_SEG_LAST, FLAG_DIG_BLOCK = 1, 2, 4, 8, 16
CHAN_AB, CHAN_A, CHAN_B = 0, 1, 2
MAX_PAYLOAD = 8192


def _crc_table():
    tab = []
    for i in range(256):
        c = i << 8
        for _ in range(8):
            c = ((c << 1) ^ 0x1021) if c & 0x8000 else (c << 1)
        tab.append(c & 0xFFFF)
    return tab


_TAB = _crc_table()


def crc16(data: bytes, crc: int = 0xFFFF) -> int:
    """CRC-16/CCITT-FALSE (poli 0x1021, init 0xFFFF), igual que mh_crc16."""
    for b in data:
        crc = ((crc << 8) & 0xFFFF) ^ _TAB[(crc >> 8) ^ b]
    return crc


def build_frame(ftype, flags, chan_mode, seq, count, fs_total, t0_us, drop_count, payload: bytes) -> bytes:
    """Construye una trama (para pruebas y simulacion)."""
    hdr = MAGIC + struct.pack("<BBBBIHHIQI", ftype, flags, chan_mode, 1, seq, count, len(payload),
                              fs_total, t0_us, drop_count)
    body = hdr + payload
    return body + struct.pack("<H", crc16(body))


class StreamParser:
    """Analizador incremental del flujo CDC: tramas binarias + lineas ASCII '#...'."""

    def __init__(self):
        self.buf = bytearray()
        self.frames: list[dict] = []
        self.lines: list[str] = []
        self.crc_errors = 0
        self.junk_bytes = 0

    def feed(self, data: bytes) -> list[dict]:
        """Anade bytes; devuelve las tramas nuevas completas (tambien quedan en self.frames)."""
        self.buf += data
        new = []
        while True:
            i = self.buf.find(MAGIC)
            if i < 0:
                keep = len(MAGIC) - 1
                self._text(bytes(self.buf), final=False)   # solo lineas completas
                if len(self.buf) > (1 << 20):         # basura sin fin de linea: descartar
                    self.junk_bytes += len(self.buf) - keep
                    del self.buf[:-keep]
                break
            if i > 0:
                self._text(self.buf[:i], final=True)
                del self.buf[:i]
            if len(self.buf) < HDR_LEN:
                break
            ftype, flags, cm, ver, seq, count, plen, fs_total, t0, drops = struct.unpack_from(
                "<BBBBIHHIQI", self.buf, 4)
            if plen > MAX_PAYLOAD or ftype not in (TYPE_SAMPLES, TYPE_EVENTS):
                self.junk_bytes += 1
                del self.buf[:1]                      # magic falso: resincronizar
                continue
            total = HDR_LEN + plen + 2
            if len(self.buf) < total:
                break
            body = bytes(self.buf[:total - 2])
            (crc,) = struct.unpack_from("<H", self.buf, total - 2)
            if crc != crc16(body):
                self.crc_errors += 1
                del self.buf[:1]
                continue
            fr = dict(type=ftype, flags=flags, chan_mode=cm, version=ver, seq=seq, count=count,
                      fs_total=fs_total, t0_us=t0, drop_count=drops, payload=body[HDR_LEN:])
            self.frames.append(fr)
            new.append(fr)
            del self.buf[:total]
        return new

    def _text(self, chunk, final):
        if not chunk:
            return
        if not final:
            # solo consumir lineas completas; el resto se queda en el buffer
            j = chunk.rfind(b"\n")
            if j < 0:
                return
            chunk = chunk[:j + 1]
            del self.buf[:j + 1]
        for ln in bytes(chunk).split(b"\n"):
            ln = ln.strip()
            if ln.startswith(b"#"):
                self.lines.append(ln.decode("ascii", "replace"))
            elif ln:
                self.junk_bytes += len(ln)


def frames_to_swipes(frames: list[dict], meta: dict | None = None) -> list[swipefile.Swipe]:
    """Agrupa tramas en pasadas. En modo disparado cada segmento (SEG_FIRST..SEG_LAST) es una
    pasada; en modo continuo todo el flujo es una sola. Los bloques perdidos (saltos de seq)
    se rellenan con el valor medio y se anotan en meta['gaps'] / meta['dropped_blocks']."""
    segs, cur = [], []
    events = [f for f in frames if f["type"] == TYPE_EVENTS]
    for f in frames:
        if f["type"] != TYPE_SAMPLES:
            continue
        if (f["flags"] & FLAG_SEG_FIRST) and cur:
            segs.append(cur)
            cur = []
        cur.append(f)
        if f["flags"] & FLAG_SEG_LAST:
            segs.append(cur)
            cur = []
    if cur:
        segs.append(cur)
    out = []
    for seg in segs:
        f0 = seg[0]
        cm, fs_total, nw = f0["chan_mode"], f0["fs_total"], f0["count"]
        nch = 2 if cm == CHAN_AB else 1
        fs = fs_total / nch
        nblk = seg[-1]["seq"] - f0["seq"] + 1
        words = np.full(nblk * nw, 2048, dtype=np.uint16)
        have = np.zeros(nblk, bool)
        for f in seg:
            k = f["seq"] - f0["seq"]
            w = np.frombuffer(f["payload"], dtype="<u2")
            if 0 <= k < nblk and len(w) == nw:
                words[k * nw:(k + 1) * nw] = w
                have[k] = True
        gaps = []
        k = 0
        while k < nblk:
            if not have[k]:
                j = k
                while j < nblk and not have[j]:
                    j += 1
                gaps.append([int(k * nw // nch), int((j - k) * nw // nch)])
                k = j
            else:
                k += 1
        if cm == CHAN_AB:
            wa, wb = words[0::2], words[1::2]
        elif cm == CHAN_A:
            wa, wb = words, np.zeros(0, np.uint16)
        else:
            wa, wb = np.zeros(0, np.uint16), words
        ref = wa if len(wa) else wb
        dig = ((ref >> 12) & 0x3).astype(np.uint8)
        if len(wa):
            dig |= (((wa >> 14) & 1) << 2).astype(np.uint8)
        if len(wb):
            dig |= (((wb >> 14) & 1) << 3).astype(np.uint8)
        t0 = f0["t0_us"]
        t1 = t0 + nblk * nw * 1e6 / fs_total
        ge = [[(struct.unpack_from("<Q", e["payload"], i * 12)[0] - t0) * 1e-6,
               e["payload"][i * 12 + 8], e["payload"][i * 12 + 9]]
              for e in events for i in range(e["count"])
              if t0 - 1e6 <= struct.unpack_from("<Q", e["payload"], i * 12)[0] <= t1]
        if not ge:                                   # sin eventos: flancos a partir de los bits
            for g in (1, 2):
                b = (dig >> (g - 1)) & 1
                idx = np.flatnonzero(np.diff(b.astype(np.int8)) != 0) + 1
                ge += [[i / fs, g, int(b[i])] for i in idx]
            ge.sort()
        m = swipefile.new_meta()
        if meta:
            m.update(meta)
        m["capture_source"] = m.get("capture_source") or "serial"
        m["dropped_blocks"] = int((~have).sum())
        m["gaps"] = gaps
        if any(f["flags"] & FLAG_OVERFLOW for f in seg) and not gaps:
            m["notes"] = (m.get("notes", "") + " [firmware: OVERFLOW antes del segmento]").strip()
        out.append(swipefile.Swipe(chA=(wa & 0x0FFF).astype(np.int16), chB=(wb & 0x0FFF).astype(np.int16),
                                   dig=dig, fs=float(fs), gate_edges=np.array(ge, float).reshape(-1, 3),
                                   meta=m))
    return out


def read_serial(port: str, seconds: float, commands=(), max_swipes: int = 0, quiet: bool = False):
    """Lee del puerto serie durante `seconds` (o hasta max_swipes segmentos completos).
    Envia antes los comandos dados (sin fin de linea). Devuelve el StreamParser."""
    import serial  # pyserial
    ps = StreamParser()
    with serial.Serial(port, 115200, timeout=0.05) as s:
        for c in commands:
            s.write((c + "\n").encode("ascii"))
            time.sleep(0.05)
        t_end = time.time() + seconds
        nseg = 0
        try:
            while time.time() < t_end:
                for f in ps.feed(s.read(65536)):
                    if f["type"] == TYPE_SAMPLES and f["flags"] & FLAG_SEG_LAST:
                        nseg += 1
                        if not quiet:
                            print(f"segmento {nseg} completo (seq {f['seq']}, perdidos {f['drop_count']})")
                if max_swipes and nseg >= max_swipes:
                    break
        except KeyboardInterrupt:
            pass
        s.write(b"STOP\n")
        time.sleep(0.1)
        ps.feed(s.read(1 << 20))
    return ps


def import_wav(path: str, meta: dict | None = None, volts_full_scale: float = 1.0,
               swap: bool = False) -> swipefile.Swipe:
    """WAV de tarjeta de sonido (96/192 kHz). Canal izquierdo -> A, derecho -> B.
    La escala completa del WAV se lleva a +-2047 cuentas alrededor de 2048 y se anota
    volts_per_count = volts_full_scale / 2047 (calibrar volts_full_scale con un tono conocido)."""
    from scipy.io import wavfile
    fs, d = wavfile.read(path)
    d = np.asarray(d)
    if d.ndim == 1:
        d = d[:, None]
    if np.issubdtype(d.dtype, np.integer):
        full = float(np.iinfo(d.dtype).max) if d.dtype != np.uint8 else 127.0
        x = (d.astype(float) - (128.0 if d.dtype == np.uint8 else 0.0)) / full
    else:
        x = d.astype(float)
    codes = np.clip(np.round(2048 + (x - np.median(x, axis=0)) * 2047), 0, 4095).astype(np.int16)
    a = codes[:, 0]
    b = codes[:, 1] if codes.shape[1] > 1 else np.zeros(0, np.int16)
    if swap and len(b):
        a, b = b, a
    m = swipefile.new_meta()
    if meta:
        m.update(meta)
    m["capture_source"] = "wav"
    m["volts_per_count"] = volts_full_scale / 2047.0
    return swipefile.Swipe(chA=a, chB=b, dig=np.zeros(0, np.uint8), fs=float(fs),
                           gate_edges=np.zeros((0, 3)), meta=m)


def import_csv(path: str, meta: dict | None = None, volts_per_count: float | None = None,
               fs: float | None = None) -> swipefile.Swipe:
    """CSV de osciloscopio: columnas tiempo (s), CH1 (V) [, CH2 (V)]. Se saltan las lineas de
    cabecera no numericas; separador coma, punto y coma o tabulador. Si no hay columna de
    tiempo utilizable hay que dar fs. Los voltios se pasan a cuentas alrededor de 2048 quitando
    la mediana. Sin volts_per_count se usa 3.3/4096; si la senal no cabe en 12 bits se elige
    la escala minima que evita el recorte (queda anotada en meta['volts_per_count'])."""
    rows = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for ln in f:
            ln = ln.strip().replace(";", ",").replace("\t", ",")
            if not ln:
                continue
            try:
                vals = [float(v) for v in ln.split(",") if v.strip() != ""]
            except ValueError:
                continue
            if len(vals) >= 2:
                rows.append(vals[:3])
    if len(rows) < 16:
        raise ValueError("CSV sin suficientes filas numericas")
    ncol = min(len(r) for r in rows)
    arr = np.array([r[:ncol] for r in rows], float)
    t = arr[:, 0]
    if fs is None:
        dt = np.median(np.diff(t))
        if not dt > 0:
            raise ValueError("la primera columna no es un tiempo creciente; indique fs")
        fs = 1.0 / dt
    v = arr[:, 1:] - np.median(arr[:, 1:], axis=0)
    if volts_per_count is None:
        volts_per_count = max(swipefile.VOLTS_PER_COUNT, float(np.max(np.abs(v))) / 2040.0)
    codes = np.clip(np.round(2048 + v / volts_per_count), 0, 4095).astype(np.int16)
    m = swipefile.new_meta()
    if meta:
        m.update(meta)
    m["capture_source"] = "csv"
    m["volts_per_count"] = float(volts_per_count)
    return swipefile.Swipe(chA=codes[:, 0], chB=codes[:, 1] if codes.shape[1] > 1 else np.zeros(0, np.int16),
                           dig=np.zeros(0, np.uint8), fs=float(fs), gate_edges=np.zeros((0, 3)), meta=m)


def _load_meta(path):
    if not path:
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Captura de pasadas MagHead")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serial", help="leer el firmware por USB CDC")
    s.add_argument("--port", required=True)
    s.add_argument("--out", required=True, help="carpeta de salida")
    s.add_argument("--meta", help="JSON con metadatos comunes (plantilla)")
    s.add_argument("--rate", type=int, default=250000, help="Hz por canal")
    s.add_argument("--chan", default="AB", choices=["AB", "A", "B"])
    s.add_argument("--continuous", action="store_true", help="sin disparo (flujo continuo)")
    s.add_argument("--thr", type=int, default=150, help="umbral de disparo, cuentas")
    s.add_argument("--seconds", type=float, default=60.0)
    s.add_argument("--swipes", type=int, default=0, help="parar tras N pasadas")
    s.add_argument("--prefix", default="swipe")
    b = sub.add_parser("bin", help="convertir un flujo binario ya guardado")
    b.add_argument("file"); b.add_argument("--out", required=True); b.add_argument("--meta")
    b.add_argument("--prefix", default="swipe")
    w = sub.add_parser("wav", help="importar WAV")
    w.add_argument("file"); w.add_argument("--out", required=True); w.add_argument("--meta")
    w.add_argument("--volts-full-scale", type=float, default=1.0)
    c = sub.add_parser("csv", help="importar CSV de osciloscopio")
    c.add_argument("file"); c.add_argument("--out", required=True); c.add_argument("--meta")
    c.add_argument("--volts-per-count", type=float); c.add_argument("--fs", type=float)
    a = ap.parse_args(argv)
    meta = _load_meta(a.meta)

    if a.cmd in ("serial", "bin"):
        if a.cmd == "serial":
            cmds = ["STOP", f"CHAN {a.chan}", f"RATE {a.rate}", f"THR {a.thr}",
                    "TRIG OFF" if a.continuous else "TRIG ON", "VER", "START"]
            ps = read_serial(a.port, a.seconds, cmds, a.swipes)
        else:
            ps = StreamParser()
            with open(a.file, "rb") as f:
                ps.feed(f.read())
        ver = next((ln for ln in ps.lines if ln.startswith("#VER")), None)
        if ver:
            meta.setdefault("firmware_version", ver[4:].strip())
        swipes = frames_to_swipes(ps.frames, meta)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        for i, sw in enumerate(swipes):
            base = swipefile.save(sw, f"{a.out}/{a.prefix}_{stamp}_{i:03d}")
            print(f"{base}: {len(sw.chA) or len(sw.chB)} muestras/canal, fs={sw.fs:.0f} Hz, "
                  f"bloques perdidos={sw.meta['dropped_blocks']}")
        print(f"tramas={len(ps.frames)} errores_crc={ps.crc_errors} basura={ps.junk_bytes} B")
        for ln in ps.lines:
            print("  fw:", ln)
        return 0
    sw = import_wav(a.file, meta, a.volts_full_scale) if a.cmd == "wav" else \
        import_csv(a.file, meta, a.volts_per_count, a.fs)
    base = swipefile.save(sw, a.out)
    print(f"{base}: {len(sw.chA)} muestras, fs={sw.fs:.0f} Hz")
    for p in swipefile.validate_meta(sw.meta):
        print("  aviso metadatos:", p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
