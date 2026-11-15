/*
 * f2f_decode.c - Decodificador F2F / ISO 7811 portable. Ver f2f_decode.h.
 *
 * Solo C99 + stdint. Sin malloc, sin coma flotante. Las divisiones de 64 bits
 * solo ocurren una vez por pico detectado, no por muestra.
 *
 * OJO: cualquier cambio aqui debe replicarse en tools/maghead/decode.py
 * (la prueba tools/tests/test_c_decoder.py exige resultados identicos).
 */
#include "f2f_decode.h"
#include <string.h>

void f2f_cfg_default(f2f_cfg_t *c)
{
    c->thr_frac_q8 = 77;         /* 0.30 de la envolvente pico-pico */
    c->noise_floor = 24;         /* cuentas ADC p-p (~19 mV a 3.3 V / 4096) */
    c->class_thr_q8 = 184;       /* 0.72 */
    c->pair_thr_q8 = 320;        /* 1.25 */
    c->period_alpha_shift = 2;   /* alfa = 1/4 */
    c->period_bound_shift = 2;   /* +-25 % por actualizacion */
    c->sync_count = 4;
    c->sync_tol_q8 = 51;         /* 20 % */
    c->min_transitions = 10;
    c->min_lead_zeros = 4;
}

void f2f_init(f2f_t *d, const f2f_cfg_t *cfg, uint32_t decim)
{
    memset(d, 0, sizeof(*d));
    if (cfg) d->cfg = *cfg; else f2f_cfg_default(&d->cfg);
    d->decim = decim ? decim : 1;
}

void f2f_set_log(f2f_t *d, int64_t *t, int32_t *v, uint32_t *p, uint32_t cap)
{
    d->tlog_t = t; d->tlog_v = v; d->tlog_p = p; d->tlog_cap = cap; d->tlog_n = 0;
}

/* ------------------------------------------------------------------ bits */

static void emit_bit(f2f_t *d, uint8_t b, uint32_t per)
{
    if (d->n_bits < F2F_MAX_BITS) {
        d->bits[d->n_bits] = b;
        d->bit_period[d->n_bits] = per;
        d->n_bits++;
    }
}

/* IIR acotado: P += clamp(meas - P, +-P>>bound) >> alpha */
static void period_update(f2f_t *d, int64_t meas)
{
    int64_t p = (int64_t)d->period;
    int64_t diff = meas - p;
    int64_t bound = p >> d->cfg.period_bound_shift;
    if (diff > bound) diff = bound;
    if (diff < -bound) diff = -bound;
    if (diff >= 0) p += diff >> d->cfg.period_alpha_shift;
    else           p -= (-diff) >> d->cfg.period_alpha_shift;
    if (p < 1) p = 1;
    d->period = (uint32_t)p;
}

static void bits_unlock(f2f_t *d)
{
    d->locked = 0; d->sync_n = 0; d->sync_sum = 0; d->half_pending = 0; d->bad_run = 0;
}

static void bits_feed(f2f_t *d, int64_t t)
{
    int64_t iv, p;
    d->n_trans++;
    if (!d->have_last) { d->last_t = t; d->have_last = 1; return; }
    iv = t - d->last_t;
    d->last_t = t;
    if (iv <= 0) return;

    if (!d->locked) {
        /* Enganche: sync_count intervalos consecutivos iguales dentro de la
         * tolerancia (preambulo de ceros). */
        if (d->sync_n == 0) {
            d->sync_sum = iv; d->sync_n = 1;
        } else {
            int64_t mean = d->sync_sum / d->sync_n;
            int64_t dev = iv - mean;
            if (dev < 0) dev = -dev;
            if (dev * 256 <= (int64_t)d->cfg.sync_tol_q8 * mean) {
                d->sync_sum += iv; d->sync_n++;
            } else {
                d->sync_sum = iv; d->sync_n = 1;
            }
        }
        if (d->sync_n >= d->cfg.sync_count) {
            int i;
            int64_t per = d->sync_sum / d->sync_n;
            if (per < 1) per = 1;
            d->period = (uint32_t)per;
            d->locked = 1; d->half_pending = 0; d->bad_run = 0;
            for (i = 0; i < d->sync_n; i++) emit_bit(d, 0, d->period);
        }
        return;
    }

    p = (int64_t)d->period;
    if (iv > 4 * p) {                       /* hueco: fin de zona o perdida de senal */
        d->f2f_errors++;
        bits_unlock(d);
        return;
    }
    if (d->half_pending) {
        /* Criterio de pareja: la suma de las dos medias celdas es inmune al
         * desplazamiento de pico de la transicion central. */
        int64_t sum = d->half_iv + iv;
        d->half_pending = 0;
        if (sum * 256 <= (int64_t)d->cfg.pair_thr_q8 * p) {
            emit_bit(d, 1, (uint32_t)sum);
            period_update(d, sum);
            d->bad_run = 0;
        } else {
            d->f2f_errors++;                /* media + entera: transicion perdida o sobrante */
            emit_bit(d, 0, (uint32_t)p);
            if (++d->bad_run >= 3) bits_unlock(d);
        }
        return;
    }
    if (iv * 256 < (int64_t)d->cfg.class_thr_q8 * p) {
        d->half_pending = 1;
        d->half_iv = iv;
        return;
    }
    if (iv * 2 > 3 * p) {                   /* > 1.5 P: falta alguna transicion */
        int64_t nb = (iv + p / 2) / p, i;
        d->f2f_errors++;
        for (i = 0; i < nb; i++) emit_bit(d, 0, (uint32_t)(iv / nb));
        if (++d->bad_run >= 3) bits_unlock(d);
        return;
    }
    emit_bit(d, 0, (uint32_t)iv);
    period_update(d, iv);
    d->bad_run = 0;
}

