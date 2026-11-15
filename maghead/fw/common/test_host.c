/*
 * test_host.c - Arnes de pruebas en HOST (gcc) para los modulos portables:
 * f2f_decode.[ch] y mh_proto.[ch].
 *
 *   test_host selftest                      pruebas unitarias internas
 *   test_host decode <vec.i16> [fmt]        decodifica un vector de muestras int16 LE
 *                                           (fmt: 0 auto, 1 pista 1, 2 pistas 2/3) y vuelca
 *                                           resultado, transiciones y bits (texto)
 *   test_host edges <vec.i64> [fmt]         idem con marcas de tiempo de flancos int64 LE
 *   test_host stream <vec.i16> <out.bin> <fs_total> <trig 0|1> [drop_block]
 *                                           simula el camino de tramas del firmware (canal A =
 *                                           vector, canal B = 2048) y escribe el flujo binario
 *                                           que leeria el PC; drop_block simula un bloque perdido
 */
#include "f2f_decode.h"
#include "mh_proto.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int f2f_host_run(const uint16_t *x, size_t n, int fmt, const f2f_cfg_t *cfg,
                 const uint32_t *decims, f2f_result_t *res,
                 int64_t *tlog, int32_t *vlog, uint32_t *plog, uint32_t cap, uint32_t *n_tlog,
                 uint8_t *bits, uint32_t *bper, uint32_t *n_bits);
int f2f_host_run_edges(const int64_t *t, size_t n, int fmt, const f2f_cfg_t *cfg,
                       f2f_result_t *res, uint8_t *bits, uint32_t *n_bits);

