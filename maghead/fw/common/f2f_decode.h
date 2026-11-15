/*
 * f2f_decode.h - Decodificador F2F / ISO 7811 portable (sin dependencias del SDK).
 *
 * Banco de pruebas MagHead: caracterizacion de cabezales LECTORES con tarjetas
 * de laboratorio de contenido sintetico conocido.
 *
 * Cadena (todo en aritmetica entera, apto para RP2040 sin FPU):
 *   muestras ADC -> diezmado (suma de bloques M, ventana 2M) -> detector de picos
 *   de polaridad alternada (histeresis = fraccion de la envolvente pico-pico
 *   seguida, con suelo minimo) -> intervalos -> seguidor de periodo de bit
 *   (IIR acotado) -> bits F2F -> ISO 7811 (pista 1: 7 bits, pistas 2/3: 5 bits),
 *   ambos sentidos de pasada, paridad impar por caracter y LRC.
 *
 * La ruta de flancos (comparador) entra directamente en el seguidor de bits con
 * f2f_feed_edge().
 *
 * Unidades de tiempo ("ticks"): en la ruta de muestras 1 muestra del canal =
 * F2F_TICKS_PER_SAMPLE ticks. En la ruta de flancos el tick es el que use quien
 * llama (p. ej. microsegundos); los periodos se devuelven en esos mismos ticks.
 *
 * La implementacion de referencia en Python (tools/maghead/decode.py) replica
 * este algoritmo entero a entero; tools/tests compara ambas.
 */
#ifndef F2F_DECODE_H
#define F2F_DECODE_H

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

#define F2F_TICKS_PER_SAMPLE 64
#define F2F_MAX_BITS   1024   /* pista 1 completa: 709 celdas a 210 bpi */
#define F2F_MAX_CHARS  112    /* pista 3: 107 caracteres */
#define F2F_MAX_PERR   16     /* posiciones de error de paridad que se guardan */
#ifndef F2F_MULTI_N
#define F2F_MULTI_N    7      /* instancias en paralelo (diezmados 1, 2, 4 ... 64) */
#endif

typedef enum {
    F2F_OK = 0,          /* SS..ES encontrados, paridad y LRC correctos */
    F2F_NO_SIGNAL = 1,   /* menos de cfg.min_transitions transiciones */
    F2F_NO_START = 2,    /* hay transiciones pero no se encontro centinela de inicio */
    F2F_NO_END = 3,      /* SS encontrado pero sin ES (+LRC) antes de acabar los bits */
    F2F_PARITY_ERR = 4,  /* errores de paridad de caracter (n_parity_err, parity_pos) */
    F2F_LRC_ERR = 5      /* paridades bien pero el LRC no cuadra */
} f2f_status_t;

typedef enum {
    F2F_FMT_AUTO = 0,    /* probar los dos formatos */
    F2F_FMT_T1 = 1,      /* 7 bits/caracter (6 datos LSB primero + paridad impar), +0x20, SS '%' */
    F2F_FMT_T2 = 2       /* 5 bits/caracter (4 datos LSB primero + paridad impar), +0x30, SS ';' (pistas 2 y 3) */
} f2f_fmt_t;

#define F2F_DIR_FWD 0
#define F2F_DIR_REV 1

typedef struct {
    int32_t thr_frac_q8;        /* histeresis = thr_frac * envolvente p-p (Q8; 51 = 0.20) */
    int32_t noise_floor;        /* histeresis minima, cuentas ADC pico-pico */
    int32_t class_thr_q8;       /* intervalo < class_thr * P => media celda (Q8; 184 = 0.72) */
    int32_t pair_thr_q8;        /* suma de dos medias <= pair_thr * P => bit 1 (Q8; 320 = 1.25) */
    int32_t period_alpha_shift; /* P += correccion >> shift (2 => alfa 1/4) */
    int32_t period_bound_shift; /* correccion acotada a +-P >> shift (2 => +-25 %) */
    int32_t sync_count;         /* intervalos consecutivos concordantes para enganchar */
    int32_t sync_tol_q8;        /* tolerancia de concordancia (Q8; 51 = 20 %) */
    int32_t min_transitions;    /* por debajo => F2F_NO_SIGNAL */
    int32_t min_lead_zeros;     /* ceros (de periodo coherente) exigidos justo antes del SS */
    int32_t min_seg_bits;       /* tramos enganchados mas cortos se descartan (basura por ruido) */
} f2f_cfg_t;