void f2f_feed_edge(f2f_t *d, int64_t t_ticks)
{
    bits_feed(d, t_ticks);
    if (d->tlog_n < d->tlog_cap) {
        if (d->tlog_t) d->tlog_t[d->tlog_n] = t_ticks;
        if (d->tlog_v) d->tlog_v[d->tlog_n] = 0;
        if (d->tlog_p) d->tlog_p[d->tlog_n] = d->locked ? d->period : 0;
        d->tlog_n++;
    }
}

/* ------------------------------------------------------------------ picos */

static void set_ext(f2f_t *d, int32_t y)
{
    d->ext = y; d->ext_j = d->j; d->ext_prev = d->y_prev; d->ext_has_next = 0;
}

static void emit_peak(f2f_t *d)
{
    int64_t tpd = (int64_t)F2F_TICKS_PER_SAMPLE * d->decim;
    int64_t den = (int64_t)d->ext_prev - 2 * (int64_t)d->ext + (int64_t)d->ext_next;
    int64_t num = (int64_t)d->ext_prev - (int64_t)d->ext_next;
    int64_t off = 0, t;
    if (den != 0) {
        off = (num * tpd) / (2 * den);      /* vertice de la parabola por 3 puntos */
        if (off > tpd / 2) off = tpd / 2;
        if (off < -(tpd / 2)) off = -(tpd / 2);
    }
    /* y[j] = b[j] + b[j-1] cubre las muestras (j-1)M .. (j+1)M-1: centro jM - 0.5 */
    t = tpd * (int64_t)d->ext_j - F2F_TICKS_PER_SAMPLE / 2 + off;

    if (d->have_last_peak) {
        int32_t pp = d->ext - d->last_peak;
        if (pp < 0) pp = -pp;
        if (pp > d->env) d->env += (pp - d->env) >> 1;   /* ataque rapido */
        else             d->env -= (d->env - pp) >> 3;   /* caida lenta */
    }
    d->last_peak = d->ext;
    d->have_last_peak = 1;
    d->last_gap = d->since_peak;
    d->since_peak = 0;

    bits_feed(d, t);
    if (d->tlog_n < d->tlog_cap) {
        if (d->tlog_t) d->tlog_t[d->tlog_n] = t;
        if (d->tlog_v) d->tlog_v[d->tlog_n] = d->ext;
        if (d->tlog_p) d->tlog_p[d->tlog_n] = d->locked ? d->period : 0;
        d->tlog_n++;
    }
}

static void process_y(f2f_t *d, int32_t y)
{
    int32_t h = (int32_t)(((int64_t)d->cfg.thr_frac_q8 * d->env) >> 8);
    int32_t fl = d->cfg.noise_floor * 2 * (int32_t)d->decim;
    uint32_t tmo;
    if (h < fl) h = fl;

    /* Si no llegan picos durante mucho tiempo (p. ej. tras un transitorio que
     * inflo la envolvente) se deja caer la envolvente para no quedar sordo. */
    d->since_peak++;
    tmo = 8 * d->last_gap;
    if (tmo < 64) tmo = 64;
    if (d->since_peak >= tmo && (d->since_peak % tmo) == 0) d->env -= d->env >> 2;

    if (d->state == 0) {
        if (!d->have_y) { d->init_min = d->init_max = y; d->y_prev = y; d->have_y = 1; }
        if (y < d->init_min) d->init_min = y;
        if (y > d->init_max) d->init_max = y;
        if (y - d->init_min >= h)      { d->state = 1;  set_ext(d, y); }
        else if (d->init_max - y >= h) { d->state = -1; set_ext(d, y); }
    } else if (d->state > 0) {
        if (y > d->ext) set_ext(d, y);
        else {
            if (!d->ext_has_next) { d->ext_next = y; d->ext_has_next = 1; }
            if (d->ext - y >= h) { emit_peak(d); d->state = -1; set_ext(d, y); }
        }
    } else {
        if (y < d->ext) set_ext(d, y);
        else {
            if (!d->ext_has_next) { d->ext_next = y; d->ext_has_next = 1; }
            if (y - d->ext >= h) { emit_peak(d); d->state = 1; set_ext(d, y); }
        }
    }
    d->y_prev = y;
}

