"""El decodificador C (fw/common) compilado en host debe dar EXACTAMENTE el mismo resultado
que la referencia Python sobre los mismos vectores sinteticos."""
import os
import shutil
import subprocess
import numpy as np
import pytest

from maghead import synth, decode, cdecode
from conftest import T1, T2

pytestmark = pytest.mark.skipif(shutil.which("gcc") is None or shutil.which("make") is None,
                                reason="hace falta gcc y make")


@pytest.fixture(scope="module", autouse=True)
def built():
    cdecode.build(force=True)
    assert os.path.exists(cdecode.TEST_HOST) and os.path.exists(cdecode.LIB_PATH)


def run_host(*args):
    p = subprocess.run([cdecode.TEST_HOST, *map(str, args)], capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr
    return p.stdout


def parse(out):
    kv, trans = {}, []
    for ln in out.splitlines():
        if ln.startswith("T "):
            trans.append([int(v) for v in ln.split()[1:]])
        elif "=" in ln:
            k, v = ln.split("=", 1)
            kv[k] = v
    return kv, np.array(trans, dtype=np.int64).reshape(-1, 3)


def assert_same(kv, trans, r):
    assert int(kv["status"]) == r.status and kv["status_name"] == r.status_name
    assert kv["text"] == r.text
    for k in ("fmt", "direction", "instance", "n_transitions", "f2f_errors", "n_bits", "n_chars",
              "n_parity_err", "leading_zeros", "ss_bit", "end_bit", "lrc_value", "period_min",
              "period_max"):
        assert int(kv[k]) == int(getattr(r, k)), k
    assert int(kv["lrc_ok"]) == int(r.lrc_ok)
    assert [int(v) for v in kv["parity_pos"].split(",") if v] == list(r.parity_pos)
    assert kv["bits"] == "".join(str(int(b)) for b in r.bits)
    if "bit_period" in kv:
        assert [int(v) for v in kv["bit_period"].split(",") if v] == r.bit_period.tolist()
    if trans is not None:
        assert np.array_equal(trans[:, 0], r.trans_ticks)
        assert np.array_equal(trans[:, 1], r.trans_value)
        assert np.array_equal(trans[:, 2], r.trans_period)


def test_c_selftest():
    out = run_host("selftest")
    assert "0 fallos" in out and "FALLO" not in out


def test_c_selftest_sanitizers():
    """Mismo selftest con AddressSanitizer + UBSan (si el compilador los tiene)."""
    p = subprocess.run(["make", "-C", cdecode.FW_COMMON, "asan"], capture_output=True, text=True)
    if p.returncode != 0 and "selftest" not in p.stdout:
        pytest.skip("sanitizers no disponibles")
    assert p.returncode == 0 and "0 fallos" in p.stdout, p.stdout + p.stderr


def _cases():
    rng = np.random.default_rng(2024)
    out = []
    for i in range(36):
        speed = float(10 ** rng.uniform(np.log10(0.05), np.log10(1.5)))
        out.append(dict(
            text=(T1, T2)[i % 2], speed=speed, reverse=bool(i & 2),
            profile=("const", "hand", "accel")[i % 3], v_end=speed * float(rng.uniform(0.4, 2.5)),
            snr_db=float(rng.uniform(4, 40)), pw50_um=float(rng.uniform(20, 200)),
            hum_uV=float(rng.choice([0, 200])), gates=False, seed=i))
    # casos dirigidos: bit corrupto (paridad), dos bits (LRC), sin senal util
    out.append(dict(text=T2, speed=0.4, snr_db=35, gates=False, flip_data_bits=(37,)))
    out.append(dict(text=T1, speed=0.4, snr_db=35, gates=False, flip_data_bits=(63, 64), reverse=True))
    out.append(dict(text=T2, speed=0.4, snr_db=-20, gates=False))
    return out


@pytest.mark.parametrize("i,kw", list(enumerate(_cases())))
def test_c_matches_python_on_synthetic_vectors(i, kw, tmp_path):
    sw = synth.synthesize(**kw)
    vec = tmp_path / "v.i16"
    sw.adc.astype("<i2").tofile(vec)                         # volcado del vector
    for fmt in (0, sw.fmt):
        r = decode.decode(sw.adc, sw.fs, fmt)
        kv, trans = parse(run_host("decode", vec, fmt))
        assert_same(kv, trans, r)
        rc = cdecode.decode(sw.adc, sw.fs, fmt)              # mismo C via ctypes
        assert (rc.status, rc.text, rc.instance) == (r.status, r.text, r.instance)
        assert np.array_equal(rc.trans_ticks, r.trans_ticks) and np.array_equal(rc.bits, r.bits)
        assert np.array_equal(rc.bit_tidx, r.bit_tidx)


def test_c_decodes_the_reference_strings(tmp_path):
    """Comprobacion directa (no solo de igualdad): el C decodifica las dos cadenas."""
    for text in (T1, T2):
        for rev in (False, True):
            sw = synth.synthesize(text=text, speed=0.3, reverse=rev, snr_db=30, profile="hand",
                                  gates=False, seed=1)
            vec = tmp_path / "v.i16"
            sw.adc.astype("<i2").tofile(vec)
            kv, _ = parse(run_host("decode", vec, 0))
            assert kv["status_name"] == "OK" and kv["text"] == text and int(kv["direction"]) == int(rev)


@pytest.mark.parametrize("text", [T1, T2], ids=["pista1", "pista2"])
def test_c_edge_path_matches_python(text, tmp_path):
    sw = synth.synthesize(text=text, speed=0.3, profile="hand", snr_db=34, gates=False, seed=8)
    comp = synth.comparator(sw.adc, 150)
    edges = (np.flatnonzero(np.diff(comp.astype(int)) != 0) + 1).astype("<i8")
    f = tmp_path / "e.i64"
    edges.tofile(f)
    r = decode.decode_edges(edges, sw.fs)
    kv, _ = parse(run_host("edges", f, 0))
    assert_same(kv, None, r)
    assert kv["status_name"] == "OK" and kv["text"] == text
    assert cdecode.decode_edges(edges, sw.fs).text == text
