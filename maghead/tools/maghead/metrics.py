"""Metricas por pasada y veredictos L1/L2/L3.

Tres niveles de veredicto, deliberadamente separados:
  L1  senal detectada:           SNR > umbral (12 dB por defecto)
  L2  transiciones recuperadas:  100 % de las transiciones esperadas en la zona de datos
                                 (SS..LRC, deducidas de la cadena conocida), sin sobrantes
  L3  decodificacion completa:   cadena == esperada, paridad y LRC correctos

Definiciones:
  amplitud de pico   |pico - linea base| en cuentas ADC, con el mismo suavizado (ventana de
                     2*M muestras) que uso la instancia ganadora del decodificador
  ruido RMS          desviacion tipica en una ventana sin senal (antes o despues de la
                     pasada); incluye el zumbido de red que haya
  SNR (dB)           20*log10(mediana de picos de los ceros de cabecera / ruido RMS)
  velocidad          barreras: 20.00 mm / (t2 - t1); bits: celda / periodo de bit
  amplitud normal.   uV (referidos al cabezal, con la ganancia de los metadatos) / (m/s)
  PW50               anchura a media altura del pulso medio de las transiciones aisladas
                     (ceros de cabecera), en um; pw50_um corrige la interferencia entre
                     pulsos vecinos SUPONIENDO pulsos lorentzianos
  resolucion         amplitud de los pulsos de '1' / amplitud de los pulsos de '0'
"""
from __future__ import annotations

import math
import numpy as np

from . import decode as pydec
from . import swipefile, synth

GATE_SPACING_M = 20.00e-3
L1_SNR_DB = 12.0


def _decode(x, fs, fmt, decoder="auto", cfg=None):
    if decoder in ("auto", "c"):
        try:
            from . import cdecode
            return cdecode.decode(x, fs, fmt, cfg)
        except Exception:
            if decoder == "c":
                raise
    return pydec.decode(x, fs, fmt, cfg)


# ------------------------------------------------------------------ PW50 / ISI

_ISI_TAB = None


def _isi_table():
    """w_medida/B en funcion de PW50/B para un tren alterno de lorentzianas de paso B."""
    global _ISI_TAB
    if _ISI_TAB is None:
        r = np.concatenate([np.linspace(0.02, 0.3, 15), np.linspace(0.32, 1.6, 65)])
        u = np.linspace(0, 0.5, 2001)
        n = np.arange(-400, 401)
        sgn = np.where(n % 2 == 0, 1.0, -1.0)
        w = []
        for ri in r:
            s = (sgn[None, :] / (1 + 4 * ((u[:, None] - n[None, :]) / ri) ** 2)).sum(axis=1)
            w.append(2 * np.interp(0.5 * s[0], s[::-1], u[::-1]))
        _ISI_TAB = (r, np.array(w))
    return _ISI_TAB


def isi_correct(w_over_b: float) -> float:
    """PW50/B a partir de la anchura medida/B (NaN fuera del rango invertible)."""
    r, w = _isi_table()
    if not np.isfinite(w_over_b) or w_over_b <= 0 or w_over_b > 0.60:
        return float("nan")
    return float(np.interp(w_over_b, w, r))


def _fwhm(u, s):
    """Anchura a media altura de un pulso positivo s(u) con maximo cerca de u = 0."""
    k = int(np.argmax(s))
    half = 0.5 * s[k]
    i = k
    while i > 0 and s[i] > half:
        i -= 1
    j = k
    while j < len(s) - 1 and s[j] > half:
        j += 1
    if s[i] > half or s[j] > half:
        return float("nan")
    ul = u[i] + (half - s[i]) * (u[i + 1] - u[i]) / (s[i + 1] - s[i])
    ur = u[j - 1] + (half - s[j - 1]) * (u[j] - u[j - 1]) / (s[j] - s[j - 1])
    return float(ur - ul)


# ------------------------------------------------------------------ utilidades

def wilson(k: int, n: int, z: float = 1.959964):
    """Intervalo de Wilson al 95 % para una proporcion k/n. Devuelve (lo, hi)."""
    if n <= 0:
        return (float("nan"), float("nan"))
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, c - h), min(1.0, c + h))


