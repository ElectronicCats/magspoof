"""Decodificador F2F / ISO 7811 de referencia (offline).

`decode()` replica ENTERO A ENTERO el modulo C fw/common/f2f_decode.c (misma
aritmetica, mismos umbrales); la prueba tests/test_c_decoder.py exige resultados
identicos. Cualquier cambio debe hacerse en los dos sitios.

Cadena causal:
  muestras ADC -> suma de bloques de M muestras, y[j] = b[j] + b[j-1] (ventana 2M)
  -> detector de picos de polaridad alternada con histeresis = fraccion de la
  envolvente pico-pico seguida (con suelo minimo) -> tiempo de pico interpolado
  (parabola por 3 puntos) -> intervalos -> seguidor de periodo de bit con IIR
  acotado -> bits -> ISO 7811 (pista 1: 7 bits; pistas 2/3: 5 bits), ambos
  sentidos, paridad impar por caracter y LRC.
Se ejecutan varias instancias con M = 1, 2, 4 ... 64 y se elige el mejor resultado.

`decode_noncausal()` es una variante solo-host (filtro de fase cero y periodo
local estimado mirando a ambos lados); NO existe en el firmware.

Tiempo en "ticks": 1 muestra = TICKS_PER_SAMPLE ticks.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import numpy as np

TICKS_PER_SAMPLE = 64
MAX_BITS = 1024
MAX_CHARS = 112
MAX_PERR = 16
DEFAULT_DECIMS = (1, 2, 4, 8, 16, 32, 64)

OK, NO_SIGNAL, NO_START, NO_END, PARITY_ERR, LRC_ERR = range(6)
STATUS_NAMES = ["OK", "NO_SIGNAL", "NO_START", "NO_END", "PARITY_ERR", "LRC_ERR"]
FMT_AUTO, FMT_T1, FMT_T2 = 0, 1, 2
DIR_FWD, DIR_REV = 0, 1
_RANK = {OK: 5, LRC_ERR: 4, PARITY_ERR: 3, NO_END: 2, NO_START: 1, NO_SIGNAL: 0}


@dataclass
class Config:
    """Mismos campos y valores por defecto que f2f_cfg_t."""
    thr_frac_q8: int = 51
    noise_floor: int = 24
    class_thr_q8: int = 184
    pair_thr_q8: int = 320
    period_alpha_shift: int = 2
    period_bound_shift: int = 2
    sync_count: int = 4
    sync_tol_q8: int = 51
    min_transitions: int = 10
    min_lead_zeros: int = 4
    min_seg_bits: int = 24


@dataclass
class Result:
    status: int = NO_START
    fmt: int = FMT_AUTO
    direction: int = DIR_FWD
    lrc_ok: bool = False
    instance: int = 0
    n_transitions: int = 0
    f2f_errors: int = 0
    n_bits: int = 0
    n_chars: int = 0
    n_parity_err: int = 0
    parity_pos: list = field(default_factory=list)
    leading_zeros: int = 0
    ss_bit: int = 0
    end_bit: int = 0
    lrc_value: int = 0
    period_min: int = 0
    period_max: int = 0
    text: str = ""
    # --- extras solo Python (analisis) ---
    tick_hz: float = 0.0
    decim: int = 1
    trans_ticks: np.ndarray | None = None    # tiempos de transicion, ticks
    trans_value: np.ndarray | None = None    # valor del pico (suma de 2*decim muestras)
    trans_period: np.ndarray | None = None   # periodo seguido tras cada transicion (0 = sin enganche)
    bits: np.ndarray | None = None           # bits en orden de llegada (sin orientar)
    bit_period: np.ndarray | None = None
    bit_tidx: np.ndarray | None = None       # indice de la transicion que cierra cada bit

    @property
    def status_name(self) -> str:
        return STATUS_NAMES[self.status]

    @property
    def ok(self) -> bool:
        return self.status == OK

    @property
    def transition_times(self) -> np.ndarray:
        """Tiempos de transicion en segundos."""
        if self.trans_ticks is None or not self.tick_hz:
            return np.zeros(0)
        return np.asarray(self.trans_ticks, dtype=float) / self.tick_hz

    def oriented_bits(self) -> np.ndarray:
        """Bits en el sentido de lectura del resultado (SS antes que ES)."""
        b = np.asarray(self.bits if self.bits is not None else [], dtype=np.uint8)
        return b[::-1] if self.direction == DIR_REV else b


def _tdiv(a: int, b: int) -> int:
    """Division entera truncada hacia cero (como en C)."""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b >= 0) else -q


# --------------------------------------------------------------------- picos

def decimate(x, decim: int) -> np.ndarray:
    """y[j] = b[j] + b[j-1], con b = sumas de bloques de `decim` muestras. Devuelve y[1:]
    (el indice j de y[k] es k + 1)."""
    x = np.asarray(x).astype(np.int64) & 0x0FFF
    nb = len(x) // decim
    b = x[: nb * decim].reshape(nb, decim).sum(axis=1)
    return b[1:] + b[:-1]


def find_peaks_causal(x, decim: int = 1, cfg: Config | None = None):
    """Detector de picos alternados. Devuelve (ticks, valores) como listas de enteros."""
    cfg = cfg or Config()
    ys = decimate(x, decim).tolist()
    frac = cfg.thr_frac_q8
    fl = cfg.noise_floor * 2 * decim
    tpd = TICKS_PER_SAMPLE * decim
    half = tpd // 2
    out_t, out_v = [], []
    state = 0
    ext = ext_prev = ext_next = 0
    ext_j = 0
    has_next = False
    env = 0
    since_peak = 0
    last_gap = 0
    last_peak = 0
    have_last_peak = False
    if not ys:
        return out_t, out_v
    init_min = init_max = y_prev = ys[0]
    j = 0
    for y in ys:
        j += 1
        h = (frac * env) >> 8
        if h < fl:
            h = fl
        since_peak += 1
        tmo = 8 * last_gap
        if tmo < 64:
            tmo = 64
        if since_peak >= tmo and since_peak % tmo == 0:
            env -= env >> 2
        emit = False
        if state == 0:
            if y < init_min:
                init_min = y
            if y > init_max:
                init_max = y
            if y - init_min >= h:
                state = 1
                ext = y; ext_j = j; ext_prev = y_prev; has_next = False
            elif init_max - y >= h:
                state = -1
                ext = y; ext_j = j; ext_prev = y_prev; has_next = False
        elif state > 0:
            if y > ext:
                ext = y; ext_j = j; ext_prev = y_prev; has_next = False
            else:
                if not has_next:
                    ext_next = y; has_next = True
                if ext - y >= h:
                    emit = True
        else:
            if y < ext:
                ext = y; ext_j = j; ext_prev = y_prev; has_next = False
            else:
                if not has_next:
                    ext_next = y; has_next = True
                if y - ext >= h:
                    emit = True
        if emit:
            den = ext_prev - 2 * ext + ext_next
            off = 0
            if den != 0:
                off = _tdiv((ext_prev - ext_next) * tpd, 2 * den)
                if off > half:
                    off = half
                if off < -half:
                    off = -half
            out_t.append(tpd * ext_j - TICKS_PER_SAMPLE // 2 + off)
            out_v.append(ext)
            if have_last_peak:
                pp = abs(ext - last_peak)
                if pp > env:
                    env += (pp - env) >> 1
                else:
                    env -= (env - pp) >> 3
            last_peak = ext
            have_last_peak = True
            last_gap = since_peak
            since_peak = 0
            state = -state
            ext = y; ext_j = j; ext_prev = y_prev; has_next = False
        y_prev = y
    return out_t, out_v


# --------------------------------------------------------------------- bits

class BitTracker:
    """Seguidor de periodo de bit + clasificacion F2F (replica de bits_feed en C)."""

    def __init__(self, cfg: Config | None = None):
        self.cfg = cfg or Config()
        self.last_t = None
        self.n_trans = 0
        self.locked = False
        self.period = 0
        self.sync_sum = 0
        self.sync_n = 0
        self.half_pending = False
        self.half_iv = 0
        self.err_level = 0
        self.seg_start = 0
        self.f2f_errors = 0
        self.bits: list[int] = []
        self.bit_period: list[int] = []
        self.bit_tidx: list[int] = []
        self.trans_period: list[int] = []

    def _room(self):
        if len(self.bits) >= MAX_BITS and self.seg_start > 0:
            del self.bits[:self.seg_start]
            del self.bit_period[:self.seg_start]
            del self.bit_tidx[:self.seg_start]
            self.seg_start = 0

    def _emit(self, b, per):
        self._room()
        if len(self.bits) < MAX_BITS:
            self.bits.append(b)
            self.bit_period.append(int(per))
            self.bit_tidx.append(self.n_trans - 1)

    def _update(self, meas):
        p = self.period
        diff = meas - p
        bound = p >> self.cfg.period_bound_shift
        if diff > bound:
            diff = bound
        if diff < -bound:
            diff = -bound
        if diff >= 0:
            p += diff >> self.cfg.period_alpha_shift
        else:
            p -= (-diff) >> self.cfg.period_alpha_shift
        self.period = max(p, 1)

    def _unlock(self):
        self.locked = False
        self.sync_n = 0
        self.sync_sum = 0
        self.half_pending = False
        self.err_level = 0
        if len(self.bits) - self.seg_start < self.cfg.min_seg_bits:
            del self.bits[self.seg_start:]
            del self.bit_period[self.seg_start:]
            del self.bit_tidx[self.seg_start:]
        else:
            self.seg_start = len(self.bits)

    def _error(self):
        self.f2f_errors += 1
        self.err_level += 4
        if self.err_level >= 12:
            self._unlock()

    def _good(self):
        if self.err_level > 0:
            self.err_level -= 1

    def feed(self, t: int):
        self._feed(int(t))
        self.trans_period.append(self.period if self.locked else 0)

    def _feed(self, t: int):
        cfg = self.cfg
        self.n_trans += 1
        if self.last_t is None:
            self.last_t = t
            return
        iv = t - self.last_t
        self.last_t = t
        if iv <= 0:
            return
        if not self.locked:
            if self.sync_n == 0:
                self.sync_sum = iv; self.sync_n = 1
            else:
                mean = self.sync_sum // self.sync_n
                if abs(iv - mean) * 256 <= cfg.sync_tol_q8 * mean:
                    self.sync_sum += iv; self.sync_n += 1
                else:
                    self.sync_sum = iv; self.sync_n = 1
            if self.sync_n >= cfg.sync_count:
                self.period = max(self.sync_sum // self.sync_n, 1)
                self.locked = True; self.half_pending = False; self.err_level = 0
                n = self.sync_n
                for i in range(n):
                    self._room()
                    if len(self.bits) < MAX_BITS:
                        self.bits.append(0)
                        self.bit_period.append(self.period)
                        self.bit_tidx.append(self.n_trans - n + i)
            return
        p = self.period
        if iv > 4 * p:
            self.f2f_errors += 1
            self._unlock()
            return
        if self.half_pending:
            s = self.half_iv + iv
            self.half_pending = False
            if s * 256 <= cfg.pair_thr_q8 * p:
                self._emit(1, s)
                self._update(s)
                self._good()
            else:
                self._emit(0, p)
                self._error()
            return
        if iv * 256 < cfg.class_thr_q8 * p:
            self.half_pending = True
            self.half_iv = iv
            return
        if iv * 2 > 3 * p:
            nb = (iv + p // 2) // p
            for _ in range(nb):
                self._emit(0, iv // nb)
            self._error()
            return
        self._emit(0, iv)
        self._update(iv)
        self._good()


# --------------------------------------------------------------------- ISO 7811

def result_better(a: Result, b: Result) -> bool:
    ra, rb = _RANK[a.status], _RANK[b.status]
    if ra != rb:
        return ra > rb
    sa, sb = a.n_chars - 2 * a.n_parity_err, b.n_chars - 2 * b.n_parity_err
    if sa != sb:
        return sa > sb
    return a.f2f_errors < b.f2f_errors


def _decode_one(bits, bper, fmt, rev, min_lead, best: Result) -> Result:
    n = len(bits)
    nb = 7 if fmt == FMT_T1 else 5
    nd = nb - 1
    ss_val = 0x05 if fmt == FMT_T1 else 0x0B
    es_val = 0x1F if fmt == FMT_T1 else 0x0F
    base = 0x20 if fmt == FMT_T1 else 0x30
    bb = bits[::-1] if rev else bits
    pp = (bper[::-1] if rev else bper) if bper is not None else None

    def char_at(pos):
        val = 0
        ones = 0
        for k in range(nb):
            if bb[pos + k]:
                ones += 1
                if k < nd:
                    val |= 1 << k
        return val, ones

    zeros = 0
    for s in range(0, n - nb + 1):
        lead = zeros
        zeros = 0 if bb[s] else zeros + 1
        if not bb[s] or lead < min_lead:
            continue
        val, ones = char_at(s)
        if val != ss_val or not (ones & 1):
            continue
        if pp is not None:      # solo ceros de periodo coherente (+-25 %)
            l2 = 0
            pn = pp[s]
            for i in range(s - 1, s - lead - 1, -1):
                if abs(pp[i] - pn) * 4 > pn:
                    break
                l2 += 1
                pn = pp[i]
            lead = l2
            if lead < min_lead:
                continue
        r = Result(fmt=fmt, direction=rev, leading_zeros=lead, ss_bit=s)
        pos = s
        found_es = False
        lrc = 0
        chars = []
        while pos + nb <= n and len(chars) < MAX_CHARS:
            val, ones = char_at(pos)
            if not (ones & 1):
                if r.n_parity_err < MAX_PERR:
                    r.parity_pos.append(len(chars))
                r.n_parity_err += 1
            lrc ^= val
            chars.append(chr(base + val))
            pos += nb
            if val == es_val and len(chars) > 1:
                found_es = True
                break
        r.text = "".join(chars)
        r.n_chars = len(chars)
        if not found_es or pos + nb > n:
            r.status = NO_END
        else:
            val, ones = char_at(pos)
            pos += nb
            r.lrc_value = val
            r.lrc_ok = bool(val == lrc and (ones & 1))
            if r.n_parity_err:
                r.status = PARITY_ERR
            else:
                r.status = OK if r.lrc_ok else LRC_ERR
        r.end_bit = pos
        if pp is not None:
            seg = pp[s - lead:pos]
            r.period_min = int(min(seg))
            r.period_max = int(max(seg))
        if result_better(r, best):
            best = r
        if best.status == OK:
            return best
    return best


def decode_bits(bits, bit_period=None, fmt: int = FMT_AUTO, min_lead_zeros: int = 4) -> Result:
    """Capa ISO 7811: bits -> caracteres. Prueba formato(s) y ambos sentidos."""
    bits = [int(b) for b in bits]
    bper = [int(p) for p in bit_period] if bit_period is not None else None
    best = Result(status=NO_START, fmt=fmt)
    for f in (FMT_T1, FMT_T2):
        if fmt != FMT_AUTO and fmt != f:
            continue
        for rev in (0, 1):
            best = _decode_one(bits, bper, f, rev, min_lead_zeros, best)
            if best.status == OK:
                break
        if best.status == OK:
            break
    best.n_bits = len(bits)
    return best


def _finish(tr: BitTracker, fmt, cfg: Config) -> Result:
    if tr.n_trans < cfg.min_transitions:
        r = Result(status=NO_SIGNAL, fmt=fmt)
    else:
        r = decode_bits(tr.bits, tr.bit_period, fmt, cfg.min_lead_zeros)
    r.n_bits = len(tr.bits)
    r.n_transitions = tr.n_trans
    r.f2f_errors = tr.f2f_errors
    r.bits = np.array(tr.bits, dtype=np.uint8)
    r.bit_period = np.array(tr.bit_period, dtype=np.int64)
    r.bit_tidx = np.array(tr.bit_tidx, dtype=np.int64)
    r.trans_period = np.array(tr.trans_period, dtype=np.int64)
    return r


def decode_instance(x, fs: float, fmt: int = FMT_AUTO, cfg: Config | None = None,
                    decim: int = 1) -> Result:
    """Una sola instancia (un diezmado), equivalente a f2f_init/feed/finish."""
    cfg = cfg or Config()
    t, v = find_peaks_causal(x, decim, cfg)
    tr = BitTracker(cfg)
    for ti in t:
        tr.feed(ti)
    r = _finish(tr, fmt, cfg)
    r.trans_ticks = np.array(t, dtype=np.int64)
    r.trans_value = np.array(v, dtype=np.int64)
    r.tick_hz = float(fs) * TICKS_PER_SAMPLE
    r.decim = decim
    return r


def decode(x, fs: float, fmt: int = FMT_AUTO, cfg: Config | None = None,
           decims=DEFAULT_DECIMS) -> Result:
    """Decodificador causal multi-instancia (equivalente a f2f_multi_*)."""
    best = None
    oks = []
    for i, m in enumerate(decims):
        r = decode_instance(x, fs, fmt, cfg, m)
        r.instance = i
        if r.status == OK:
            oks.append(r)
        if best is None or result_better(r, best):
            best = r
    if len(oks) > 1:            # varias correctas: la central (ver f2f_multi_finish)
        best = oks[(len(oks) - 1) // 2]
    return best


def decode_edges(times_ticks, tick_hz: float, fmt: int = FMT_AUTO,
                 cfg: Config | None = None) -> Result:
    """Ruta del comparador: marcas de tiempo de flancos (enteros) -> bits -> ISO."""
    cfg = cfg or Config()
    tr = BitTracker(cfg)
    for ti in times_ticks:
        tr.feed(int(ti))
    r = _finish(tr, fmt, cfg)
    r.trans_ticks = np.array([int(t) for t in times_ticks], dtype=np.int64)
    r.trans_value = np.zeros(len(r.trans_ticks), dtype=np.int64)
    r.tick_hz = float(tick_hz)
    return r


# --------------------------------------------------------------------- no causal

def _alt_peaks(y, h):
    """Picos alternados con histeresis h(t) (vector) sobre senal ya filtrada. Indices."""
    from scipy.signal import find_peaks
    hp = float(np.median(h))
    pk, _ = find_peaks(y, prominence=hp)
    vl, _ = find_peaks(-y, prominence=hp)
    idx = np.concatenate([pk, vl])
    sgn = np.concatenate([np.ones(len(pk), int), -np.ones(len(vl), int)])
    o = np.argsort(idx)
    idx, sgn = idx[o], sgn[o]
    keep = []
    for i, s in zip(idx.tolist(), sgn.tolist()):
        if keep and keep[-1][1] == s:           # misma polaridad seguida: el mayor
            if abs(y[i]) > abs(y[keep[-1][0]]):
                keep[-1] = (i, s)
        else:
            keep.append((i, s))
    return np.array([k[0] for k in keep], dtype=int)


def decode_noncausal(x, fs: float, fmt: int = FMT_AUTO, cfg: Config | None = None,
                     sigmas=(0.7, 2.0, 6.0, 18.0, 54.0)) -> Result:
    """Variante offline NO causal (solo host, no existe en el firmware).

    Filtro gaussiano de fase cero a varias escalas, picos por prominencia, y
    clasificacion de intervalos con periodo local suavizado mirando a ambos lados
    (mediana movil de las duraciones de bit, dos iteraciones)."""
    from scipy.ndimage import gaussian_filter1d, median_filter
    cfg = cfg or Config()
    x0 = (np.asarray(x).astype(np.int64) & 0x0FFF).astype(float)
    x0 -= np.median(x0)
    best = None
    for si, sg in enumerate(sigmas):
        y = gaussian_filter1d(x0, sg)
        amp = np.percentile(np.abs(y), 99.5)
        h = max(0.30 * 2 * amp * 0.6, float(cfg.noise_floor))
        idx = _alt_peaks(y, np.array([h]))
        idx = idx[(idx > 0) & (idx < len(y) - 1)]
        if len(idx) < cfg.min_transitions:
            r = Result(status=NO_SIGNAL, fmt=fmt, n_transitions=len(idx))
            r.trans_ticks = np.zeros(0, dtype=np.int64)
        else:
            ym, y0, yp = y[idx - 1], y[idx], y[idx + 1]
            den = ym - 2 * y0 + yp
            off = np.where(den != 0, 0.5 * (ym - yp) / np.where(den == 0, 1, den), 0.0)
            tt = np.round((idx + np.clip(off, -0.5, 0.5)) * TICKS_PER_SAMPLE).astype(np.int64)
            # pasada causal para etiquetar, luego periodo local suavizado y reclasificacion
            tr = BitTracker(cfg)
            for ti in tt:
                tr.feed(int(ti))
            for _ in range(2):
                if len(tr.bits) < 8:
                    break
                bp = np.array(tr.bit_period, float)
                sm = median_filter(bp, size=9, mode="nearest")
                tend = tt[np.array(tr.bit_tidx)]
                tr2 = _SmoothedTracker(cfg, tend, sm)
                for ti in tt:
                    tr2.feed(int(ti))
                tr = tr2
            r = _finish(tr, fmt, cfg)
            r.trans_ticks = tt
            r.trans_value = np.round(y[idx]).astype(np.int64)
        r.tick_hz = float(fs) * TICKS_PER_SAMPLE
        r.instance = si
        if best is None or result_better(r, best):
            best = r
    return best


class _SmoothedTracker(BitTracker):
    """BitTracker cuyo periodo se impone desde una estimacion externa P(t) (no causal)."""

    def __init__(self, cfg, t_knots, p_knots):
        super().__init__(cfg)
        self._tk = np.asarray(t_knots, float)
        self._pk = np.asarray(p_knots, float)

    def _feed(self, t):
        if self.locked:
            self.period = max(int(np.interp(t, self._tk, self._pk)), 1)
        super()._feed(t)

    def _update(self, meas):
        pass
