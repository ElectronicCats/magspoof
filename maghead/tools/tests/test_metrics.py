"""Metricas por pasada, veredictos L1/L2/L3 e informe agregado."""
import csv
import math
import numpy as np
import pytest

from maghead import synth, metrics, report, swipefile, decode
from conftest import T1, T2


def analyze(**kw):
    s = synth.synthesize(**kw)
    return metrics.analyze(synth.to_swipe(s)), s


@pytest.mark.parametrize("text", [T1, T2], ids=["pista1", "pista2"])
@pytest.mark.parametrize("reverse", [False, True], ids=["fwd", "rev"])
def test_clean_swipe_all_levels(text, reverse):
    m, s = analyze(text=text, speed=0.3, snr_db=30, pw50_um=40, reverse=reverse, seed=3)
    assert (m["L1"], m["L2"], m["L3"]) == (1, 1, 1)
    assert m["status"] == "OK" and m["decoded_text"] == text
    assert m["direction"] == ("REV" if reverse else "FWD")
    assert m["trans_missed"] == 0 and m["trans_extra"] == 0 and m["bit_errors"] == 0
    assert m["exp_transitions"] == len(s.data_bits) + 1 + int(s.data_bits.sum())
    assert m["truth_missed"] == 0 and m["truth_extra"] <= 2
    assert abs(m["snr_db"] - 30) < 2.0
    assert abs(m["noise_rms_counts"] / s.noise_rms_counts - 1) < 0.1
    assert abs(m["speed_gates_mm_s"] - 300) < 1 and abs(m["speed_bits_mm_s"] - 300) < 6
    assert m["speed_bits_min_mm_s"] <= m["speed_bits_mm_s"] <= m["speed_bits_max_mm_s"]
    # amplitud normalizada: sensibilidad sintetica 10000 uV s/m (menos ISI de los ceros)
    assert 0.85 < m["amp_norm_uV_s_per_m"] / 10000 < 1.03
    assert abs(m["amp_norm_iso_uV_s_per_m"] / 10000 - 1) < 0.05
    assert m["pw50_valid"] == 1 and abs(m["pw50_um"] - 40) < 4


@pytest.mark.parametrize("pw", [30, 60, 100, 150])
def test_pw50_estimate_track2(pw):
    m, _ = analyze(text=T2, speed=0.2, snr_db=36, pw50_um=pw, seed=1)
    assert m["pw50_valid"] == 1
    assert abs(m["pw50_um"] / pw - 1) < 0.08
    assert m["L3"] == 1


def test_pw50_flagged_invalid_when_isi_too_strong():
    m, _ = analyze(text=T1, speed=0.3, snr_db=36, pw50_um=150, seed=1)   # PW50 > celda (121 um)
    assert m["pw50_valid"] == 0


def test_resolution_drops_with_pw50():
    r = [analyze(text=T1, speed=0.3, snr_db=40, pw50_um=pw, seed=1)[0]["resolution"] for pw in (20, 60, 100)]
    assert r[0] > 0.9 and r[0] > r[1] > r[2] and r[2] < 0.6
    # modelo: tren alterno de lorentzianas, amplitud ~ a/sinh(a), a = pi*PW50/(2*paso)
    f = lambda pw, b: (math.pi * pw / (2 * b)) / math.sinh(math.pi * pw / (2 * b))
    assert abs(r[1] - f(60, 60.5) / f(60, 121)) < 0.1


def test_speed_from_gates_vs_bits_with_acceleration():
    m, s = analyze(text=T2, speed=0.2, v_end=0.8, profile="accel", snr_db=30, seed=2)
    t1, t2 = s.gate_edges[0, 0], s.gate_edges[1, 0]
    assert abs(m["speed_gates_mm_s"] - 20.0 / (t2 - t1)) < 0.5
    assert m["speed_bits_max_mm_s"] / m["speed_bits_min_mm_s"] > 1.5      # la aceleracion se ve
    assert m["speed_bits_mm_s"] > m["speed_gates_mm_s"]                   # las barreras van antes


def test_noise_only_fails_every_level():
    rng = np.random.default_rng(1)
    x = np.clip(np.round(2048 + 20 * rng.standard_normal(150000)), 0, 4095).astype(np.int16)
    m0 = swipefile.new_meta()
    m0.update(expected_tracks={"2": T2}, track_under_test=2, afe_gain_a=100.0)
    sw = swipefile.Swipe(chA=x, chB=np.zeros(0, np.int16), dig=np.zeros(0, np.uint8), fs=250e3,
                         gate_edges=np.zeros((0, 3)), meta=m0)
    m = metrics.analyze(sw)
    assert (m["L1"], m["L2"], m["L3"]) == (0, 0, 0)
    assert m["trans_missed"] > 0 and math.isnan(m["speed_gates_mm_s"])


def test_levels_are_separate_signal_but_no_decode():
    """PW50 enorme en pista 1: hay senal de sobra (L1) pero no se recuperan transiciones ni datos."""
    m, _ = analyze(text=T1, speed=0.3, snr_db=40, pw50_um=260, seed=1)
    assert m["L1"] == 1 and m["L2"] == 0 and m["L3"] == 0
    assert m["trans_missed"] > 0


