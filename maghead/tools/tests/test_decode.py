"""Ida y vuelta sintetizador -> decodificador de referencia (Python)."""
import numpy as np
import pytest

from maghead import synth, decode
from conftest import T1, T2

SPEEDS = [0.05, 0.1, 0.25, 0.5, 1.0, 1.5]


def check_ok(r, text, reverse):
    assert r.status == decode.OK, (r.status_name, r.text)
    assert r.text == text
    assert r.direction == (decode.DIR_REV if reverse else decode.DIR_FWD)
    assert r.lrc_ok and r.n_parity_err == 0


@pytest.mark.parametrize("text", [T1, T2], ids=["pista1", "pista2"])
@pytest.mark.parametrize("reverse", [False, True], ids=["fwd", "rev"])
@pytest.mark.parametrize("speed", SPEEDS)
def test_roundtrip_speeds(text, reverse, speed):
    sw = synth.synthesize(text=text, speed=speed, reverse=reverse, snr_db=30, pw50_um=40,
                          gates=False, seed=11)
    r = decode.decode(sw.adc, sw.fs)                          # formato automatico
    check_ok(r, text, reverse)
    assert r.fmt == sw.fmt
    if not reverse:
        # +-2: un pico de ruido justo antes de la primera transicion puede contar como cero
        assert abs(r.leading_zeros - sw.lead_zeros) <= 2
    else:
        assert 4 <= r.leading_zeros <= sw.lead_zeros + 4      # la cabecera es otra zona de ceros
    # periodo de bit medido: celda / v dentro del 6 %
    p_nom = sw.cell_m / speed * r.tick_hz
    assert 0.94 * p_nom < r.period_min <= r.period_max < 1.06 * p_nom


@pytest.mark.parametrize("text", [T1, T2], ids=["pista1", "pista2"])
@pytest.mark.parametrize("reverse", [False, True], ids=["fwd", "rev"])
@pytest.mark.parametrize("v0,v1", [(0.1, 0.4), (0.2, 0.8), (1.2, 0.3), (0.5, 1.5)])
def test_roundtrip_acceleration(text, reverse, v0, v1):
    sw = synth.synthesize(text=text, speed=v0, v_end=v1, profile="accel", reverse=reverse,
                          snr_db=30, gates=False, seed=5)
    r = decode.decode(sw.adc, sw.fs)
    check_ok(r, text, reverse)
    # el seguidor de periodo debe haber seguido el cambio de velocidad
    # (comparado con la velocidad real sobre la zona ceros de cabecera + datos + LRC)
    nfr = sw.lead_zeros + len(sw.data_bits)
    ntr = nfr + 1 + int(sw.data_bits.sum())
    v = sw.v_trans[-ntr:] if reverse else sw.v_trans[:ntr]
    ratio = r.period_max / r.period_min
    assert abs(ratio / (v.max() / v.min()) - 1) < 0.20      # extremos por bit: incluyen jitter


@pytest.mark.parametrize("text", [T1, T2], ids=["pista1", "pista2"])
@pytest.mark.parametrize("seed", range(6))
def test_roundtrip_hand_variation(text, seed):
    sw = synth.synthesize(text=text, speed=[0.15, 0.4, 0.9][seed % 3], profile="hand",
                          hand_depth=0.30, reverse=bool(seed & 1), snr_db=30, gates=False, seed=seed)
    check_ok(decode.decode(sw.adc, sw.fs), text, bool(seed & 1))


@pytest.mark.parametrize("text", [T1, T2], ids=["pista1", "pista2"])
@pytest.mark.parametrize("snr", [40, 30, 24, 20])
def test_snr_sweep_decodes(text, snr):
    for seed in range(4):
        sw = synth.synthesize(text=text, speed=0.3, snr_db=snr, pw50_um=40, profile="hand",
                              gates=False, seed=100 + seed)
        check_ok(decode.decode(sw.adc, sw.fs), text, False)


@pytest.mark.parametrize("text", [T1, T2], ids=["pista1", "pista2"])
@pytest.mark.parametrize("snr", [6, 0, -10])
def test_low_snr_never_false_ok(text, snr):
    """Con SNR muy baja puede fallar, pero nunca debe dar OK con una cadena equivocada."""
    for seed in range(4):
        sw = synth.synthesize(text=text, speed=0.3, snr_db=snr, gates=False, seed=200 + seed)
        r = decode.decode(sw.adc, sw.fs)
        assert not (r.status == decode.OK and r.text != text)


def test_noise_only_is_not_ok():
    rng = np.random.default_rng(0)
    for sigma in (2, 30, 200):
        x = np.clip(np.round(2048 + sigma * rng.standard_normal(200000)), 0, 4095).astype(np.int16)
        assert decode.decode(x, 250e3).status != decode.OK


def test_flat_signal_is_no_signal():
    r = decode.decode(np.full(50000, 2048, np.int16), 250e3)
    assert r.status == decode.NO_SIGNAL and r.n_transitions == 0


def test_hum_and_baseline_wander():
    for text in (T1, T2):
        sw = synth.synthesize(text=text, speed=0.3, snr_db=30, hum_uV=300, wander_mV=40,
                              gates=False, seed=3)       # zumbido = 10 % del pico aislado
        check_ok(decode.decode(sw.adc, sw.fs), text, False)


