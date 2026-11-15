"""Protocolo de tramas, captura, importadores y formato de archivo."""
import json
import shutil
import struct
import subprocess
import numpy as np
import pytest

from maghead import synth, decode, capture, swipefile, cdecode
from conftest import T1, T2

HAVE_CC = shutil.which("gcc") is not None and shutil.which("make") is not None


def make_frames(n=5, nw=64, fs_total=500000, drop=None):
    """Tramas de muestras A/B construidas en Python: A = rampa, B = 2048."""
    frames, ref = [], []
    for k in range(n):
        if k == drop:
            continue
        a = (np.arange(nw // 2) + 100 * k) & 0x0FFF
        w = np.empty(nw, np.uint16)
        w[0::2] = a | 0x4000                       # comparador A alto
        w[1::2] = 2048 | 0x8000                    # canal B
        if k >= 2:
            w |= 0x1000                            # barrera 1 activa desde el bloque 2
        flags = capture.FLAG_OVERFLOW if (drop is not None and k == drop + 1) else 0
        frames.append(capture.build_frame(capture.TYPE_SAMPLES, flags, capture.CHAN_AB, k, nw,
                                          fs_total, 1_000_000 + k * nw * 2, int(drop is not None and k > drop),
                                          w.astype("<u2").tobytes()))
        ref.append(a)
    return frames, ref


def test_crc16_known_value():
    assert capture.crc16(b"123456789") == 0x29B1


def test_parser_roundtrip_with_text_and_chunking():
    frames, ref = make_frames()
    stream = b"#OK START\n" + frames[0] + frames[1] + b"#STATUS run=1\n" + b"".join(frames[2:]) + b"#OK STOP\n"
    for chunk in (1, 7, 100, len(stream)):
        ps = capture.StreamParser()
        for i in range(0, len(stream), chunk):
            ps.feed(stream[i:i + chunk])
        assert len(ps.frames) == 5 and ps.crc_errors == 0
        assert [f["seq"] for f in ps.frames] == [0, 1, 2, 3, 4]
        assert ps.lines == ["#OK START", "#STATUS run=1", "#OK STOP"]
    sw = capture.frames_to_swipes(ps.frames)[0]
    assert sw.fs == 250000 and np.array_equal(sw.chA, np.concatenate(ref))
    assert np.all(sw.chB == 2048)
    assert np.all((sw.dig >> 2) & 1 == 1) and np.all((sw.dig >> 3) & 1 == 0)
    assert sw.meta["dropped_blocks"] == 0 and sw.meta["gaps"] == []
    # flanco de barrera deducido de los bits (no hay tramas de eventos): inicio del bloque 2
    assert sw.gate_edges.tolist() == [[64 / 250000, 1.0, 1.0]]


def test_parser_detects_crc_error_and_resyncs():
    frames, _ = make_frames()
    bad = bytearray(frames[2])
    bad[50] ^= 0x10
    ps = capture.StreamParser()
    ps.feed(b"\x00\x01garbage" + frames[0] + frames[1] + bytes(bad) + frames[3] + frames[4])
    assert ps.crc_errors == 1
    assert [f["seq"] for f in ps.frames] == [0, 1, 3, 4]
    sw = capture.frames_to_swipes(ps.frames)[0]
    assert sw.meta["dropped_blocks"] == 1 and sw.meta["gaps"] == [[64, 32]]
    assert np.all(sw.chA[64:96] == 2048)           # hueco rellenado con el valor medio


def test_dropped_block_is_flagged():
    frames, _ = make_frames(drop=1)
    ps = capture.StreamParser()
    ps.feed(b"".join(frames))
    assert ps.frames[1]["flags"] & capture.FLAG_OVERFLOW and ps.frames[-1]["drop_count"] == 1
    sw = capture.frames_to_swipes(ps.frames)[0]
    assert sw.meta["dropped_blocks"] == 1 and sw.meta["gaps"] == [[32, 32]]
    assert len(sw.chA) == 5 * 32                   # la base de tiempos se conserva


def test_event_frames_give_gate_edges():
    frames, _ = make_frames()
    ev = struct.pack("<QBBH", 1_000_000 + 300, 1, 1, 0) + struct.pack("<QBBH", 1_000_000 + 500, 2, 1, 0)
    evf = capture.build_frame(capture.TYPE_EVENTS, 0, 0, 0, 2, 500000, 0, 0, ev)
    ps = capture.StreamParser()
    ps.feed(frames[0] + evf + b"".join(frames[1:]))
    sw = capture.frames_to_swipes(ps.frames)[0]
    assert np.allclose(sw.gate_edges, [[300e-6, 1, 1], [500e-6, 2, 1]])


@pytest.mark.skipif(not HAVE_CC, reason="hace falta gcc y make")
@pytest.mark.parametrize("trig", [0, 1])
def test_c_generated_stream_end_to_end(trig, tmp_path):
    """Camino de tramas del firmware simulado en host (C) -> analizador Python -> decodificacion."""
    cdecode.build()
    sw0 = synth.synthesize(text=T2, speed=0.5, snr_db=40, gates=False, quiet_ms=150, seed=1)
    vec, out = tmp_path / "v.i16", tmp_path / "s.bin"
    sw0.adc.astype("<i2").tofile(vec)
    subprocess.run([cdecode.TEST_HOST, "stream", str(vec), str(out), "500000", str(trig)], check=True)
    ps = capture.StreamParser()
    data = out.read_bytes()
    for i in range(0, len(data), 4093):
        ps.feed(data[i:i + 4093])
    assert ps.crc_errors == 0 and ps.junk_bytes == 0
    assert "#OK START" in ps.lines and "#OK STOP" in ps.lines
    swipes = capture.frames_to_swipes(ps.frames)
    assert len(swipes) == 1
    sw = swipes[0]
    assert sw.fs == 250000 and sw.meta["dropped_blocks"] == 0
    nblk = len(sw0.adc) * 2 // 1024
    samples = [f for f in ps.frames if f["type"] == capture.TYPE_SAMPLES]
    if not trig:
        assert len(samples) == nblk
        assert np.array_equal(sw.chA, sw0.adc[:nblk * 512])
    else:
        assert len(samples) < nblk                 # solo se transmite la pasada
        assert samples[0]["flags"] & capture.FLAG_SEG_FIRST and samples[-1]["flags"] & capture.FLAG_SEG_LAST
        assert all(f["flags"] & capture.FLAG_TRIGGERED for f in samples)
        first = samples[0]["seq"] * 512
        assert np.array_equal(sw.chA, sw0.adc[first:first + len(sw.chA)])
        # pre-disparo >= 20 ms antes de la primera muestra por encima del umbral (150 cuentas)
        i_thr = int(np.flatnonzero(np.abs(sw0.adc.astype(int) - 2048) > 150)[0])
        assert 0.020 <= (i_thr - first) / 250000 <= 0.020 + 2 * 1024 / 500000
        # cola de silencio ~100 ms
        i_last = int(np.flatnonzero(np.abs(sw0.adc.astype(int) - 2048) > 150)[-1])
        assert 0.095 <= (first + len(sw.chA) - i_last) / 250000 <= 0.105
        assert "#SEG END" in ps.lines
    # comparador A (bit 14) y barrera 1 (evento con marca de tiempo) tal como los genero el C
    assert np.array_equal((sw.dig >> 2) & 1, (sw.chA > 2048).astype(np.uint8))
    assert len(sw.gate_edges) == 1 and sw.gate_edges[0, 1] == 1
    t_gate_abs = (len(sw0.adc) // 2) / 250000
    assert abs(sw.gate_edges[0, 0] + samples[0]["seq"] * 512 / 250000 - t_gate_abs) < 3e-6
    r = decode.decode(sw.chA, sw.fs)
    assert r.status == decode.OK and r.text == T2


@pytest.mark.skipif(not HAVE_CC, reason="hace falta gcc y make")
def test_c_generated_stream_dropped_block(tmp_path):
    cdecode.build()
    sw0 = synth.synthesize(text=T2, speed=0.5, snr_db=40, gates=False, seed=1)
    vec, out = tmp_path / "v.i16", tmp_path / "s.bin"
    sw0.adc.astype("<i2").tofile(vec)
    subprocess.run([cdecode.TEST_HOST, "stream", str(vec), str(out), "500000", "0", "40"], check=True)
    ps = capture.StreamParser()
    ps.feed(out.read_bytes())
    seqs = [f["seq"] for f in ps.frames if f["type"] == capture.TYPE_SAMPLES]
    assert 40 not in seqs and 39 in seqs and 41 in seqs
    f41 = next(f for f in ps.frames if f["type"] == capture.TYPE_SAMPLES and f["seq"] == 41)
    assert f41["flags"] & capture.FLAG_OVERFLOW and f41["drop_count"] == 1
    sw = capture.frames_to_swipes(ps.frames)[0]
    assert sw.meta["dropped_blocks"] == 1 and sw.meta["gaps"] == [[40 * 512, 512]]


def test_cli_bin_conversion(tmp_path):
    frames, _ = make_frames()
    f = tmp_path / "s.bin"
    f.write_bytes(b"#VER maghead_capture 0.1.0\n" + b"".join(frames))
    meta = tmp_path / "m.json"
    meta.write_text(json.dumps({"card_id": "LAB-01", "head_variant": "V1"}))
    assert capture.main(["bin", str(f), "--out", str(tmp_path / "o"), "--meta", str(meta)]) == 0
    bases = swipefile.list_swipes(str(tmp_path / "o"))
    assert len(bases) == 1
    sw = swipefile.load(bases[0])
    assert sw.meta["card_id"] == "LAB-01" and sw.meta["firmware_version"] == "maghead_capture 0.1.0"
    assert sw.meta["capture_source"] == "serial" and len(sw.chA) == 160


@pytest.mark.parametrize("fs", [96000, 192000])
def test_wav_import(fs, tmp_path):
    from scipy.io import wavfile
    sw0 = synth.synthesize(text=T2, speed=0.3, fs=fs, snr_db=35, gates=False)
    x = ((sw0.adc.astype(float) - 2048) / 2048 * 20000).astype(np.int16)
    st = np.stack([x, np.zeros_like(x)], axis=1)
    wavfile.write(tmp_path / "s.wav", fs, st)
    sw = capture.import_wav(str(tmp_path / "s.wav"), volts_full_scale=2.0)
    assert sw.fs == fs and len(sw.chA) == len(x) and len(sw.chB) == len(x)
    assert abs(sw.meta["volts_per_count"] - 2.0 / 2047) < 1e-12 and sw.meta["capture_source"] == "wav"
    r = decode.decode(sw.chA, sw.fs)
    assert r.status == decode.OK and r.text == T2


def test_csv_import(tmp_path):
    sw0 = synth.synthesize(text=T1, speed=0.5, snr_db=35, gates=False)
    t = np.arange(len(sw0.adc)) / sw0.fs
    v = sw0.adc * 3.3 / 4096
    p = tmp_path / "scope.csv"
    with open(p, "w") as f:
        f.write("Model,DSO-X\nSample Interval,4e-06\nTIME,CH1\n")
        for a, b in zip(t, v):
            f.write(f"{a:.7e},{b:.5f}\n")
    sw = capture.import_csv(str(p))
    assert abs(sw.fs - 250e3) < 1 and len(sw.chA) == len(v)
    assert np.max(np.abs(sw.chA.astype(int) - sw0.adc)) <= 3   # mediana ~2048 + redondeo del CSV
    r = decode.decode(sw.chA, sw.fs)
    assert r.status == decode.OK and r.text == T1
    assert capture.main(["csv", str(p), "--out", str(tmp_path / "x" / "p1")]) == 0
    assert swipefile.load(str(tmp_path / "x" / "p1")).meta["capture_source"] == "csv"


def test_swipefile_roundtrip_and_schema(tmp_path):
    s = synth.synthesize(text=T2, speed=0.4, snr_db=30)
    sw = synth.to_swipe(s, meta={"operator": "pytest", "spacing_shim_um": 25.0})
    assert swipefile.validate_meta(sw.meta) == []
    base = swipefile.save(sw, str(tmp_path / "a" / "sw001"))
    sw2 = swipefile.load(base + ".npz")
    assert np.array_equal(sw2.chA, s.adc) and sw2.chA.dtype == np.int16 and sw2.fs == s.fs
    assert sw2.dig.dtype == np.uint8 and np.array_equal(sw2.dig & 1, s.gate1)
    assert np.allclose(sw2.gate_edges, s.gate_edges) and sw2.gate_edges.shape == (2, 3)
    assert sw2.meta["operator"] == "pytest" and sw2.meta["swipe_id"] == "sw001"
    assert sw2.meta["expected_tracks"] == {"2": T2}
    # todas las claves de la plantilla estan documentadas en el esquema
    assert set(swipefile.new_meta()) <= set(swipefile.SCHEMA)
    bad = dict(sw.meta)
    del bad["card_id"]
    bad["track_under_test"] = 1
    probs = swipefile.validate_meta(bad)
    assert any("card_id" in p for p in probs) and any("pista 1" in p for p in probs)