static int n_pass, n_fail;
#define CHECK(cond) do { if (cond) n_pass++; else { n_fail++; \
    printf("FALLO %s:%d: %s\n", __FILE__, __LINE__, #cond); } } while (0)

/* ---- codificador minimo para las pruebas ---- */
static int enc_track(const char *text, int fmt, uint8_t *bits, int lead, int trail)
{
    int nb = fmt == 1 ? 7 : 5, nd = nb - 1, base = fmt == 1 ? 0x20 : 0x30;
    int n = 0, i, k, lrc = 0, len = (int)strlen(text);
    for (i = 0; i < lead; i++) bits[n++] = 0;
    for (i = 0; i <= len; i++) {
        int v = (i < len) ? text[i] - base : lrc, ones = 0;
        if (i < len) lrc ^= v;
        for (k = 0; k < nd; k++) { bits[n] = (uint8_t)((v >> k) & 1); ones += bits[n]; n++; }
        bits[n++] = (uint8_t)(1 - (ones & 1));
    }
    for (i = 0; i < trail; i++) bits[n++] = 0;
    return n;
}

static void rev_bits(uint8_t *b, int n)
{
    int i;
    for (i = 0; i < n / 2; i++) { uint8_t t = b[i]; b[i] = b[n - 1 - i]; b[n - 1 - i] = t; }
}

/* bits -> marcas de tiempo de flancos, con periodo que varia linealmente p0 -> p1 */
static size_t bits_to_edges(const uint8_t *bits, int n, int64_t p0, int64_t p1, int64_t *t)
{
    size_t k = 0;
    int64_t now = 1000;
    int i;
    t[k++] = now;
    for (i = 0; i < n; i++) {
        int64_t p = p0 + (p1 - p0) * i / (n > 1 ? n - 1 : 1);
        if (bits[i]) { t[k++] = now + p / 2; }
        now += p;
        t[k++] = now;
    }
    return k;
}

static const char *T1 = "%B1234567890123445^MAGHEAD/TEST^99011200000000000000**XXX******?";
static const char *T2 = ";1234567890123445=99011200123400000000?";

static void selftest(void)
{
    static uint8_t bits[F2F_MAX_BITS];
    static int64_t edges[2 * F2F_MAX_BITS + 2];
    f2f_result_t r;
    f2f_cfg_t cfg;
    int n;
    size_t ne;

    f2f_cfg_default(&cfg);

    /* --- capa ISO: ambas pistas, ambos sentidos --- */
    n = enc_track(T2, 2, bits, 20, 30);
    CHECK(f2f_decode_bits(bits, NULL, n, F2F_FMT_T2, 4, &r) == F2F_OK);
    CHECK(strcmp(r.text, T2) == 0 && r.direction == F2F_DIR_FWD && r.leading_zeros == 20 && r.lrc_ok);
    CHECK(f2f_decode_bits(bits, NULL, n, F2F_FMT_AUTO, 4, &r) == F2F_OK && r.fmt == F2F_FMT_T2);
    rev_bits(bits, n);
    CHECK(f2f_decode_bits(bits, NULL, n, F2F_FMT_AUTO, 4, &r) == F2F_OK);
    CHECK(strcmp(r.text, T2) == 0 && r.direction == F2F_DIR_REV && r.leading_zeros == 20);

    n = enc_track(T1, 1, bits, 57, 40);
    CHECK(f2f_decode_bits(bits, NULL, n, F2F_FMT_T1, 4, &r) == F2F_OK);
    CHECK(strcmp(r.text, T1) == 0 && r.direction == F2F_DIR_FWD && r.leading_zeros == 57);
    CHECK(f2f_decode_bits(bits, NULL, n, F2F_FMT_AUTO, 4, &r) == F2F_OK && r.fmt == F2F_FMT_T1);
    rev_bits(bits, n);
    CHECK(f2f_decode_bits(bits, NULL, n, F2F_FMT_T1, 4, &r) == F2F_OK && r.direction == F2F_DIR_REV);
    CHECK(strcmp(r.text, T1) == 0);

    /* --- un bit corrupto en el caracter 5 => error de paridad en la posicion 5 --- */
    n = enc_track(T2, 2, bits, 20, 30);
    bits[20 + 5 * 5 + 1] ^= 1;
    CHECK(f2f_decode_bits(bits, NULL, n, F2F_FMT_T2, 4, &r) == F2F_PARITY_ERR);
    CHECK(r.n_parity_err == 1 && r.parity_pos[0] == 5 && !r.lrc_ok);
    /* --- dos bits en el mismo caracter: paridad bien, LRC mal --- */
    bits[20 + 5 * 5 + 2] ^= 1;
    CHECK(f2f_decode_bits(bits, NULL, n, F2F_FMT_T2, 4, &r) == F2F_LRC_ERR);
    CHECK(r.n_parity_err == 0 && !r.lrc_ok);
    /* --- bit de paridad del propio LRC corrupto --- */
    n = enc_track(T1, 1, bits, 57, 40);
    bits[57 + 7 * (int)strlen(T1) + 6] ^= 1;
    CHECK(f2f_decode_bits(bits, NULL, n, F2F_FMT_T1, 4, &r) == F2F_LRC_ERR);
    /* --- sin centinela de inicio --- */
    memset(bits, 0, 200);
    CHECK(f2f_decode_bits(bits, NULL, 200, F2F_FMT_AUTO, 4, &r) == F2F_NO_START);
    /* --- truncado antes del ES --- */
    n = enc_track(T2, 2, bits, 20, 0);
    CHECK(f2f_decode_bits(bits, NULL, 20 + 5 * 10, F2F_FMT_T2, 4, &r) == F2F_NO_END);
    CHECK(r.n_chars == 10 && r.n_parity_err == 0);

    /* --- ruta de flancos: velocidad constante, acelerando x3 y frenando, ambos sentidos --- */
    {
        static const int64_t P0[] = { 1000, 3000, 1000, 400 }, P1[] = { 1000, 1000, 3000, 400 };
        int c, rv, f;
        for (f = 1; f <= 2; f++) for (c = 0; c < 4; c++) for (rv = 0; rv < 2; rv++) {
            const char *txt = f == 1 ? T1 : T2;
            n = enc_track(txt, f, bits, 20, 20);
            if (rv) rev_bits(bits, n);
            ne = bits_to_edges(bits, n, P0[c], P1[c], edges);
            CHECK(f2f_host_run_edges(edges, ne, F2F_FMT_AUTO, &cfg, &r, NULL, NULL) == F2F_OK);
            CHECK(strcmp(r.text, txt) == 0 && r.direction == rv && r.fmt == f);
            CHECK(r.period_min >= 380 && r.period_max <= 3100 && r.period_min <= r.period_max);
            CHECK(r.f2f_errors == 0);
        }
    }
    /* --- sin senal --- */
    edges[0] = 0; edges[1] = 100; edges[2] = 200;
    CHECK(f2f_host_run_edges(edges, 3, F2F_FMT_AUTO, &cfg, &r, NULL, NULL) == F2F_NO_SIGNAL);
    /* --- transiciones regulares pero sin datos => NO_START --- */
    memset(bits, 0, 100);
    ne = bits_to_edges(bits, 100, 500, 500, edges);
    CHECK(f2f_host_run_edges(edges, ne, F2F_FMT_AUTO, &cfg, &r, NULL, NULL) == F2F_NO_START);
    CHECK(r.n_transitions == 101);

    /* --- muestras: senal plana => NO_SIGNAL --- */
    {
        static uint16_t x[30000];
        size_t i, k;
        for (i = 0; i < 30000; i++) x[i] = 2048;
        CHECK(f2f_host_run(x, 30000, 0, &cfg, NULL, &r, NULL, NULL, NULL, 0, NULL, NULL, NULL, NULL) == F2F_NO_SIGNAL);
        /* tren de pulsos triangulares alternos en cada flanco (pista 2, P = 100 muestras) */
        n = enc_track(T2, 2, bits, 20, 20);
        ne = bits_to_edges(bits, n, 100, 100, edges);
        for (k = 0; k < ne; k++) {
            int d, c = (int)(edges[k] - 1000 + 500);
            for (d = -15; d <= 15; d++)
                x[c + d] = (uint16_t)(x[c + d] + ((k & 1) ? -1 : 1) * (16 - (d < 0 ? -d : d)) * 40);
        }
        CHECK(f2f_host_run(x, 30000, 0, &cfg, NULL, &r, NULL, NULL, NULL, 0, NULL, NULL, NULL, NULL) == F2F_OK);
        CHECK(strcmp(r.text, T2) == 0);
        CHECK(r.period_min > 95 * F2F_TICKS_PER_SAMPLE && r.period_max < 105 * F2F_TICKS_PER_SAMPLE);
    }

    /* --- protocolo --- */
    CHECK(mh_crc16((const uint8_t *)"123456789", 9, 0xFFFF) == 0x29B1);
    {
        uint8_t buf[MH_HDR_LEN + 2 * 16 + 2];
        uint16_t adc[16];
        uint32_t dig[2] = { 0xFFFFFFFFu, 0xFFFFFFFFu };
        mh_hdr_t h, g;
        size_t len;
        int i;
        memset(&h, 0, sizeof(h));
        h.flags = MH_FLAG_TRIGGERED; h.chan_mode = MH_CHAN_AB; h.seq = 0x01020304;
        h.fs_total_hz = 500000; h.t0_us = 0x0102030405060708ull; h.drop_count = 7;
        for (i = 0; i < 16; i++) adc[i] = (uint16_t)(100 + i);
        dig[0] &= ~(uint32_t)(MH_DIG_GATE1 << 8);      /* muestra 2: barrera 1 activa */
        dig[0] &= ~(uint32_t)(MH_DIG_COMP_B << 12);    /* muestra 3 (canal B): comparador B bajo */
        len = mh_build_sample_frame(buf, &h, adc, dig, 16);
        CHECK(len == sizeof(buf));
        CHECK(mh_unpack_header(buf, &g) == 0 && g.seq == h.seq && g.t0_us == h.t0_us);
        CHECK(g.count == 16 && g.payload_len == 32 && g.drop_count == 7 && g.type == MH_TYPE_SAMPLES);
        CHECK((uint16_t)(buf[len - 2] | (buf[len - 1] << 8)) == mh_crc16(buf, len - 2, 0xFFFF));
        CHECK((buf[32] | (buf[33] << 8)) == (100 | MH_W_COMP));                 /* A, comp A alto */
        CHECK((buf[34] | (buf[35] << 8)) == (101 | MH_W_COMP | MH_W_CHB));
        CHECK((buf[36] | (buf[37] << 8)) == (102 | MH_W_COMP | MH_W_GATE1));
        CHECK((buf[38] | (buf[39] << 8)) == (103 | MH_W_CHB));
        {
            int32_t mid[2] = { 108, 108 }, mean[2];
            CHECK(mh_block_activity(adc, NULL, 16, MH_CHAN_AB, mid, 50, mean) == 0);
            CHECK(mean[0] == 107 && mean[1] == 108);
            CHECK(mh_block_activity(adc, NULL, 16, MH_CHAN_AB, mid, 5, mean) == 1);
            CHECK(mh_block_activity(adc, dig, 16, MH_CHAN_AB, mid, 50, mean) == 1);  /* barrera */
        }
    }
    {
        mh_trig_t t;
        int i, r2 = 0;
        mh_trig_init(&t, 500000, 1024);
        CHECK(t.pre_blocks == 10 && t.quiet_blocks == 49);
        CHECK(mh_trig_step(&t, 0) == MH_TRIG_IDLE);
        CHECK(mh_trig_step(&t, 1) == MH_TRIG_START);
        CHECK(mh_trig_step(&t, 1) == MH_TRIG_SEND);
        for (i = 0; i < 48; i++) r2 = mh_trig_step(&t, 0);
        CHECK(r2 == MH_TRIG_SEND);
        CHECK(mh_trig_step(&t, 0) == MH_TRIG_LAST);
        CHECK(mh_trig_step(&t, 0) == MH_TRIG_IDLE);
    }
    {
        mh_cmd_t c;
        CHECK(mh_parse_cmd("start\r\n", &c) == MH_CMD_START);
        CHECK(mh_parse_cmd("  STOP", &c) == MH_CMD_STOP);
        CHECK(mh_parse_cmd("RATE 250000\n", &c) == MH_CMD_RATE && c.arg == 250000);
        CHECK(mh_parse_cmd("rate x", &c) == MH_CMD_ERR);
        CHECK(mh_parse_cmd("CHAN AB", &c) == MH_CMD_CHAN && c.arg == MH_CHAN_AB);
        CHECK(mh_parse_cmd("chan b", &c) == MH_CMD_CHAN && c.arg == MH_CHAN_B);
        CHECK(mh_parse_cmd("TRIG ON", &c) == MH_CMD_TRIG && c.arg == 1);
        CHECK(mh_parse_cmd("TRIG off", &c) == MH_CMD_TRIG && c.arg == 0);
        CHECK(mh_parse_cmd("THR 150", &c) == MH_CMD_THR && c.arg == 150);
        CHECK(mh_parse_cmd("THR 5000", &c) == MH_CMD_ERR);
        CHECK(mh_parse_cmd("DECODE T2", &c) == MH_CMD_DECODE && c.arg == 2);
        CHECK(mh_parse_cmd("DECODE OFF", &c) == MH_CMD_DECODE && c.arg == -1);
        CHECK(mh_parse_cmd("STARTX", &c) == MH_CMD_ERR);
        CHECK(mh_parse_cmd("START 1", &c) == MH_CMD_ERR);
        CHECK(mh_parse_cmd("", &c) == MH_CMD_NONE);
        CHECK(mh_rate_valid(500000) && mh_rate_valid(250000) && !mh_rate_valid(333333));
    }
    printf("selftest: %d OK, %d fallos\n", n_pass, n_fail);
}

/* ---- utilidades de archivo ---- */
static void *read_file(const char *path, size_t *len)
{
    FILE *f = fopen(path, "rb");
    long sz;
    void *buf;
    if (!f) { perror(path); exit(2); }
    fseek(f, 0, SEEK_END); sz = ftell(f); fseek(f, 0, SEEK_SET);
    buf = malloc(sz > 0 ? (size_t)sz : 1);
    if (!buf || fread(buf, 1, (size_t)sz, f) != (size_t)sz) { fprintf(stderr, "lectura fallida\n"); exit(2); }
    fclose(f);
    *len = (size_t)sz;
    return buf;
}

static void print_result(const f2f_result_t *r)
{
    int i;
    printf("status=%d\nstatus_name=%s\nfmt=%d\ndirection=%d\nlrc_ok=%d\ninstance=%d\n",
           (int)r->status, f2f_status_str(r->status), r->fmt, r->direction, r->lrc_ok, r->instance);
    printf("n_transitions=%u\nf2f_errors=%u\nn_bits=%u\nn_chars=%u\nn_parity_err=%u\n",
           (unsigned)r->n_transitions, (unsigned)r->f2f_errors, r->n_bits, r->n_chars, r->n_parity_err);
    printf("parity_pos=");
    for (i = 0; i < r->n_parity_err && i < F2F_MAX_PERR; i++) printf("%s%u", i ? "," : "", r->parity_pos[i]);
    printf("\nleading_zeros=%u\nss_bit=%u\nend_bit=%u\nlrc_value=%u\nperiod_min=%u\nperiod_max=%u\n",
           r->leading_zeros, r->ss_bit, r->end_bit, r->lrc_value,
           (unsigned)r->period_min, (unsigned)r->period_max);
    printf("text=%s\n", r->text);
}

static int cmd_decode(const char *path, int fmt)
{
    size_t len, n;
    uint16_t *x = (uint16_t *)read_file(path, &len);
    uint32_t cap, nt = 0, nb = 0, i;
    int64_t *tl; int32_t *vl; uint32_t *pl;
    static uint8_t bits[F2F_MAX_BITS];
    static uint32_t bper[F2F_MAX_BITS];
    f2f_result_t r;
    n = len / 2;
    cap = (uint32_t)n + 16;
    tl = malloc(sizeof(int64_t) * cap); vl = malloc(sizeof(int32_t) * cap); pl = malloc(sizeof(uint32_t) * cap);
    if (!tl || !vl || !pl) return 2;
    f2f_host_run(x, n, fmt, NULL, NULL, &r, tl, vl, pl, cap, &nt, bits, bper, &nb);
    print_result(&r);
    printf("bits=");
    for (i = 0; i < nb; i++) putchar('0' + bits[i]);
    printf("\nbit_period=");
    for (i = 0; i < nb; i++) printf("%s%u", i ? "," : "", (unsigned)bper[i]);
    printf("\n");
    for (i = 0; i < nt; i++) printf("T %lld %d %u\n", (long long)tl[i], (int)vl[i], (unsigned)pl[i]);
    free(tl); free(vl); free(pl); free(x);
    return 0;
}

static int cmd_edges(const char *path, int fmt)
{
    size_t len;
    int64_t *t = (int64_t *)read_file(path, &len);
    static uint8_t bits[F2F_MAX_BITS];
    uint32_t nb = 0, i;
    f2f_result_t r;
    f2f_host_run_edges(t, len / 8, fmt, NULL, &r, bits, &nb);
    print_result(&r);
    printf("bits=");
    for (i = 0; i < nb; i++) putchar('0' + bits[i]);
    printf("\n");
    free(t);
    return 0;
}

/* Simula el bucle principal del firmware: bloques A/B, disparo, tramas. */
#define BLOCK_WORDS 1024
static int cmd_stream(const char *path, const char *outp, uint32_t fs_total, int trig_on, long drop_block)
{
    size_t len, n, nblocks;
    int16_t *x = (int16_t *)read_file(path, &len);
    FILE *fo = fopen(outp, "wb");
    static uint16_t adc[BLOCK_WORDS];
    static uint32_t dig[BLOCK_WORDS / 8];
    static uint8_t frame[MH_HDR_LEN + 2 * BLOCK_WORDS + 2];
    mh_trig_t trig;
    int32_t mid[2] = { 2048, 2048 }, mean[2];
    uint32_t drops = 0, ev_seq = 0;
    int overflow = 0, first = 0, gate_sent = 0;
    long next_tx = -1;      /* -1: en reposo */
    size_t scan;
    const uint64_t t_start = 1000000;
    if (!fo) { perror(outp); return 2; }
    n = len / 2;
    nblocks = (2 * n) / BLOCK_WORDS;
    mh_trig_init(&trig, fs_total, BLOCK_WORDS);
    fputs("#OK START\n", fo);
#define FILL(bi) do { size_t i_; for (i_ = 0; i_ < BLOCK_WORDS; i_++) { \
        size_t w_ = (bi) * BLOCK_WORDS + i_; int16_t s_ = x[w_ / 2]; \
        adc[i_] = (w_ & 1) ? 2048 : (uint16_t)s_; } \
        for (i_ = 0; i_ < BLOCK_WORDS / 8; i_++) { \
            /* comparador A = signo de la muestra; barrera 1 activa en la 2a mitad del vector */ \
            uint32_t v_ = 0; int k_; for (k_ = 0; k_ < 8; k_++) { \
                size_t w_ = (bi) * BLOCK_WORDS + i_ * 8 + (size_t)k_; uint32_t nb_ = MH_DIG_GATE2; \
                if (x[w_ / 2] > 2048) nb_ |= MH_DIG_COMP_A; \
                if (w_ / 2 < n / 2) nb_ |= MH_DIG_GATE1; \
                v_ |= nb_ << (4 * k_); } dig[i_] = v_; } } while (0)
