/* mh_proto.c - Protocolo de tramas del firmware maghead_capture (portable). Ver mh_proto.h. */
#include "mh_proto.h"
#include <string.h>

uint16_t mh_crc16(const uint8_t *p, size_t n, uint16_t crc)
{
    size_t i;
    int b;
    for (i = 0; i < n; i++) {
        crc ^= (uint16_t)p[i] << 8;
        for (b = 0; b < 8; b++)
            crc = (crc & 0x8000) ? (uint16_t)((crc << 1) ^ 0x1021) : (uint16_t)(crc << 1);
    }
    return crc;
}

static void put16(uint8_t *p, uint16_t v) { p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); }
static void put32(uint8_t *p, uint32_t v) { put16(p, (uint16_t)v); put16(p + 2, (uint16_t)(v >> 16)); }
static void put64(uint8_t *p, uint64_t v) { put32(p, (uint32_t)v); put32(p + 4, (uint32_t)(v >> 32)); }
static uint16_t get16(const uint8_t *p) { return (uint16_t)(p[0] | (p[1] << 8)); }
static uint32_t get32(const uint8_t *p) { return (uint32_t)get16(p) | ((uint32_t)get16(p + 2) << 16); }
static uint64_t get64(const uint8_t *p) { return (uint64_t)get32(p) | ((uint64_t)get32(p + 4) << 32); }

size_t mh_pack_header(uint8_t *o, const mh_hdr_t *h)
{
    o[0] = MH_MAGIC0; o[1] = MH_MAGIC1; o[2] = MH_MAGIC2; o[3] = MH_MAGIC3;
    o[4] = h->type; o[5] = h->flags; o[6] = h->chan_mode; o[7] = h->version;
    put32(o + 8, h->seq);
    put16(o + 12, h->count);
    put16(o + 14, h->payload_len);
    put32(o + 16, h->fs_total_hz);
    put64(o + 20, h->t0_us);
    put32(o + 28, h->drop_count);
    return MH_HDR_LEN;
}

int mh_unpack_header(const uint8_t *i, mh_hdr_t *h)
{
    if (i[0] != MH_MAGIC0 || i[1] != MH_MAGIC1 || i[2] != MH_MAGIC2 || i[3] != MH_MAGIC3) return -1;
    h->type = i[4]; h->flags = i[5]; h->chan_mode = i[6]; h->version = i[7];
    h->seq = get32(i + 8);
    h->count = get16(i + 12);
    h->payload_len = get16(i + 14);
    h->fs_total_hz = get32(i + 16);
    h->t0_us = get64(i + 20);
    h->drop_count = get32(i + 28);
    return 0;
}

size_t mh_build_sample_frame(uint8_t *out, mh_hdr_t *h, const uint16_t *adc,
                             const uint32_t *dig, uint16_t n_words)
{
    uint16_t i, crc;
    uint8_t *p = out + MH_HDR_LEN;
    h->type = MH_TYPE_SAMPLES;
    h->version = MH_PROTO_VERSION;
    h->count = n_words;
    h->payload_len = (uint16_t)(2u * n_words);
    mh_pack_header(out, h);
    for (i = 0; i < n_words; i++) {
        uint16_t w = adc[i] & 0x0FFF;
        uint32_t nib = dig ? (dig[i >> 3] >> ((i & 7u) * 4u)) & 0xFu : (MH_DIG_GATE1 | MH_DIG_GATE2);
        int chb = (h->chan_mode == MH_CHAN_B) || (h->chan_mode == MH_CHAN_AB && (i & 1u));
        if (!(nib & MH_DIG_GATE1)) w |= MH_W_GATE1;          /* activa a nivel bajo */
        if (!(nib & MH_DIG_GATE2)) w |= MH_W_GATE2;
        if (nib & (chb ? MH_DIG_COMP_B : MH_DIG_COMP_A)) w |= MH_W_COMP;
        if (chb) w |= MH_W_CHB;
        put16(p, w);
        p += 2;
    }
    crc = mh_crc16(out, (size_t)(p - out), 0xFFFF);
    put16(p, crc);
    return (size_t)(p - out) + 2;
}

