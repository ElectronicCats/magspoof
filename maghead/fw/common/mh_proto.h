/*
 * mh_proto.h - Protocolo de tramas USB CDC del firmware maghead_capture (portable).
 *
 * Todo little-endian. Una trama:
 *   off  tam  campo
 *    0    4   magic        "MHB1" (0x4D 0x48 0x42 0x31)
 *    4    1   type         1 = MUESTRAS, 2 = EVENTOS (flancos de barrera)
 *    5    1   flags        ver MH_FLAG_*
 *    6    1   chan_mode    0 = A/B alternados, 1 = solo A, 2 = solo B
 *    7    1   version      version del protocolo (1)
 *    8    4   seq          MUESTRAS: numero de bloque DMA desde START (un salto = bloques
 *                          perdidos). EVENTOS: contador propio.
 *   12    2   count        numero de palabras de muestra / de eventos
 *   14    2   payload_len  bytes de carga util
 *   16    4   fs_total_hz  palabras por segundo (suma de canales)
 *   20    8   t0_us        marca de tiempo de la primera muestra (us desde arranque)
 *   28    4   drop_count   bloques DMA perdidos acumulados desde START
 *   32    N   payload
 *   32+N  2   crc16        CRC-16/CCITT-FALSE (poli 0x1021, init 0xFFFF) de cabecera+payload
 *
 * Palabra de muestra (16 bits): b0-11 codigo ADC, b12 barrera 1, b13 barrera 2
 * (1 = tarjeta presente), b14 nivel del comparador de ESE canal, b15 canal (0 = A, 1 = B).
 *
 * Evento (12 bytes): u64 t_us, u8 fuente (1 = barrera 1, 2 = barrera 2),
 * u8 nivel (1 = tarjeta presente), u16 reservado.
 *
 * Las respuestas a comandos son lineas ASCII que empiezan por '#' y acaban en '\n',
 * emitidas solo entre tramas.
 */
#ifndef MH_PROTO_H
#define MH_PROTO_H

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

#define MH_MAGIC0 'M'
#define MH_MAGIC1 'H'
#define MH_MAGIC2 'B'
#define MH_MAGIC3 '1'
#define MH_PROTO_VERSION 1
#define MH_HDR_LEN 32
#define MH_EVENT_LEN 12

#define MH_TYPE_SAMPLES 1
#define MH_TYPE_EVENTS  2

#define MH_FLAG_OVERFLOW   0x01  /* se perdieron bloques justo antes de esta trama */
#define MH_FLAG_TRIGGERED  0x02  /* modo disparado */
#define MH_FLAG_SEG_FIRST  0x04  /* primera trama de un segmento disparado (incluye pre-disparo) */
#define MH_FLAG_SEG_LAST   0x08  /* ultima trama del segmento (100 ms de silencio) */
#define MH_FLAG_DIG_BLOCK  0x10  /* bits digitales muestreados una vez por bloque (no por muestra) */

#define MH_CHAN_AB 0
#define MH_CHAN_A  1
#define MH_CHAN_B  2

/* Nibble digital tal como lo muestrea el PIO (GP2..GP5) */
#define MH_DIG_COMP_A 0x1
#define MH_DIG_COMP_B 0x2
#define MH_DIG_GATE1  0x4   /* nivel de pin; barrera activa a nivel bajo */
#define MH_DIG_GATE2  0x8

#define MH_W_GATE1 0x1000
#define MH_W_GATE2 0x2000
#define MH_W_COMP  0x4000
#define MH_W_CHB   0x8000

typedef struct {
    uint8_t  type, flags, chan_mode, version;
    uint32_t seq;
    uint16_t count, payload_len;
    uint32_t fs_total_hz;
    uint64_t t0_us;
    uint32_t drop_count;
} mh_hdr_t;

uint16_t mh_crc16(const uint8_t *p, size_t n, uint16_t crc);
size_t mh_pack_header(uint8_t *out, const mh_hdr_t *h);
int    mh_unpack_header(const uint8_t *in, mh_hdr_t *h);   /* 0 si el magic es correcto */

/* Construye una trama de MUESTRAS completa (cabecera + palabras + CRC) a partir de un
 * bloque ADC y de los nibbles digitales (8 por palabra de 32 bits, el primero en los
 * bits bajos; dig = NULL => bits digitales a 0). Rellena count/payload_len.
 * Devuelve la longitud total. out debe tener MH_HDR_LEN + 2*n_words + 2 bytes. */
size_t mh_build_sample_frame(uint8_t *out, mh_hdr_t *h, const uint16_t *adc,
                             const uint32_t *dig, uint16_t n_words);
size_t mh_build_event_frame(uint8_t *out, mh_hdr_t *h, const uint8_t *events, uint16_t n_events);
void   mh_pack_event(uint8_t *out, uint64_t t_us, uint8_t source, uint8_t level);

/* Actividad de un bloque para el disparo: |muestra - mid[canal]| > thr o alguna barrera
 * activa. Devuelve 1/0 y deja en mean[canal] la media del bloque (para seguir la linea base). */
int mh_block_activity(const uint16_t *adc, const uint32_t *dig, uint16_t n_words,
                      uint8_t chan_mode, const int32_t mid[2], int32_t thr, int32_t mean[2]);

/* Maquina de estados del modo disparado, por bloques. */
#define MH_TRIG_IDLE  0   /* nada que enviar */
#define MH_TRIG_START 1   /* empieza segmento: rebobinar pre_blocks y enviar hasta este bloque */
#define MH_TRIG_SEND  2   /* enviar este bloque */
#define MH_TRIG_LAST  3   /* enviar este bloque marcado como ultimo */
typedef struct {
    uint32_t pre_blocks;    /* ~20 ms */
    uint32_t quiet_blocks;  /* ~100 ms */
    uint32_t quiet;
    int      active;
} mh_trig_t;
void mh_trig_init(mh_trig_t *t, uint32_t fs_total_hz, uint32_t block_words);
int  mh_trig_step(mh_trig_t *t, int activity);

/* Frecuencias totales admitidas (divisores enteros de 48 MHz, 125 MHz y 150 MHz). */
int mh_rate_valid(uint32_t fs_total_hz);

/* Comandos ASCII */
typedef enum {
    MH_CMD_NONE = 0, MH_CMD_START, MH_CMD_STOP, MH_CMD_RATE, MH_CMD_CHAN, MH_CMD_TRIG,
    MH_CMD_THR, MH_CMD_DECODE, MH_CMD_STREAM, MH_CMD_STATUS, MH_CMD_VER, MH_CMD_HELP,
    MH_CMD_ERR
} mh_cmd_id_t;
typedef struct { mh_cmd_id_t id; int32_t arg; } mh_cmd_t;
/* START | STOP | RATE <Hz por canal> | CHAN AB|A|B | TRIG ON|OFF | THR <cuentas> |
 * DECODE OFF|AUTO|T1|T2 | STREAM ON|OFF | STATUS | VER | HELP   (no distingue mayusculas) */
mh_cmd_id_t mh_parse_cmd(const char *line, mh_cmd_t *out);

#ifdef __cplusplus
}
#endif
#endif
