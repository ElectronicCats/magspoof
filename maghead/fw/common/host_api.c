/*
 * host_api.c - Envoltorio SOLO PARA HOST (usa malloc) para llamar al decodificador
 * desde Python (ctypes) y desde test_host. No forma parte del firmware.
 */
#include "f2f_decode.h"
#include <stdlib.h>
#include <string.h>

/* Ejecuta el decodificador multi-instancia sobre un vector de muestras y devuelve,
 * ademas del resultado, el registro de transiciones y los bits de la instancia elegida.
 * decims = NULL => {1, 4, 16, 64}. Devuelve el estado, o -1 si falta memoria. */
int f2f_host_run(const uint16_t *x, size_t n, int fmt, const f2f_cfg_t *cfg,
                 const uint32_t *decims, f2f_result_t *res,
                 int64_t *tlog, int32_t *vlog, uint32_t *plog, uint32_t cap, uint32_t *n_tlog,
                 uint8_t *bits, uint32_t *bper, uint32_t *n_bits)
{
    f2f_multi_t *m = (f2f_multi_t *)malloc(sizeof(*m));
    int64_t *lt[F2F_MULTI_N]; int32_t *lv[F2F_MULTI_N]; uint32_t *lp[F2F_MULTI_N];
    int i, ok = 1;
    if (!m) return -1;
    f2f_multi_init(m, cfg, decims);
    for (i = 0; i < F2F_MULTI_N; i++) {
        lt[i] = (int64_t *)malloc(sizeof(int64_t) * (cap ? cap : 1));
        lv[i] = (int32_t *)malloc(sizeof(int32_t) * (cap ? cap : 1));
        lp[i] = (uint32_t *)malloc(sizeof(uint32_t) * (cap ? cap : 1));
        if (!lt[i] || !lv[i] || !lp[i]) ok = 0;
    }
    if (ok) {
        const f2f_t *d;
        for (i = 0; i < F2F_MULTI_N; i++) f2f_set_log(&m->inst[i], lt[i], lv[i], lp[i], cap);
        f2f_multi_feed_samples(m, x, n, 1);
        f2f_multi_finish(m, (f2f_fmt_t)fmt, res);
        d = &m->inst[res->instance];
        if (n_tlog) *n_tlog = d->tlog_n;
        if (tlog) memcpy(tlog, lt[res->instance], sizeof(int64_t) * d->tlog_n);
        if (vlog) memcpy(vlog, lv[res->instance], sizeof(int32_t) * d->tlog_n);
        if (plog) memcpy(plog, lp[res->instance], sizeof(uint32_t) * d->tlog_n);
        if (n_bits) *n_bits = d->n_bits;
        if (bits) memcpy(bits, d->bits, d->n_bits);
        if (bper) memcpy(bper, d->bit_period, sizeof(uint32_t) * d->n_bits);
    }
    for (i = 0; i < F2F_MULTI_N; i++) { free(lt[i]); free(lv[i]); free(lp[i]); }
    free(m);
    return ok ? (int)res->status : -1;
}

/* Ruta de flancos: marcas de tiempo -> resultado. */
int f2f_host_run_edges(const int64_t *t, size_t n, int fmt, const f2f_cfg_t *cfg,
                       f2f_result_t *res, uint8_t *bits, uint32_t *n_bits)
{
    f2f_t *d = (f2f_t *)malloc(sizeof(*d));
    size_t i;
    if (!d) return -1;
    f2f_init(d, cfg, 1);
    for (i = 0; i < n; i++) f2f_feed_edge(d, t[i]);
    f2f_finish(d, (f2f_fmt_t)fmt, res);
    if (n_bits) *n_bits = d->n_bits;
    if (bits) memcpy(bits, d->bits, d->n_bits);
    free(d);
    return (int)res->status;
}

size_t f2f_host_sizeof_result(void) { return sizeof(f2f_result_t); }
size_t f2f_host_sizeof_cfg(void) { return sizeof(f2f_cfg_t); }