void mh_pack_event(uint8_t *o, uint64_t t_us, uint8_t source, uint8_t level)
{
    put64(o, t_us); o[8] = source; o[9] = level; o[10] = 0; o[11] = 0;
}

size_t mh_build_event_frame(uint8_t *out, mh_hdr_t *h, const uint8_t *events, uint16_t n_events)
{
    size_t n = (size_t)n_events * MH_EVENT_LEN;
    uint16_t crc;
    h->type = MH_TYPE_EVENTS;
    h->version = MH_PROTO_VERSION;
    h->count = n_events;
    h->payload_len = (uint16_t)n;
    mh_pack_header(out, h);
    memcpy(out + MH_HDR_LEN, events, n);
    crc = mh_crc16(out, MH_HDR_LEN + n, 0xFFFF);
    put16(out + MH_HDR_LEN + n, crc);
    return MH_HDR_LEN + n + 2;
}

int mh_block_activity(const uint16_t *adc, const uint32_t *dig, uint16_t n_words,
                      uint8_t chan_mode, const int32_t mid[2], int32_t thr, int32_t mean[2])
{
    int32_t sum[2] = { 0, 0 }, cnt[2] = { 0, 0 };
    int act = 0;
    uint16_t i;
    for (i = 0; i < n_words; i++) {
        int ch = (chan_mode == MH_CHAN_B) || (chan_mode == MH_CHAN_AB && (i & 1u));
        int32_t v = adc[i] & 0x0FFF, d = v - mid[ch];
        sum[ch] += v; cnt[ch]++;
        if (d > thr || d < -thr) act = 1;
    }
    if (dig) {
        for (i = 0; i < n_words / 8; i++) {
            /* algun nibble con GATE1 o GATE2 a nivel bajo */
            if ((dig[i] & 0xCCCCCCCCu) != 0xCCCCCCCCu) { act = 1; break; }
        }
    }
    mean[0] = cnt[0] ? sum[0] / cnt[0] : mid[0];
    mean[1] = cnt[1] ? sum[1] / cnt[1] : mid[1];
    return act;
}

void mh_trig_init(mh_trig_t *t, uint32_t fs_total_hz, uint32_t block_words)
{
    /* bloques que cubren 20 ms y 100 ms, redondeando hacia arriba */
    uint64_t num = (uint64_t)fs_total_hz;
    t->pre_blocks = (uint32_t)((num * 20 + 1000ull * block_words - 1) / (1000ull * block_words));
    t->quiet_blocks = (uint32_t)((num * 100 + 1000ull * block_words - 1) / (1000ull * block_words));
    if (t->pre_blocks < 1) t->pre_blocks = 1;
    if (t->quiet_blocks < 1) t->quiet_blocks = 1;
    t->quiet = 0;
    t->active = 0;
}

int mh_trig_step(mh_trig_t *t, int activity)
{
    if (!t->active) {
        if (!activity) return MH_TRIG_IDLE;
        t->active = 1; t->quiet = 0;
        return MH_TRIG_START;
    }
    if (activity) { t->quiet = 0; return MH_TRIG_SEND; }
    if (++t->quiet >= t->quiet_blocks) { t->active = 0; t->quiet = 0; return MH_TRIG_LAST; }
    return MH_TRIG_SEND;
}

int mh_rate_valid(uint32_t fs)
{
    static const uint32_t ok[] = { 500000, 250000, 200000, 125000, 100000, 50000 };
    size_t i;
    for (i = 0; i < sizeof(ok) / sizeof(ok[0]); i++) if (ok[i] == fs) return 1;
    return 0;
}

/* ------------------------------------------------------------------ comandos */

static int up(int c) { return (c >= 'a' && c <= 'z') ? c - 32 : c; }

static const char *skip_sp(const char *s) { while (*s == ' ' || *s == '\t') s++; return s; }

