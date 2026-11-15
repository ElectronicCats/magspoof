"""Pruebas del generador sintetico."""
import numpy as np
import pytest
from scipy import signal as sps

from maghead import synth
from conftest import T1, T2


def test_encode_sentinels_and_lrc():
    b1 = synth.encode_chars(T1, 1)
    b2 = synth.encode_chars(T2, 2)
    assert b1[:7].tolist() == [1, 0, 1, 0, 0, 0, 1]          # '%' = 0x05, paridad impar
    assert b2[:5].tolist() == [1, 1, 0, 1, 0]                # ';' = 0x0B
    assert len(b1) == 7 * (len(T1) + 1) and len(b2) == 5 * (len(T2) + 1)
    for b, nb in ((b1, 7), (b2, 5)):
        m = b.reshape(-1, nb)
        assert np.all(m.sum(axis=1) % 2 == 1)                # paridad impar por caracter
        assert np.all(m[:, :nb - 1].sum(axis=0) % 2 == 0)    # LRC: paridad par por columna


def test_encode_rejects_bad_alphabet():
    with pytest.raises(ValueError):
        synth.encode_chars(";12X4?", 2)                      # 'X' no existe en pista 2
    with pytest.raises(ValueError):
        synth.encode_chars("1234", 2)                        # sin centinelas


def test_transition_count_and_truth():
    sw = synth.synthesize(text=T2, speed=0.5, gates=False)
    n_cells = len(sw.bits_card)
    assert len(sw.t_trans) == n_cells + 1 + int(sw.bits_card.sum())
    assert np.all(np.diff(sw.t_trans) > 0)
    assert abs(sw.cell_m - 25.4e-3 / 75) < 1e-12
    assert sw.lead_zeros == 20
    sw1 = synth.synthesize(text=T1, speed=0.5, gates=False)
    assert abs(sw1.cell_m - 25.4e-3 / 210) < 1e-12 and sw1.lead_zeros == 57
    # intervalos de la verdad: celda / v o media celda / v
    iv = np.diff(sw.t_trans) * 0.5 / sw.cell_m
    assert np.all((np.abs(iv - 1) < 0.01) | (np.abs(iv - 0.5) < 0.01))


def test_lorentzian_pw50():
    xg = np.arange(-2e-3, 2e-3, 0.5e-6)
    s = synth.lorentz_train(xg, np.array([0.0]), 50e-6)
    above = xg[s >= 0.5 * s.max()]
    assert abs((above[-1] - above[0]) - 50e-6) < 1.5e-6
    assert abs(s.max() - 1.0) < 1e-3


def test_amplitude_proportional_to_speed():
    a = synth.synthesize(text=T2, speed=0.2, gain=50, gates=False, pw50_um=30)
    b = synth.synthesize(text=T2, speed=0.4, gain=50, gates=False, pw50_um=30)
    pa = np.max(np.abs(a.adc.astype(int) - 2048))
    pb = np.max(np.abs(b.adc.astype(int) - 2048))
    assert abs(pb / pa - 2.0) < 0.05
    # pico aislado esperado: sens * v * ganancia
    assert abs(pa - 10000e-6 * 0.2 * 50 / (3.3 / 4096)) / pa < 0.05


def test_noise_rms_in_band_and_snr():
    sw = synth.synthesize(text=T2, speed=0.5, snr_db=20, gates=False, quiet_ms=200)
    q = sw.adc[: int(0.15 * sw.fs)].astype(float)
    assert abs(np.std(q) / sw.noise_rms_counts - 1) < 0.05
    assert abs(sw.iso_peak_counts / sw.noise_rms_counts - 10.0) < 1e-6


def test_afe_bandpass_corners():
    fs = 250e3
    n = 1 << 18
    imp = np.zeros(n)
    imp[0] = 1
    h = np.abs(np.fft.rfft(synth.afe_filter(imp, fs)))
    f = np.fft.rfftfreq(n, 1 / fs)
    g = lambda fx: 20 * np.log10(h[np.argmin(np.abs(f - fx))])
    assert abs(g(1000)) < 0.1
    assert abs(g(16) + 3.0) < 0.3
    assert abs(g(40e3) + 3.0) < 0.3
    assert g(160e3 * 0.5) < -10                               # 2 polos: -12 dB/octava


def test_velocity_profiles_and_gates():
    sw = synth.synthesize(text=T2, speed=0.4, profile="const")
    t1, t2 = sw.gate_edges[0, 0], sw.gate_edges[1, 0]
    assert abs(0.020 / (t2 - t1) - 0.4) < 1e-3
    assert sw.gate1.max() == 1 and sw.gate1[0] == 0
    acc = synth.synthesize(text=T2, speed=0.2, profile="accel", v_end=0.8, gates=False)
    assert acc.v_trans[0] < acc.v_trans[-1] and acc.v_trans.min() >= 0.2 and acc.v_trans.max() <= 0.8
    hand = synth.synthesize(text=T2, speed=0.3, profile="hand", gates=False, seed=4)
    dev = hand.v_trans / 0.3 - 1
    assert np.max(np.abs(dev)) <= 0.3 + 1e-9 and np.max(np.abs(dev)) > 0.1
    rev = synth.synthesize(text=T2, speed=0.3, reverse=True, gates=False)
    fwd = synth.synthesize(text=T2, speed=0.3, reverse=False, gates=False)
    assert len(rev.t_trans) == len(fwd.t_trans)
    # sentido inverso: la secuencia de intervalos sale invertida
    assert np.allclose(np.diff(rev.t_trans), np.diff(fwd.t_trans)[::-1], rtol=1e-6, atol=1e-9)


def test_adc_range_and_comparator():
    sw = synth.synthesize(text=T2, speed=0.5, snr_db=30, gates=False)
    assert sw.adc.dtype == np.int16 and sw.adc.min() >= 0 and sw.adc.max() <= 4095
    assert abs(np.median(sw.adc) - 2048) < 3
    c = synth.comparator(sw.adc, 100)
    edges = np.flatnonzero(np.diff(c.astype(int)) != 0)
    assert abs(len(edges) - len(sw.t_trans)) <= 2