void f2f_feed_samples(f2f_t *d, const uint16_t *x, size_t n, size_t stride)
{
    size_t i;
    if (stride == 0) stride = 1;
    for (i = 0; i < n; i++) {
        d->acc += (int32_t)(x[i * stride] & 0x0FFF);
        if (++d->acc_n >= d->decim) {
            int32_t b = d->acc;
            d->acc = 0; d->acc_n = 0;
            if (d->have_b) process_y(d, b + d->b_prev);
            d->b_prev = b; d->have_b = 1;
            d->j++;
        }
    }
}

/* ------------------------------------------------------------------ ISO 7811 */

static int status_rank(f2f_status_t s)
{
    switch (s) {
    case F2F_OK: return 5;
    case F2F_LRC_ERR: return 4;
    case F2F_PARITY_ERR: return 3;
    case F2F_NO_END: return 2;
    case F2F_NO_START: return 1;
    default: return 0;
    }
}

int f2f_result_better(const f2f_result_t *a, const f2f_result_t *b)
{
    int ra = status_rank(a->status), rb = status_rank(b->status);
    int sa, sb;
    if (ra != rb) return ra > rb;
    sa = (int)a->n_chars - 2 * (int)a->n_parity_err;
    sb = (int)b->n_chars - 2 * (int)b->n_parity_err;
    if (sa != sb) return sa > sb;
    return a->f2f_errors < b->f2f_errors;    /* a igualdad, la instancia mas limpia */
}

const char *f2f_status_str(f2f_status_t s)
{
    switch (s) {
    case F2F_OK: return "OK";
    case F2F_NO_SIGNAL: return "NO_SIGNAL";
    case F2F_NO_START: return "NO_START";
    case F2F_NO_END: return "NO_END";
    case F2F_PARITY_ERR: return "PARITY_ERR";
    case F2F_LRC_ERR: return "LRC_ERR";
    default: return "?";
    }
}

#define BIT(i) (bits[rev ? (n - 1 - (i)) : (i)])

