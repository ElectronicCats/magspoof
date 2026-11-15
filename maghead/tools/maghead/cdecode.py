"""Decodificador C (fw/common/f2f_decode.c) llamado desde Python via ctypes.

Es exactamente el codigo que va al firmware, compilado para el host. Se usa para
las simulaciones masivas (mapa SNR/PW50) y para la prueba de equivalencia con
decode.py. La biblioteca se compila bajo demanda con `make -C fw/common`.
"""
from __future__ import annotations

import ctypes as C
import os
import subprocess
import numpy as np

from . import decode as pydec

FW_COMMON = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "fw", "common"))
LIB_PATH = os.path.join(FW_COMMON, "build", "libf2f_host.so")
TEST_HOST = os.path.join(FW_COMMON, "build", "test_host")


class CCfg(C.Structure):
    _fields_ = [(n, C.c_int32) for n in (
        "thr_frac_q8", "noise_floor", "class_thr_q8", "pair_thr_q8", "period_alpha_shift",
        "period_bound_shift", "sync_count", "sync_tol_q8", "min_transitions", "min_lead_zeros")]


class CResult(C.Structure):
    _fields_ = [("status", C.c_int), ("fmt", C.c_uint8), ("direction", C.c_uint8),
                ("lrc_ok", C.c_uint8), ("instance", C.c_uint8), ("n_transitions", C.c_uint32),
                ("f2f_errors", C.c_uint32), ("n_bits", C.c_uint16), ("n_chars", C.c_uint16),
                ("n_parity_err", C.c_uint16), ("parity_pos", C.c_uint16 * pydec.MAX_PERR),
                ("leading_zeros", C.c_uint16), ("ss_bit", C.c_uint16), ("end_bit", C.c_uint16),
                ("lrc_value", C.c_uint8), ("period_min", C.c_uint32), ("period_max", C.c_uint32),
                ("text", C.c_char * (pydec.MAX_CHARS + 1))]


_lib = None


def build(force: bool = False) -> None:
    """Compila test_host y la biblioteca compartida (necesita gcc y make)."""
    args = ["make", "-C", FW_COMMON] + (["-B"] if force else [])
    subprocess.run(args, check=True, capture_output=True)


def lib():
    global _lib
    if _lib is None:
        build()
        _lib = C.CDLL(LIB_PATH)
        _lib.f2f_host_sizeof_result.restype = C.c_size_t
        _lib.f2f_host_sizeof_cfg.restype = C.c_size_t
        if _lib.f2f_host_sizeof_result() != C.sizeof(CResult) or \
                _lib.f2f_host_sizeof_cfg() != C.sizeof(CCfg):
            raise RuntimeError("las estructuras ctypes no coinciden con f2f_decode.h")
    return _lib


def _cfg(cfg):
    cfg = cfg or pydec.Config()
    return CCfg(**{n: getattr(cfg, n) for n, _ in CCfg._fields_})


def _to_result(cr: CResult) -> pydec.Result:
    return pydec.Result(
        status=cr.status, fmt=cr.fmt, direction=cr.direction, lrc_ok=bool(cr.lrc_ok),
        instance=cr.instance, n_transitions=cr.n_transitions, f2f_errors=cr.f2f_errors,
        n_bits=cr.n_bits, n_chars=cr.n_chars, n_parity_err=cr.n_parity_err,
        parity_pos=list(cr.parity_pos[:min(cr.n_parity_err, pydec.MAX_PERR)]),
        leading_zeros=cr.leading_zeros, ss_bit=cr.ss_bit, end_bit=cr.end_bit,
        lrc_value=cr.lrc_value, period_min=cr.period_min, period_max=cr.period_max,
        text=cr.text.decode("latin-1"))


def decode(x, fs: float, fmt: int = pydec.FMT_AUTO, cfg=None, decims=pydec.DEFAULT_DECIMS,
           want_log: bool = True) -> pydec.Result:
    """Igual que decode.decode() pero ejecutando el modulo C."""
    L = lib()
    xa = np.ascontiguousarray(np.asarray(x).astype(np.uint16))
    n = len(xa)
    cr = CResult()
    cc = _cfg(cfg)
    dec = (C.c_uint32 * 4)(*decims)
    cap = n + 16 if want_log else 0
    tl = np.zeros(max(cap, 1), np.int64)
    vl = np.zeros(max(cap, 1), np.int32)
    pl = np.zeros(max(cap, 1), np.uint32)
    bits = np.zeros(pydec.MAX_BITS, np.uint8)
    bper = np.zeros(pydec.MAX_BITS, np.uint32)
    nt = C.c_uint32(0)
    nb = C.c_uint32(0)
    P = lambda a, t: a.ctypes.data_as(C.POINTER(t))
    rc = L.f2f_host_run(P(xa, C.c_uint16), C.c_size_t(n), C.c_int(fmt), C.byref(cc), dec,
                        C.byref(cr), P(tl, C.c_int64), P(vl, C.c_int32), P(pl, C.c_uint32),
                        C.c_uint32(cap), C.byref(nt), P(bits, C.c_uint8), P(bper, C.c_uint32),
                        C.byref(nb))
    if rc < 0:
        raise MemoryError("f2f_host_run")
    r = _to_result(cr)
    r.tick_hz = float(fs) * pydec.TICKS_PER_SAMPLE
    r.decim = decims[r.instance]
    r.trans_ticks = tl[:nt.value].copy()
    r.trans_value = vl[:nt.value].astype(np.int64)
    r.trans_period = pl[:nt.value].astype(np.int64)
    r.bits = bits[:nb.value].copy()
    r.bit_period = bper[:nb.value].astype(np.int64)
    return r


def decode_edges(times_ticks, tick_hz: float, fmt: int = pydec.FMT_AUTO, cfg=None) -> pydec.Result:
    L = lib()
    ta = np.ascontiguousarray(np.asarray(times_ticks, dtype=np.int64))
    cr = CResult()
    cc = _cfg(cfg)
    bits = np.zeros(pydec.MAX_BITS, np.uint8)
    nb = C.c_uint32(0)
    L.f2f_host_run_edges(ta.ctypes.data_as(C.POINTER(C.c_int64)), C.c_size_t(len(ta)), C.c_int(fmt),
                         C.byref(cc), C.byref(cr), bits.ctypes.data_as(C.POINTER(C.c_uint8)),
                         C.byref(nb))
    r = _to_result(cr)
    r.tick_hz = float(tick_hz)
    r.trans_ticks = ta
    r.bits = bits[:nb.value].copy()
    return r