typedef struct {
    f2f_status_t status;
    uint8_t  fmt;               /* F2F_FMT_T1 / F2F_FMT_T2 del resultado */
    uint8_t  direction;         /* F2F_DIR_FWD: bits en el orden recibido; REV: invertidos */
    uint8_t  lrc_ok;
    uint8_t  instance;          /* instancia (diezmado) elegida por f2f_multi_finish */
    uint32_t n_transitions;
    uint32_t f2f_errors;        /* intervalos imposibles (medio+entero, huecos) */
    uint16_t n_bits;
    uint16_t n_chars;           /* caracteres en text (SS..ES incluidos, sin LRC) */
    uint16_t n_parity_err;
    uint16_t parity_pos[F2F_MAX_PERR]; /* indice de caracter (0 = SS) */
    uint16_t leading_zeros;     /* ceros consecutivos justo antes del SS */
    uint16_t ss_bit;            /* indice del primer bit del SS en el flujo ya orientado */
    uint16_t end_bit;           /* indice del bit siguiente al ultimo decodificado */
    uint8_t  lrc_value;         /* valor de datos del LRC leido */
    uint32_t period_min;        /* periodo de bit min/max en ticks sobre ceros+datos */
    uint32_t period_max;
    char     text[F2F_MAX_CHARS + 1];
} f2f_result_t;

/* Estado de una instancia (tamano aprox. 5.3 kB por F2F_MAX_BITS = 1024). */
typedef struct {
    f2f_cfg_t cfg;
    /* --- diezmado --- */
    uint32_t decim;
    int32_t  acc;
    uint32_t acc_n;
    int32_t  b_prev;
    int      have_b;
    uint32_t j;                 /* indice de bloque diezmado */
    /* --- detector de picos --- */
    int      state;             /* 0 inicial, +1 buscando maximo, -1 buscando minimo */
    int32_t  ext, ext_prev, ext_next;
    uint32_t ext_j;
    int      ext_has_next;
    int32_t  y_prev;
    int      have_y;
    int32_t  init_min, init_max;
    int32_t  last_peak;
    int      have_last_peak;
    int32_t  env;               /* envolvente pico-pico (unidades de y) */
    uint32_t since_peak;
    uint32_t last_gap;          /* muestras diezmadas entre los dos ultimos picos */
    /* --- seguidor de bits --- */
    int64_t  last_t;
    int      have_last;
    uint32_t n_trans;
    int      locked;
    uint32_t period;
    int64_t  sync_sum;
    int32_t  sync_n;
    int      half_pending;
    int64_t  half_iv;
    int32_t  err_level;         /* contador con fuga: +4 por error, -1 por bit bueno */
    uint16_t seg_start;         /* primer bit del tramo enganchado actual */
    uint32_t f2f_errors;
    uint16_t n_bits;
    uint8_t  bits[F2F_MAX_BITS];
    uint32_t bit_period[F2F_MAX_BITS];
    /* --- registro opcional de transiciones (analisis en host) --- */
    int64_t *tlog_t;            /* tiempo del pico, ticks */
    int32_t *tlog_v;            /* valor del pico (suma de 2M muestras) */
    uint32_t *tlog_p;           /* periodo seguido tras procesar la transicion (0 = sin enganche) */
    uint32_t tlog_cap, tlog_n;
} f2f_t;

typedef struct {
    f2f_t inst[F2F_MULTI_N];
} f2f_multi_t;

void f2f_cfg_default(f2f_cfg_t *cfg);
void f2f_init(f2f_t *d, const f2f_cfg_t *cfg, uint32_t decim);
void f2f_set_log(f2f_t *d, int64_t *t, int32_t *v, uint32_t *p, uint32_t cap);

/* Muestras ADC (se enmascaran a 12 bits, asi que valen las palabras del firmware).
 * stride permite recorrer un buffer A/B intercalado (stride = 2). */
void f2f_feed_samples(f2f_t *d, const uint16_t *x, size_t n, size_t stride);
/* Flanco del comparador (cualquier sentido), tiempo en ticks del usuario. */
void f2f_feed_edge(f2f_t *d, int64_t t_ticks);
f2f_status_t f2f_finish(const f2f_t *d, f2f_fmt_t fmt, f2f_result_t *res);

/* Varias instancias en paralelo (diezmados por defecto 1, 2, 4 ... 2^(N-1)) para cubrir
 * 0.05 - 1.5 m/s sin conocer la velocidad; coste total < 2x una instancia. */
void f2f_multi_init(f2f_multi_t *m, const f2f_cfg_t *cfg, const uint32_t *decims);
void f2f_multi_feed_samples(f2f_multi_t *m, const uint16_t *x, size_t n, size_t stride);
f2f_status_t f2f_multi_finish(const f2f_multi_t *m, f2f_fmt_t fmt, f2f_result_t *res);

/* Solo la capa ISO 7811: bits -> caracteres, ambos sentidos. bit_period puede ser NULL. */
f2f_status_t f2f_decode_bits(const uint8_t *bits, const uint32_t *bit_period, int n,
                             f2f_fmt_t fmt, int min_lead_zeros, f2f_result_t *res);

/* Orden de preferencia entre resultados (1 si a es mejor que b). */
int f2f_result_better(const f2f_result_t *a, const f2f_result_t *b);
const char *f2f_status_str(f2f_status_t s);

#ifdef __cplusplus
}
#endif
#endif /* F2F_DECODE_H */