def test_levels_are_separate_transitions_but_wrong_string():
    """Tarjeta bien leida pero la cadena esperada de los metadatos es otra: L1 y L3 difieren;
    con un bit distinto, la cuenta de transiciones difiere exactamente en una."""
    s = synth.synthesize(text=T2, speed=0.3, snr_db=30, flip_data_bits=(5 * 7 + 2,), seed=3)
    m = metrics.analyze(synth.to_swipe(s))
    assert m["L1"] == 1 and m["L3"] == 0 and m["status"] == "PARITY_ERR"
    assert m["bit_errors"] == 1 and m["parity_pos"] == "7"
    assert m["trans_missed"] + m["trans_extra"] == 1 and m["L2"] == 0


def test_match_transitions_counts_missing_and_extra():
    bits = synth.encode_chars(T2, 2)
    full = np.concatenate([np.zeros(20, np.uint8), bits, np.zeros(20, np.uint8)])
    x = np.round(synth.transitions_from_bits(full, 1000.0)).astype(np.int64)
    per = np.full(len(x), 1000)
    e = len(bits) + 1 + int(bits.sum())
    m = metrics.match_transitions(x, per, bits)
    assert (m["expected"], m["matched"], m["missed"], m["extra"]) == (e, e, 0, 0) and m["direction"] == 0
    m = metrics.match_transitions(x[-1] - x[::-1], per, bits)             # pasada invertida
    assert (m["missed"], m["extra"], m["direction"]) == (0, 0, 1)
    k = 20 + 60                                                            # quitar una transicion de datos
    m = metrics.match_transitions(np.delete(x, k), per[1:], bits)
    assert m["missed"] == 1 and m["extra"] == 0
    xe = np.sort(np.concatenate([x, [x[k] + 250]]))                        # anadir una espuria
    m = metrics.match_transitions(xe, np.full(len(xe), 1000), bits)
    assert m["missed"] + m["extra"] >= 1


def test_wilson_interval():
    lo, hi = metrics.wilson(0, 10)
    assert lo == 0 and abs(hi - 0.2775) < 1e-3
    lo, hi = metrics.wilson(10, 20)
    assert abs(lo - 0.2993) < 1e-3 and abs(hi - 0.7007) < 1e-3
    lo, hi = metrics.wilson(20, 20)
    assert abs(lo - 0.8389) < 1e-3 and hi == 1.0
    assert all(math.isnan(v) for v in metrics.wilson(0, 0))


def test_isi_correction_table():
    assert abs(metrics.isi_correct(0.05) - 0.05) < 0.002                  # pulsos aislados
    assert metrics.isi_correct(0.3) > 0.3
    assert math.isnan(metrics.isi_correct(0.65))


def test_report_folder(tmp_path):
    n = 0
    for variant, pw in (("V1", 40), ("V5", 200)):
        for speed in (0.15, 0.6):
            for k in range(3):
                s = synth.synthesize(text=T1, speed=speed, snr_db=28, pw50_um=pw, profile="hand",
                                     reverse=bool(k & 1), seed=n)
                sw = synth.to_swipe(s, meta={"head_variant": variant, "spacing_shim_um": 0.0,
                                             "speed_source": "hand", "operator": "pytest"})
                swipefile.save(sw, str(tmp_path / "data" / f"{variant}_{n:03d}"))
                n += 1
    out = tmp_path / "rep"
    assert report.main([str(tmp_path / "data"), "--out", str(out)]) == 0
    rows = list(csv.DictReader(open(out / "swipes.csv")))
    assert len(rows) == 12 and {"L1", "L2", "L3", "snr_db", "amp_norm_uV_s_per_m", "file"} <= set(rows[0])
    summ = list(csv.DictReader(open(out / "summary.csv")))
    assert len(summ) == 4 and all(int(r["N"]) == 3 for r in summ)
    assert {r["head_variant"] for r in summ} == {"V1", "V5"}
    assert {r["speed_bin"] for r in summ} == {"0.1-0.2 m/s", "0.4-0.8 m/s"}
    v1 = [r for r in summ if r["head_variant"] == "V1"]
    assert all(float(r["L3_pct"]) == 100.0 for r in v1)
    assert all(abs(float(r["L3_lo"]) - 43.85) < 0.1 and float(r["L3_hi"]) == 100.0 for r in v1)  # Wilson 3/3
    v5 = [r for r in summ if r["head_variant"] == "V5"]
    assert all(float(r["L1_pct"]) == 100.0 for r in v5)
    assert all(float(r["L3_pct"]) < 100.0 for r in v5)                    # PW50 200 um en pista 1
    md = (out / "summary.md").read_text()
    assert "% L3" in md and "V5" in md and "IC95" in md
    assert report.speed_bin(0.05) == "0-0.1 m/s" and report.speed_bin(2.0) == ">=1.6 m/s"