#define SEND(bi, fl) do { mh_hdr_t h_; size_t l_; memset(&h_, 0, sizeof(h_)); \
        h_.flags = (uint8_t)(fl); h_.chan_mode = MH_CHAN_AB; h_.seq = (uint32_t)(bi); \
        h_.fs_total_hz = fs_total; h_.drop_count = drops; \
        h_.t0_us = t_start + (uint64_t)(bi) * BLOCK_WORDS * 1000000ull / fs_total; \
        FILL(bi); l_ = mh_build_sample_frame(frame, &h_, adc, dig, BLOCK_WORDS); \
        fwrite(frame, 1, l_, fo); } while (0)
    for (scan = 0; scan < nblocks; scan++) {
        int act, st;
        uint8_t fl = trig_on ? MH_FLAG_TRIGGERED : 0;
        if ((long)scan == drop_block) { drops++; overflow = 1; continue; }
        FILL(scan);
        act = mh_block_activity(adc, dig, BLOCK_WORDS, MH_CHAN_AB, mid, 150, mean);
        if (!gate_sent && scan * BLOCK_WORDS / 2 >= n / 2) {   /* evento de barrera 1 */
            uint8_t ev[MH_EVENT_LEN];
            mh_hdr_t h; size_t l;
            memset(&h, 0, sizeof(h));
            h.seq = ev_seq++; h.fs_total_hz = fs_total;
            mh_pack_event(ev, t_start + (uint64_t)(n / 2) * 2 * 1000000ull / fs_total, 1, 1);
            l = mh_build_event_frame(frame, &h, ev, 1);
            fwrite(frame, 1, l, fo);
            gate_sent = 1;
        }
        if (!trig_on) {
            if (overflow) { fl |= MH_FLAG_OVERFLOW; overflow = 0; }
            SEND(scan, fl);
            continue;
        }
        st = mh_trig_step(&trig, act);
        if (st == MH_TRIG_IDLE) continue;
        if (st == MH_TRIG_START) {
            size_t bi;
            next_tx = (long)scan - (long)trig.pre_blocks;
            if (next_tx < 0) next_tx = 0;
            first = 1;
            for (bi = (size_t)next_tx; bi < scan; bi++) {
                uint8_t f2 = fl;
                if ((long)bi == drop_block) continue;
                if (first) { f2 |= MH_FLAG_SEG_FIRST; first = 0; }
                SEND(bi, f2);
            }
        }
        if (first) { fl |= MH_FLAG_SEG_FIRST; first = 0; }
        if (overflow) { fl |= MH_FLAG_OVERFLOW; overflow = 0; }
        if (st == MH_TRIG_LAST) fl |= MH_FLAG_SEG_LAST;
        SEND(scan, fl);
        if (st == MH_TRIG_LAST) fputs("#SEG END\n", fo);
    }
    fputs("#OK STOP\n", fo);
    fclose(fo);
    free(x);
    return 0;
}

int main(int argc, char **argv)
{
    if (argc >= 2 && !strcmp(argv[1], "selftest")) { selftest(); return n_fail ? 1 : 0; }
    if (argc >= 3 && !strcmp(argv[1], "decode")) return cmd_decode(argv[2], argc > 3 ? atoi(argv[3]) : 0);
    if (argc >= 3 && !strcmp(argv[1], "edges")) return cmd_edges(argv[2], argc > 3 ? atoi(argv[3]) : 0);
    if (argc >= 6 && !strcmp(argv[1], "stream"))
        return cmd_stream(argv[2], argv[3], (uint32_t)atol(argv[4]), atoi(argv[5]),
                          argc > 6 ? atol(argv[6]) : -1);
    fprintf(stderr, "uso: test_host selftest | decode <vec.i16> [fmt] | edges <vec.i64> [fmt] |\n"
                    "     stream <vec.i16> <out.bin> <fs_total> <trig> [drop_block]\n");
    return 2;
}