/* compara palabra (sin distinguir mayusculas); devuelve puntero tras ella o NULL */
static const char *word(const char *s, const char *w)
{
    while (*w) { if (up((unsigned char)*s) != *w) return NULL; s++; w++; }
    if (*s && *s != ' ' && *s != '\t' && *s != '\r' && *s != '\n') return NULL;
    return skip_sp(s);
}

static int at_end(const char *s) { return *s == 0 || *s == '\r' || *s == '\n'; }

static int parse_u(const char *s, int32_t *v)
{
    int32_t x = 0, n = 0;
    while (*s >= '0' && *s <= '9') { if (x > 100000000) return -1; x = x * 10 + (*s - '0'); s++; n++; }
    s = skip_sp(s);
    if (!n || !at_end(s)) return -1;
    *v = x;
    return 0;
}

static int parse_onoff(const char *s, int32_t *v)
{
    const char *e;
    if ((e = word(s, "ON")) && at_end(e)) { *v = 1; return 0; }
    if ((e = word(s, "OFF")) && at_end(e)) { *v = 0; return 0; }
    if ((e = word(s, "1")) && at_end(e)) { *v = 1; return 0; }
    if ((e = word(s, "0")) && at_end(e)) { *v = 0; return 0; }
    return -1;
}

mh_cmd_id_t mh_parse_cmd(const char *line, mh_cmd_t *out)
{
    const char *s = skip_sp(line), *a;
    out->id = MH_CMD_ERR; out->arg = 0;
    if (at_end(s)) { out->id = MH_CMD_NONE; return out->id; }
#define SIMPLE(name, idv) if ((a = word(s, name))) { if (at_end(a)) out->id = idv; return out->id; }
    SIMPLE("START", MH_CMD_START)
    SIMPLE("STOP", MH_CMD_STOP)
    SIMPLE("STATUS", MH_CMD_STATUS)
    SIMPLE("VER", MH_CMD_VER)
    SIMPLE("HELP", MH_CMD_HELP)
#undef SIMPLE
    if ((a = word(s, "RATE"))) { if (!parse_u(a, &out->arg) && out->arg > 0) out->id = MH_CMD_RATE; return out->id; }
    if ((a = word(s, "THR")))  { if (!parse_u(a, &out->arg) && out->arg > 0 && out->arg < 2048) out->id = MH_CMD_THR; return out->id; }
    if ((a = word(s, "TRIG"))) { if (!parse_onoff(a, &out->arg)) out->id = MH_CMD_TRIG; return out->id; }
    if ((a = word(s, "STREAM"))) { if (!parse_onoff(a, &out->arg)) out->id = MH_CMD_STREAM; return out->id; }
    if ((a = word(s, "CHAN"))) {
        const char *e;
        if ((e = word(a, "AB")) && at_end(e)) { out->arg = MH_CHAN_AB; out->id = MH_CMD_CHAN; }
        else if ((e = word(a, "A")) && at_end(e)) { out->arg = MH_CHAN_A; out->id = MH_CMD_CHAN; }
        else if ((e = word(a, "B")) && at_end(e)) { out->arg = MH_CHAN_B; out->id = MH_CMD_CHAN; }
        return out->id;
    }
    if ((a = word(s, "DECODE"))) {
        const char *e;
        /* arg: -1 = apagado, 0 = AUTO, 1 = T1, 2 = T2 (f2f_fmt_t) */
        if ((e = word(a, "OFF")) && at_end(e)) { out->arg = -1; out->id = MH_CMD_DECODE; }
        else if ((e = word(a, "AUTO")) && at_end(e)) { out->arg = 0; out->id = MH_CMD_DECODE; }
        else if ((e = word(a, "ON")) && at_end(e)) { out->arg = 0; out->id = MH_CMD_DECODE; }
        else if ((e = word(a, "T1")) && at_end(e)) { out->arg = 1; out->id = MH_CMD_DECODE; }
        else if ((e = word(a, "T2")) && at_end(e)) { out->arg = 2; out->id = MH_CMD_DECODE; }
        return out->id;
    }
    return out->id;
}