def test_single_channel_500k_rate():
    sw = synth.synthesize(text=T1, speed=1.5, fs=500e3, snr_db=30, gates=False)
    check_ok(decode.decode(sw.adc, sw.fs), T1, False)


# ---------------------------------------------------------------- paridad / LRC

@pytest.mark.parametrize("text,fmt,nb", [(T1, 1, 7), (T2, 2, 5)], ids=["pista1", "pista2"])
@pytest.mark.parametrize("reverse", [False, True], ids=["fwd", "rev"])
def test_one_corrupt_bit_reports_parity_position(text, fmt, nb, reverse):
    ch = 7                                                   # caracter corrupto (0 = SS)
    sw = synth.synthesize(text=text, speed=0.4, snr_db=35, reverse=reverse, gates=False,
                          flip_data_bits=(ch * nb + 2,))
    r = decode.decode(sw.adc, sw.fs, fmt)
    assert r.status == decode.PARITY_ERR
    assert r.n_parity_err == 1 and r.parity_pos == [ch]
    assert not r.lrc_ok                                      # un solo bit tambien rompe el LRC
    assert r.direction == int(reverse)
    assert len(r.text) == len(text) and r.text != text
    assert [i for i, (a, b) in enumerate(zip(r.text, text)) if a != b] == [ch]


@pytest.mark.parametrize("text,fmt,nb", [(T1, 1, 7), (T2, 2, 5)], ids=["pista1", "pista2"])
def test_two_bits_same_char_reports_lrc_error(text, fmt, nb):
    sw = synth.synthesize(text=text, speed=0.4, snr_db=35, gates=False,
                          flip_data_bits=(9 * nb + 0, 9 * nb + 1))
    r = decode.decode(sw.adc, sw.fs, fmt)
    assert r.status == decode.LRC_ERR and r.n_parity_err == 0 and not r.lrc_ok


def test_lrc_parity_bit_corrupt():
    n = 5 * len(T2)
    sw = synth.synthesize(text=T2, speed=0.4, snr_db=35, gates=False, flip_data_bits=(n + 4,))
    r = decode.decode(sw.adc, sw.fs)
    assert r.status == decode.LRC_ERR and r.text == T2


def test_decode_bits_layer_statuses():
    bits = np.concatenate([np.zeros(20, np.uint8), synth.encode_chars(T2, 2), np.zeros(20, np.uint8)])
    r = decode.decode_bits(bits)
    assert r.status == decode.OK and r.text == T2 and r.leading_zeros == 20 and r.fmt == 2
    r = decode.decode_bits(bits[::-1])
    assert r.status == decode.OK and r.direction == decode.DIR_REV and r.text == T2
    assert decode.decode_bits(np.zeros(300, np.uint8)).status == decode.NO_START
    r = decode.decode_bits(bits[:20 + 5 * 12], fmt=2)
    assert r.status == decode.NO_END and r.n_chars == 12
    b = bits.copy()
    b[20 + 5 * 3 + 4] ^= 1                                   # bit de paridad del caracter 3
    r = decode.decode_bits(b, fmt=2)
    assert r.status == decode.PARITY_ERR and r.parity_pos == [3] and r.lrc_ok
    b[20 + 5 * 30 + 0] ^= 1
    r = decode.decode_bits(b, fmt=2)
    assert r.status == decode.PARITY_ERR and r.n_parity_err == 2 and r.parity_pos == [3, 30]


def test_transitions_without_start_sentinel():
    """Tren regular de transiciones (solo ceros): hay senal pero no centinela."""
    t = (np.arange(200) * 1000).tolist()
    r = decode.decode_edges(t, 1e6)
    assert r.status == decode.NO_START and r.n_transitions == 200 and r.n_bits >= 190


# ---------------------------------------------------------------- otras rutas

@pytest.mark.parametrize("text", [T1, T2], ids=["pista1", "pista2"])
@pytest.mark.parametrize("reverse", [False, True], ids=["fwd", "rev"])
def test_comparator_edge_path(text, reverse):
    sw = synth.synthesize(text=text, speed=0.3, profile="hand", reverse=reverse, snr_db=34,
                          pw50_um=40, gates=False, seed=8)
    comp = synth.comparator(sw.adc, 150)
    edges = np.flatnonzero(np.diff(comp.astype(int)) != 0) + 1
    r = decode.decode_edges(edges, sw.fs)                    # tick = 1 muestra
    check_ok(r, text, reverse)


def test_transition_times_match_truth():
    sw = synth.synthesize(text=T2, speed=0.5, snr_db=40, pw50_um=40, gates=False)
    r = decode.decode(sw.adc, sw.fs)
    t = r.transition_times
    t = t[(t > sw.t_trans[0] - 1e-4) & (t < sw.t_trans[-1] + 1e-4)]
    assert len(t) == len(sw.t_trans)
    assert np.sqrt(np.mean((t - sw.t_trans) ** 2)) < 2.5 / sw.fs   # < 2.5 muestras RMS


@pytest.mark.parametrize("text", [T1, T2], ids=["pista1", "pista2"])
@pytest.mark.parametrize("reverse", [False, True], ids=["fwd", "rev"])
def test_noncausal_variant(text, reverse):
    sw = synth.synthesize(text=text, speed=0.4, profile="hand", reverse=reverse, snr_db=30,
                          gates=False, seed=2)
    check_ok(decode.decode_noncausal(sw.adc, sw.fs), text, reverse)