/* Un formato y un sentido. Recorre todos los candidatos a SS. */
static void decode_one(const uint8_t *bits, const uint32_t *bper, int n, int fmt, int rev,
                       int min_lead, f2f_result_t *best)
{
    const int nb = (fmt == F2F_FMT_T1) ? 7 : 5;
    const int nd = nb - 1;
    const int ss_val = (fmt == F2F_FMT_T1) ? 0x05 : 0x0B;
    const int es_val = (fmt == F2F_FMT_T1) ? 0x1F : 0x0F;
    const int base = (fmt == F2F_FMT_T1) ? 0x20 : 0x30;
    int s, zeros = 0;
    f2f_result_t r;

    for (s = 0; s + nb <= n; s++) {
        int k, val = 0, ones = 0, pos, found_es = 0, lrc = 0, lead = zeros;
        /* 'zeros' = ceros consecutivos justo antes de s */
        if (BIT(s)) zeros = 0; else zeros++;
        if (!BIT(s) || lead < min_lead) continue;
        for (k = 0; k < nb; k++) { if (BIT(s + k)) { ones++; if (k < nd) val |= 1 << k; } }
        if (val != ss_val || !(ones & 1)) continue;

        if (bper) {
            /* Contar como ceros de cabecera solo los de periodo coherente (+-25 %
             * respecto al bit siguiente): descarta bits basura por ruido previo. */
            int i, l2 = 0;
            uint32_t pn = bper[rev ? (n - 1 - s) : s];
            for (i = s - 1; i >= s - lead; i--) {
                uint32_t p = bper[rev ? (n - 1 - i) : i];
                uint32_t df = p > pn ? p - pn : pn - p;
                if ((uint64_t)df * 4 > pn) break;
                l2++; pn = p;
            }
            lead = l2;
        }
        memset(&r, 0, sizeof(r));
        r.fmt = (uint8_t)fmt; r.direction = (uint8_t)rev;
        r.leading_zeros = (uint16_t)lead; r.ss_bit = (uint16_t)s;
        pos = s;
        while (pos + nb <= n && r.n_chars < F2F_MAX_CHARS) {
            val = 0; ones = 0;
            for (k = 0; k < nb; k++) { if (BIT(pos + k)) { ones++; if (k < nd) val |= 1 << k; } }
            if (!(ones & 1)) {
                if (r.n_parity_err < F2F_MAX_PERR) r.parity_pos[r.n_parity_err] = r.n_chars;
                r.n_parity_err++;
            }
            lrc ^= val;
            r.text[r.n_chars++] = (char)(base + val);
            pos += nb;
            if (val == es_val && r.n_chars > 1) { found_es = 1; break; }
        }
        r.text[r.n_chars] = 0;
        if (!found_es || pos + nb > n) {
            r.status = F2F_NO_END;
        } else {
            val = 0; ones = 0;
            for (k = 0; k < nb; k++) { if (BIT(pos + k)) { ones++; if (k < nd) val |= 1 << k; } }
            pos += nb;
            r.lrc_value = (uint8_t)val;
            /* LRC: paridad par por columna sobre SS..ES..LRC; su bit de paridad, impar */
            r.lrc_ok = (uint8_t)((val == lrc) && (ones & 1));
            if (r.n_parity_err) r.status = F2F_PARITY_ERR;
            else r.status = r.lrc_ok ? F2F_OK : F2F_LRC_ERR;
        }
        r.end_bit = (uint16_t)pos;
        if (bper) {
            int i;
            uint32_t mn = 0xFFFFFFFFu, mx = 0;
            for (i = s - lead; i < pos; i++) {
                uint32_t p = bper[rev ? (n - 1 - i) : i];
                if (p < mn) mn = p;
                if (p > mx) mx = p;
            }
            r.period_min = mn; r.period_max = mx;
        }
        if (f2f_result_better(&r, best)) *best = r;
        if (best->status == F2F_OK) return;
    }
}

f2f_status_t f2f_decode_bits(const uint8_t *bits, const uint32_t *bit_period, int n,
                             f2f_fmt_t fmt, int min_lead_zeros, f2f_result_t *res)
{
    int f, rev;
    memset(res, 0, sizeof(*res));
    res->status = F2F_NO_START;
    res->fmt = (uint8_t)fmt;
    for (f = F2F_FMT_T1; f <= F2F_FMT_T2; f++) {
        if (fmt != F2F_FMT_AUTO && (int)fmt != f) continue;
        for (rev = 0; rev <= 1; rev++) {
            decode_one(bits, bit_period, n, f, rev, min_lead_zeros, res);
            if (res->status == F2F_OK) goto done;
        }
    }
done:
    res->n_bits = (uint16_t)n;
    return res->status;
}

f2f_status_t f2f_finish(const f2f_t *d, f2f_fmt_t fmt, f2f_result_t *res)
{
    if ((int32_t)d->n_trans < d->cfg.min_transitions) {
        memset(res, 0, sizeof(*res));
        res->status = F2F_NO_SIGNAL;
        res->fmt = (uint8_t)fmt;
    } else {
        f2f_decode_bits(d->bits, d->bit_period, d->n_bits, fmt, d->cfg.min_lead_zeros, res);
    }
    res->n_bits = d->n_bits;
    res->n_transitions = d->n_trans;
    res->f2f_errors = d->f2f_errors;
    return res->status;
}

/* ------------------------------------------------------------------ multi */

void f2f_multi_init(f2f_multi_t *m, const f2f_cfg_t *cfg, const uint32_t *decims)
{
    static const uint32_t def[F2F_MULTI_N] = { 1, 4, 16, 64 };
    int i;
    if (!decims) decims = def;
    for (i = 0; i < F2F_MULTI_N; i++) f2f_init(&m->inst[i], cfg, decims[i]);
}

void f2f_multi_feed_samples(f2f_multi_t *m, const uint16_t *x, size_t n, size_t stride)
{
    int i;
    for (i = 0; i < F2F_MULTI_N; i++) f2f_feed_samples(&m->inst[i], x, n, stride);
}

f2f_status_t f2f_multi_finish(const f2f_multi_t *m, f2f_fmt_t fmt, f2f_result_t *res)
{
    f2f_result_t r;
    int i;
    for (i = 0; i < F2F_MULTI_N; i++) {
        f2f_finish(&m->inst[i], fmt, &r);
        r.instance = (uint8_t)i;
        if (i == 0 || f2f_result_better(&r, res)) *res = r;
    }
    return res->status;
}