def noise_window(x: np.ndarray, fs: float):
    """Busca una ventana sin senal. Devuelve (i0, i1) o None."""
    n = len(x)
    if n < 64:
        return None
    d = np.abs(x - np.median(x))
    k = max(int(fs * 1e-3), 1)
    env = np.convolve(d, np.ones(k) / k, mode="same")
    lim = 0.2 * np.max(env)
    act = np.flatnonzero(env > lim)
    if len(act) == 0:
        return (0, n)
    m = int(5e-3 * fs)
    a, b = act[0] - m, act[-1] + m
    pre, post = (0, max(a, 0)), (min(b, n), n)
    best = pre if (pre[1] - pre[0]) >= (post[1] - post[0]) else post
    return best if best[1] - best[0] >= max(int(5e-3 * fs), 64) else None


def noise_rms_fallback(x: np.ndarray, fs: float) -> float:
    """Ruido cuando la envolvente no delimita la pasada (SNR muy baja): mediana de la
    desviacion tipica del 20 % mas tranquilo de los tramos de 5 ms. Si no hay ningun
    tramo sin senal, sobreestima el ruido (veredicto L1 conservador)."""
    k = max(int(5e-3 * fs), 32)
    nchunk = len(x) // k
    if nchunk < 1:
        return float("nan")
    sd = np.sort(x[:nchunk * k].reshape(nchunk, k).std(axis=1))
    return float(np.median(sd[:max(1, nchunk // 5)]))


def expected_positions(data_bits) -> np.ndarray:
    """Posiciones de las transiciones de la zona de datos en unidades de media celda."""
    b = np.asarray(data_bits)
    k = np.arange(len(b))
    return np.sort(np.concatenate([2 * k, [2 * len(b)], 2 * k[b == 1] + 1]))


def match_transitions(tt_ticks, tper, data_bits):
    """Alinea las transiciones detectadas con las esperadas (por la cadena conocida).

    Cada intervalo se cuantiza a un numero entero de medias celdas con el periodo seguido
    por el decodificador; se prueba cada tramo enganchado, ambos sentidos y todos los
    desfases, y se elige el de mas coincidencias.
    Devuelve dict(expected, matched, missed, extra, direction)."""
    E = expected_positions(data_bits)
    L = int(E[-1])
    best = dict(expected=len(E), matched=0, missed=len(E), extra=0, direction=-1)
    tt = np.asarray(tt_ticks, dtype=np.int64)
    tper = np.asarray(tper, dtype=np.int64)
    if len(tt) < 2:
        return best
    # tramos de transiciones consecutivas con periodo valido
    segs, cur = [], [0]
    q = 0
    for k in range(1, len(tt)):
        p = tper[k] if tper[k] > 0 else (tper[k - 1] if tper[k - 1] > 0 else 0)
        if p <= 0:
            if len(cur) > 1:
                segs.append(cur)
            cur, q = [0], 0
            continue
        q += max(1, int(round(2.0 * (tt[k] - tt[k - 1]) / p)))
        cur.append(q)
    if len(cur) > 1:
        segs.append(cur)
    ind_e = [np.zeros(L + 1), np.zeros(L + 1)]
    ind_e[0][E] = 1
    ind_e[1][L - E] = 1
    for seg in segs:
        qs = np.array(seg)
        if qs[-1] < L // 2:
            continue
        ind_d = np.zeros(qs[-1] + 1)
        ind_d[qs] = 1
        for d in (0, 1):
            cc = np.correlate(ind_d, ind_e[d], mode="full")     # desfase = idx - L
            off = int(np.argmax(cc)) - L
            inr = qs[(qs >= off) & (qs <= off + L)] - off
            matched = int(ind_e[d][inr].sum())
            extra = len(inr) - matched
            if matched - extra > best["matched"] - best["extra"]:
                best = dict(expected=len(E), matched=matched, missed=len(E) - matched,
                            extra=int(extra), direction=d)
    return best


def match_truth(t_det, t_true):
    """Empareja tiempos detectados con la verdad-terreno (datos sinteticos).
    Tolerancia: 35 % del menor intervalo vecino. Devuelve (perdidas, sobrantes, rms_s)."""
    t_det = np.asarray(t_det, float)
    t_true = np.asarray(t_true, float)
    if len(t_true) < 2:
        return 0, len(t_det), float("nan")
    iv = np.diff(t_true)
    tol = 0.35 * np.minimum(np.concatenate([[iv[0]], iv]), np.concatenate([iv, [iv[-1]]]))
    used = np.zeros(len(t_det), bool)
    errs = []
    missed = 0
    idx = np.searchsorted(t_det, t_true)
    for k, t in enumerate(t_true):
        cand = [i for i in (idx[k] - 1, idx[k]) if 0 <= i < len(t_det) and not used[i]]
        cand = [i for i in cand if abs(t_det[i] - t) <= tol[k]]
        if not cand:
            missed += 1
            continue
        i = min(cand, key=lambda i: abs(t_det[i] - t))
        used[i] = True
        errs.append(t_det[i] - t)
    inside = (t_det >= t_true[0] - tol[0]) & (t_det <= t_true[-1] + tol[-1])
    extra = int((inside & ~used).sum())
    rms = float(np.sqrt(np.mean(np.square(errs)))) if errs else float("nan")
    return missed, extra, rms


# ------------------------------------------------------------------ analisis

def analyze(sw: swipefile.Swipe, channel: str | None = None, l1_snr_db: float = L1_SNR_DB,
            decoder: str = "auto", cfg: pydec.Config | None = None, return_result: bool = False):
    """Calcula todas las metricas de una pasada. Devuelve un dict plano (apto para CSV)."""
    meta = sw.meta
    channel = (channel or meta.get("channel_under_test") or "A").upper()
    x = np.asarray(sw.channel(channel)).astype(np.int64) & 0x0FFF
    fs = float(sw.fs)
    track = int(meta.get("track_under_test") or 2)
    fmt = synth.TRACKS[track]["fmt"]
    cell = 25.4e-3 / float(meta.get("bpi") or synth.TRACKS[track]["bpi"])
    expected = (meta.get("expected_tracks") or {}).get(str(track), "")
    vpc = float(meta.get("volts_per_count") or swipefile.VOLTS_PER_COUNT)
    gain = meta.get("afe_gain_b" if channel == "B" else "afe_gain_a")
    nan = float("nan")

    r = _decode(x, fs, fmt, decoder, cfg)
    out = dict(
        swipe_id=meta.get("swipe_id", ""), channel=channel, track=track,
        head_variant=meta.get("head_variant", ""), spacing_shim_um=meta.get("spacing_shim_um"),
        nominal_speed_m_s=meta.get("nominal_speed_m_s"), speed_source=meta.get("speed_source", ""),
        status=r.status_name, direction="REV" if r.direction else "FWD",
        decoded_text=r.text, expected_text=expected, n_transitions=r.n_transitions,
        n_bits=r.n_bits, leading_zeros=r.leading_zeros, n_parity_err=r.n_parity_err,
        parity_pos=" ".join(str(p) for p in r.parity_pos), lrc_ok=int(r.lrc_ok),
        f2f_errors=r.f2f_errors, decim=r.decim, dropped_blocks=meta.get("dropped_blocks", 0))

    # --- ruido en ventana sin senal ---
    nw = noise_window(x.astype(float), fs)
    if nw is not None:
        seg = x[nw[0]:nw[1]].astype(float)
        base = float(np.median(seg))
        noise = float(np.std(seg))
    else:
        base, noise = float(np.median(x)), noise_rms_fallback(x.astype(float), fs)
    out["noise_window"] = "envolvente" if nw is not None else "tramos_5ms"
    out["noise_rms_counts"] = noise
    out["noise_rms_mV_adc"] = noise * vpc * 1e3

    # --- amplitudes de pico y clasificacion de transiciones ---
    tt = np.asarray(r.trans_ticks if r.trans_ticks is not None else [], dtype=np.int64)
    nt = len(tt)
    amp = np.abs(np.asarray(r.trans_value, float) / (2.0 * r.decim) - base) if nt else np.zeros(0)
    per = np.asarray(r.trans_period, float) if r.trans_period is not None and nt else np.zeros(nt)
    is0 = np.zeros(nt, bool)
    is1 = np.zeros(nt, bool)
    if nt >= 3:
        iv = np.diff(tt).astype(float)
        p = np.where(per[1:-1] > 0, per[1:-1], np.inf)
        a, b = iv[:-1] / p, iv[1:] / p
        is0[1:-1] = (a > 0.75) & (a < 1.5) & (b > 0.75) & (b < 1.5)
        is1[1:-1] = (a > 0.25) & (a < 0.72) & (b > 0.25) & (b < 0.72)

    # zona de datos (SS..LRC) y ceros que la preceden EN EL TIEMPO
    in_data = np.zeros(nt, bool)
    in_pre = np.zeros(nt, bool)
    has_frame = r.status in (pydec.OK, pydec.PARITY_ERR, pydec.LRC_ERR) and r.bit_tidx is not None
    if has_frame:
        nb = len(r.bits)
        a_raw, b_raw = (r.ss_bit, r.end_bit) if r.direction == 0 else (nb - r.end_bit, nb - r.ss_bit)
        k0 = int(r.bit_tidx[a_raw - 1]) if a_raw >= 1 else 0
        k1 = int(r.bit_tidx[b_raw - 1])
        in_data[k0:k1 + 1] = True
        j = a_raw - 1                      # ceros coherentes inmediatamente anteriores
        while j >= 1 and r.bits[j] == 0 and abs(r.bit_period[j] - r.bit_period[j + 1]) * 4 <= r.bit_period[j + 1]:
            j -= 1
        kp = int(r.bit_tidx[j]) if j >= 0 else 0
        in_pre[kp:k0] = True
    med = lambda v: float(np.median(v)) if len(v) else nan

    # --- PW50 a partir del pulso medio de las transiciones aisladas (ceros) ---
    sel = in_pre & is0 if (in_pre & is0).sum() >= 3 else is0
    pw_raw = pw_cor = t_width = nan
    pw_valid = 0
    if sel.sum() >= 3:
        ks = np.flatnonzero(sel)
        u = np.linspace(-0.5 * cell, 0.5 * cell, 401)
        tx = np.arange(len(x)) / fs
        acc = np.zeros_like(u)
        nacc = 0
        wt = []
        for k in ks:
            v_loc = cell / (per[k] / r.tick_hz)
            tk = tt[k] / r.tick_hz
            s = np.interp(tk + u / v_loc, tx, x.astype(float)) - base
            if s[len(u) // 2] < 0:
                s = -s
            pk = np.max(s[len(u) // 2 - 40: len(u) // 2 + 41])
            if pk > 0:
                acc += s / pk
                nacc += 1
                wt.append(1.0 / v_loc)
        if nacc:
            pw_raw = _fwhm(u, acc / nacc)
            pw_cor = isi_correct(pw_raw / cell) * cell
            # valido si la correccion es invertible y el pulso no esta limitado por el LPF de 40 kHz
            t_width = pw_raw * float(np.median(wt)) if np.isfinite(pw_raw) else nan
            pw_valid = int(np.isfinite(pw_cor) and t_width > 30e-6)   # (y SNR > 20 dB, abajo)
    out["pw50_raw_um"] = pw_raw * 1e6
    out["pw50_um"] = pw_cor * 1e6
    out["pw50_valid"] = pw_valid

    # Amplitud de pico sobre la senal cruda promediada en +-10 % de la anchura temporal
    # del pulso (sesgo < 2 % para un pulso lorentziano); asi no depende del suavizado
    # de la instancia ganadora. Sin PW50 se queda la del decodificador.
    if nt and np.isfinite(t_width) and t_width > 0:
        hw = int(0.1 * t_width * fs)
        cs = np.concatenate([[0.0], np.cumsum(x.astype(float))])
        ci = np.clip(np.round(tt / pydec.TICKS_PER_SAMPLE).astype(np.int64), hw, len(x) - hw - 1)
        amp = np.abs((cs[ci + hw + 1] - cs[ci - hw]) / (2 * hw + 1) - base)
    pre0 = amp[in_pre & is0]
    out["amp_preamble_counts"] = med(pre0)
    out["amp_data_counts"] = med(amp[in_data])
    out["amp_data_zeros_counts"] = med(amp[in_data & is0])
    out["amp_data_ones_counts"] = med(amp[in_data & is1])
    z_all = amp[(in_data | in_pre) & is0] if has_frame else amp[is0]
    o_all = amp[in_data & is1] if has_frame else amp[is1]
    out["resolution"] = med(o_all) / med(z_all) if len(o_all) and len(z_all) and med(z_all) > 0 else nan

    if len(pre0) >= 3:
        amp_ref = med(pre0)
    elif is0.sum() >= 5:
        amp_ref = med(amp[is0])
    else:                                  # sin transiciones fiables: excursion robusta
        amp_ref = 0.5 * float(np.percentile(x, 99.9) - np.percentile(x, 0.1))
    out["amp_ref_counts"] = amp_ref
    out["amp_ref_mV_adc"] = amp_ref * vpc * 1e3
    out["snr_db"] = 20 * math.log10(amp_ref / noise) if noise and noise > 0 and amp_ref > 0 else nan
    if not (out["snr_db"] > 20.0):         # con poco SNR el pulso medio sale ensanchado
        pw_valid = 0
    out["pw50_valid"] = pw_valid

    # --- velocidad ---
    ge = np.asarray(sw.gate_edges, float).reshape(-1, 3)
    v_g = nan
    if len(ge):
        t1 = ge[(ge[:, 1] == 1) & (ge[:, 2] == 1), 0]
        t2 = ge[(ge[:, 1] == 2) & (ge[:, 2] == 1), 0]
        if len(t1) and len(t2) and t1[0] != t2[0]:
            v_g = GATE_SPACING_M / abs(t2[0] - t1[0])
    out["speed_gates_mm_s"] = float(v_g * 1e3)
    v_b = v_bmin = v_bmax = nan
    if has_frame and r.period_min > 0:
        nb = len(r.bits)
        lo, hi = (r.ss_bit - r.leading_zeros, r.end_bit)
        bp = np.asarray(r.bit_period, float)
        bp = (bp[::-1] if r.direction else bp)[lo:hi]
        v_b = cell / (np.median(bp) / r.tick_hz)
        v_bmin = cell / (r.period_max / r.tick_hz)
        v_bmax = cell / (r.period_min / r.tick_hz)
    elif (per > 0).sum() >= 8:
        v_b = cell / (np.median(per[per > 0]) / r.tick_hz)
    out["speed_bits_mm_s"] = float(v_b * 1e3)
    out["speed_bits_min_mm_s"] = v_bmin * 1e3
    out["speed_bits_max_mm_s"] = v_bmax * 1e3

    # --- amplitud normalizada por velocidad (uV s / m) ---
    norm = norm_iso = nan
    if gain and sel.sum() >= 3:
        v_loc = cell / (per[sel] / r.tick_hz)
        norm = med(amp[sel] * vpc / float(gain) * 1e6 / v_loc)
        if pw_valid:        # pulso aislado equivalente, suponiendo lorentzianas de paso = celda
            a_isi = math.pi * pw_cor / (2 * cell)
            norm_iso = norm * math.sinh(a_isi) / a_isi
    out["amp_norm_uV_s_per_m"] = norm
    out["amp_norm_iso_uV_s_per_m"] = norm_iso

    # --- recuperacion de transiciones frente a la cadena esperada ---
    out.update(exp_transitions=0, trans_matched=0, trans_missed=0, trans_extra=0,
               bit_errors=nan, exp_bits=0)
    l2 = l3 = False
    if expected:
        data_bits = synth.encode_chars(expected, fmt)
        m = match_transitions(tt, per, data_bits)
        out.update(exp_transitions=m["expected"], trans_matched=m["matched"],
                   trans_missed=m["missed"], trans_extra=m["extra"], exp_bits=len(data_bits))
        l2 = m["missed"] == 0 and m["extra"] == 0
        # errores de bit: alineando por el SS si existe; si no, mejor desfase en ambos sentidos
        nbx = len(data_bits)
        if r.bits is not None and len(r.bits) >= nbx:
            if has_frame:
                ob = r.oriented_bits()[r.ss_bit:r.ss_bit + nbx]
                out["bit_errors"] = int(np.sum(ob != data_bits[:len(ob)]) + (nbx - len(ob)))
            else:
                best = nbx
                for ob in (np.asarray(r.bits), np.asarray(r.bits)[::-1]):
                    win = np.lib.stride_tricks.sliding_window_view(ob, nbx)
                    best = min(best, int((win != data_bits[None, :]).sum(axis=1).min()))
                out["bit_errors"] = best
        l3 = r.status == pydec.OK and r.text == expected
    # --- verdad-terreno (solo sintetico) ---
    truth = (meta.get("synthetic") or {}).get("t_trans")
    if truth is not None:
        ms, ex, rms = match_truth(tt / r.tick_hz if nt else [], truth)
        out.update(truth_transitions=len(truth), truth_missed=ms, truth_extra=ex,
                   timing_rms_us=rms * 1e6)
    l1 = bool(np.isfinite(out["snr_db"]) and out["snr_db"] > l1_snr_db)
    out.update(L1=int(l1), L2=int(l2), L3=int(l3))
    return (out, r) if return_result else out


def main(argv=None):
    import argparse
    import json
    ap = argparse.ArgumentParser(description="Metricas de una pasada (.npz + .json)")
    ap.add_argument("swipe", nargs="+")
    ap.add_argument("--channel")
    ap.add_argument("--l1-snr", type=float, default=L1_SNR_DB)
    a = ap.parse_args(argv)
    for path in a.swipe:
        sw = swipefile.load(path)
        print(json.dumps(analyze(sw, a.channel, a.l1_snr), indent=1, default=float))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
