"""Generador de senal sintetica de cabezal lector (tarjetas ISO 7811 de laboratorio).

Modelo (idealizado, NO es una prediccion de un cabezal real):
  * cadena -> bits ISO 7811 (paridad impar por caracter, LRC) con ceros delante y detras;
  * transiciones de flujo sobre la tarjeta (celda = 25.4 mm / bpi; F2F: una transicion
    en cada frontera de celda y otra en el centro de las celdas '1');
  * perfil de velocidad v(p) a lo largo del recorrido (constante, aceleracion lineal,
    variacion "de mano" +-30 %), en cualquiera de los dos sentidos;
  * tension del cabezal = suma de pulsos lorentzianos de signo alterno, de anchura
    PW50 ESPACIAL (um) y amplitud proporcional a la velocidad instantanea;
  * + zumbido de 60 Hz + ruido blanco (RMS definido en la banda del AFE) + deriva lenta;
  * AFE: paso alto 16 Hz (1 polo) y paso bajo 40 kHz (2 polos, Butterworth);
  * ADC de 12 bits centrado en 1.65 V (3.3 V fondo de escala) con ganancia configurable.
Devuelve la senal y la verdad-terreno (tiempos de transicion, bits, caracteres).
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
import numpy as np
from scipy import signal as sps

CARD_LEN_M = 85.60e-3          # ISO 7810 ID-1
SS_POS_M = 7.44e-3             # ISO 7811: inicio del SS desde el borde (pistas 1 y 2)
VREF = 3.3
ADC_FS = 4096
ADC_MID = 2048
GATE_SPACING_M = 20.00e-3
AFE_HPF_HZ = 16.0
AFE_LPF_HZ = 40e3

TRACKS = {1: dict(fmt=1, bpi=210), 2: dict(fmt=2, bpi=75), 3: dict(fmt=2, bpi=210)}


def fmt_params(fmt: int):
    """(bits por caracter, offset ASCII, SS, ES) para fmt 1 (pista 1) o 2 (pistas 2/3)."""
    return (7, 0x20, "%", "?") if fmt == 1 else (5, 0x30, ";", "?")


def encode_chars(text: str, fmt: int) -> np.ndarray:
    """Cadena completa (SS..ES incluidos) -> bits SS..ES + LRC (LSB primero, paridad impar)."""
    nb, base, ss, es = fmt_params(fmt)
    nd = nb - 1
    if not (text.startswith(ss) and text.endswith(es)):
        raise ValueError(f"la cadena debe empezar por {ss!r} y acabar en {es!r}")
    bits = []
    lrc = 0
    for ch in text:
        val = ord(ch) - base
        if not 0 <= val < (1 << nd):
            raise ValueError(f"caracter {ch!r} fuera del alfabeto de la pista")
        lrc ^= val
        d = [(val >> k) & 1 for k in range(nd)]
        bits += d + [1 - (sum(d) & 1)]
    d = [(lrc >> k) & 1 for k in range(nd)]
    bits += d + [1 - (sum(d) & 1)]
    return np.array(bits, dtype=np.uint8)


def lrc_char(text: str, fmt: int) -> str:
    nb, base, _, _ = fmt_params(fmt)
    v = 0
    for ch in text:
        v ^= ord(ch) - base
    return chr(base + v)


def guess_track(text: str) -> int:
    return 1 if text.startswith("%") else 2


def transitions_from_bits(bits, cell_m: float, x0_m: float = 0.0) -> np.ndarray:
    """Posiciones (m) de las transiciones de flujo F2F para una secuencia de celdas."""
    bits = np.asarray(bits)
    k = np.arange(len(bits))
    edges = np.concatenate([k, [len(bits)]]) * cell_m
    mids = (k[bits == 1] + 0.5) * cell_m
    return np.sort(np.concatenate([edges, mids])) + x0_m


@dataclass
class SynthParams:
    text: str = ";1234567890123445=99011200XXXX00000000?"
    track: int | None = None          # 1, 2 o 3; None = deducir del SS
    bpi: float | None = None          # None = el de la pista
    fs: float = 250e3                 # Hz por canal
    speed: float = 0.5                # m/s (media; en 'accel' es la velocidad inicial)
    profile: str = "const"            # 'const' | 'accel' | 'hand'
    v_end: float | None = None        # 'accel': velocidad final (m/s)
    hand_depth: float = 0.30          # 'hand': desviacion maxima relativa
    reverse: bool = False             # pasada en sentido contrario
    pw50_um: float = 40.0             # anchura a media altura del pulso aislado (espacial)
    sens_uV_s_per_m: float = 10000.0  # pico aislado (uV) = sens * v (m/s)
    gain: float | None = None         # ganancia AFE V/V; None = pico aislado a v max ~ 0.6 V
    noise_uV_rms: float = 0.0         # ruido referido al cabezal, RMS en la banda del AFE
    snr_db: float | None = None       # alternativa: pico aislado a v nominal / ruido RMS
    hum_uV: float = 0.0               # amplitud de pico del zumbido, referida al cabezal
    hum_hz: float = 60.0
    wander_mV: float = 0.0            # deriva lenta de linea base en el ADC (pico)
    lead_zeros: int | None = None     # None = hasta ~0.5 mm del borde
    trail_zeros: int | None = None    # None = hasta ~0.5 mm del otro borde
    quiet_ms: float = 30.0            # silencio (solo ruido) antes y despues
    gates: bool = True                # simular las dos barreras opticas
    gate_pos_mm: tuple = (-25.0, -5.0)  # posicion de las barreras respecto al cabezal
    seed: int | None = 0


@dataclass
class SynthSwipe:
    adc: np.ndarray                   # int16, codigos 0..4095
    fs: float
    gate1: np.ndarray                 # uint8, 1 = tarjeta presente
    gate2: np.ndarray
    gate_edges: np.ndarray            # filas [t_s, n_barrera (1|2), nivel (1 = presente)]
    t_trans: np.ndarray               # verdad: tiempos de transicion (s), orden temporal
    v_trans: np.ndarray               # verdad: velocidad en cada transicion (m/s)
    bits_card: np.ndarray             # todas las celdas en orden de tarjeta (ceros incluidos)
    data_bits: np.ndarray             # SS..ES + LRC
    text: str
    fmt: int
    track: int
    bpi: float
    cell_m: float
    lead_zeros: int
    trail_zeros: int
    gain: float
    noise_rms_counts: float           # ruido RMS en cuentas ADC (en banda)
    iso_peak_counts: float            # pico aislado a velocidad nominal, cuentas
    v_mean: float
    params: SynthParams = field(default_factory=SynthParams)

    @property
    def t(self):
        return np.arange(len(self.adc)) / self.fs


def velocity_profile(p: np.ndarray, prm: SynthParams, rng) -> np.ndarray:
    """v(p) sobre la rejilla de recorrido p (m)."""
    u = (p - p[0]) / (p[-1] - p[0])
    if prm.profile == "const":
        return np.full_like(p, prm.speed)
    if prm.profile == "accel":
        v0, v1 = prm.speed, (prm.v_end if prm.v_end is not None else prm.speed * 2)
        return np.sqrt(v0 ** 2 + (v1 ** 2 - v0 ** 2) * u)   # aceleracion constante en el tiempo
    if prm.profile == "hand":
        w = np.zeros_like(p)
        for cyc in (0.6, 1.3, 2.4):                          # ciclos a lo largo del recorrido
            w += rng.uniform(0.5, 1.0) * np.sin(2 * np.pi * (cyc * u + rng.uniform()))
        w /= np.max(np.abs(w))
        return prm.speed * (1.0 + prm.hand_depth * w)
    raise ValueError(f"perfil desconocido: {prm.profile}")


def afe_filter(x: np.ndarray, fs: float) -> np.ndarray:
    """Paso banda del AFE: HPF 16 Hz (1 polo) + LPF 40 kHz (2 polos)."""
    bh, ah = sps.butter(1, AFE_HPF_HZ, "highpass", fs=fs)
    bl, al = sps.butter(2, min(AFE_LPF_HZ, 0.45 * fs), "lowpass", fs=fs)
    return sps.lfilter(bl, al, sps.lfilter(bh, ah, x))


def afe_delay_s(fs: float) -> float:
    """Retardo de grupo en baja frecuencia del LPF de 2 polos."""
    return np.sqrt(2.0) / (2 * np.pi * min(AFE_LPF_HZ, 0.45 * fs))


def lorentz_train(xg: np.ndarray, xk: np.ndarray, pw50: float, span: float = 40.0) -> np.ndarray:
    """Suma de lorentzianas alternas de FWHM pw50 centradas en xk, evaluada en la rejilla xg."""
    s = np.zeros_like(xg)
    dx = xg[1] - xg[0]
    hw = int(np.ceil(span * pw50 / dx))
    for k, x in enumerate(xk):
        c = int(round((x - xg[0]) / dx))
        a, b = max(c - hw, 0), min(c + hw + 1, len(xg))
        if a >= b:
            continue
        u = (xg[a:b] - x) / pw50
        s[a:b] += (1.0 if k % 2 == 0 else -1.0) / (1.0 + 4.0 * u * u)
    return s


def synthesize(prm: SynthParams | None = None, **kw) -> SynthSwipe:
    """Genera una pasada sintetica. Acepta un SynthParams o sus campos por nombre."""
    if prm is None:
        prm = SynthParams(**kw)
    elif kw:
        prm = SynthParams(**{**asdict(prm), **kw})
    rng = np.random.default_rng(prm.seed)
    track = prm.track or guess_track(prm.text)
    fmt = TRACKS[track]["fmt"]
    bpi = prm.bpi or TRACKS[track]["bpi"]
    cell = 25.4e-3 / bpi
    pw50 = prm.pw50_um * 1e-6

    # --- bits y posiciones sobre la tarjeta ---
    data = encode_chars(prm.text, fmt)
    lead = prm.lead_zeros if prm.lead_zeros is not None else int((SS_POS_M - 0.5e-3) / cell)
    x_first = SS_POS_M - lead * cell
    room = int((CARD_LEN_M - 0.5e-3 - (SS_POS_M + len(data) * cell)) / cell)
    if room < 0:
        raise ValueError("la cadena no cabe en la tarjeta a esta densidad")
    trail = prm.trail_zeros if prm.trail_zeros is not None else room
    bits_card = np.concatenate([np.zeros(lead, np.uint8), data, np.zeros(trail, np.uint8)])
    xk = transitions_from_bits(bits_card, cell, x_first)

    # --- recorrido p (posicion del borde de entrada respecto al cabezal) y tiempo ---
    p0 = (min(prm.gate_pos_mm) - 3.0) * 1e-3 if prm.gates else -3.0e-3
    p1 = CARD_LEN_M + 3.0e-3
    pg = np.linspace(p0, p1, 4001)
    vg = velocity_profile(pg, prm, rng)
    tg = np.concatenate([[0.0], np.cumsum(np.diff(pg) * 2.0 / (vg[1:] + vg[:-1]))])
    quiet = prm.quiet_ms * 1e-3
    n_move = int(np.ceil(tg[-1] * prm.fs))
    nq = int(round(quiet * prm.fs))
    n = n_move + 2 * nq
    tm = np.arange(n_move) / prm.fs
    p_t = np.interp(tm, tg, pg)
    v_t = np.interp(tm, tg, vg)
    xc_t = (CARD_LEN_M - p_t) if prm.reverse else p_t       # coordenada de tarjeta bajo el cabezal

    # --- forma de onda espacial y tension del cabezal ---
    dx = min(pw50 / 20.0, cell / 50.0)
    xg = np.arange(-3.5e-3, CARD_LEN_M + 3.5e-3, dx)
    s_x = lorentz_train(xg, xk, pw50)
    v_nom = float(np.mean(vg)) if prm.profile != "accel" else float(prm.speed)
    v_nom = float(np.interp(0.5 * (p0 + p1), pg, vg)) if prm.profile == "accel" else v_nom
    sens = prm.sens_uV_s_per_m * 1e-6                        # V s / m
    head = np.zeros(n)
    head[nq:nq + n_move] = sens * v_t * np.interp(xc_t, xg, s_x)
    tt = np.arange(n) / prm.fs
    if prm.hum_uV:
        head += prm.hum_uV * 1e-6 * np.sin(2 * np.pi * prm.hum_hz * tt + rng.uniform(0, 2 * np.pi))

    iso_peak_v = sens * v_nom                                # pico aislado a velocidad nominal (V, cabezal)
    noise_v = prm.noise_uV_rms * 1e-6
    if prm.snr_db is not None:
        noise_v = iso_peak_v / (10.0 ** (prm.snr_db / 20.0))
    gain = prm.gain if prm.gain is not None else 0.6 / (sens * float(np.max(vg)))

    out = afe_filter(head, prm.fs)
    if noise_v > 0:
        nz = afe_filter(rng.standard_normal(n + 4096), prm.fs)[4096:]
        out += nz * (noise_v / np.std(nz))                   # RMS exacto en la banda del AFE
    out_v = VREF / 2 + gain * out
    if prm.wander_mV:
        out_v += prm.wander_mV * 1e-3 * np.sin(2 * np.pi * rng.uniform(1.0, 4.0) * tt + rng.uniform(0, 6.28))
    adc = np.clip(np.round(out_v / VREF * ADC_FS), 0, ADC_FS - 1).astype(np.int16)

    # --- verdad-terreno ---
    pk = (CARD_LEN_M - xk) if prm.reverse else xk
    t_tr = np.interp(pk, pg, tg) + quiet + afe_delay_s(prm.fs)
    v_tr = np.interp(pk, pg, vg)
    order = np.argsort(t_tr)
    t_tr, v_tr = t_tr[order], v_tr[order]

    # --- barreras opticas ---
    g1 = np.zeros(n, np.uint8)
    g2 = np.zeros(n, np.uint8)
    edges = []
    if prm.gates:
        for gi, (arr, gp) in enumerate(zip((g1, g2), prm.gate_pos_mm), start=1):
            te = float(np.interp(gp * 1e-3, pg, tg)) + quiet
            arr[int(np.ceil(te * prm.fs)):] = 1
            edges.append([te, gi, 1])
    cnt = VREF / ADC_FS
    return SynthSwipe(
        adc=adc, fs=float(prm.fs), gate1=g1, gate2=g2,
        gate_edges=np.array(edges, dtype=float).reshape(-1, 3),
        t_trans=t_tr, v_trans=v_tr, bits_card=bits_card, data_bits=data, text=prm.text,
        fmt=fmt, track=track, bpi=float(bpi), cell_m=cell, lead_zeros=lead, trail_zeros=trail,
        gain=float(gain), noise_rms_counts=float(noise_v * gain / cnt),
        iso_peak_counts=float(iso_peak_v * gain / cnt), v_mean=float(np.mean(vg)), params=prm)


def comparator(adc, hyst_counts: int = 60, mid: int = ADC_MID) -> np.ndarray:
    """Comparador con histeresis sobre la senal (modelo de la salida digital F2F, GP2/GP3)."""
    x = np.asarray(adc, dtype=np.int32) - mid
    hi = x > hyst_counts
    lo = x < -hyst_counts
    state = np.zeros(len(x), np.int8)
    state[hi] = 1
    state[lo] = -1
    idx = np.where(state != 0, np.arange(len(x)), 0)      # arrastrar el ultimo estado no nulo
    np.maximum.accumulate(idx, out=idx)
    return (state[idx] > 0).astype(np.uint8)


def to_swipe(sw: SynthSwipe, chB: np.ndarray | None = None, meta: dict | None = None):
    """Convierte una pasada sintetica al formato de archivo (swipefile.Swipe)."""
    from . import swipefile
    comp = comparator(sw.adc)
    dig = (sw.gate1 | (sw.gate2 << 1) | (comp << 2)).astype(np.uint8)
    if chB is not None:
        dig |= (comparator(chB) << 3).astype(np.uint8)
    m = swipefile.new_meta()
    prm = sw.params
    m.update(card_id="SYNTH", expected_tracks={str(sw.track): sw.text}, track_under_test=sw.track,
             head_variant="synth", afe_gain_a=sw.gain, afe_gain_b=sw.gain,
             nominal_speed_m_s=prm.speed, speed_source="synthetic",
             notes=f"sintetico: pw50={prm.pw50_um} um perfil={prm.profile} reverse={prm.reverse}")
    m["synthetic"] = {"t_trans": sw.t_trans.tolist(), "noise_rms_counts": sw.noise_rms_counts,
                      "iso_peak_counts": sw.iso_peak_counts, "pw50_um": prm.pw50_um,
                      "snr_db": prm.snr_db, "v_mean": sw.v_mean}
    if meta:
        m.update(meta)
    return swipefile.Swipe(chA=sw.adc, chB=chB if chB is not None else np.zeros(0, np.int16),
                           dig=dig, fs=sw.fs, gate_edges=sw.gate_edges, meta=m)
