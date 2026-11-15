/*
 * maghead_capture - Firmware de adquisicion para el banco de pruebas de cabezales
 * lectores (Raspberry Pi Pico 2 / RP2350; compatible con Pico / RP2040).
 *
 * ESTADO: codigo escrito contra la API del Pico SDK pero NO compilado para el
 * objetivo ni probado en hardware (ver ../README.md). Lo probado en host son los
 * modulos portables de ../common (decodificador, tramas, comandos, disparo).
 *
 * Fase 1 - adquisicion cruda:
 *   ADC en round-robin A (GP26/ADC0) / B (GP27/ADC1) -> DMA en ping-pong sobre un
 *   anillo de bloques de 1024 palabras. En paralelo un programa PIO muestrea
 *   GP2..GP5 a la misma cadencia (otro DMA, 4 bits por muestra). El bucle principal
 *   fusiona ambos en palabras de 16 bits y las envia por USB CDC en tramas con
 *   cabecera, numero de secuencia y CRC16 (mh_proto.h).
 *   Los flancos de las barreras opticas se envian ademas como eventos con marca de
 *   tiempo en microsegundos (IRQ de GPIO).
 *
 * Fase 2 - decodificacion en placa (opcional, comando DECODE): en modo disparado
 *   cada pasada se pasa por f2f_decode (ruta ADC y ruta de flancos del comparador)
 *   y al terminar se emite una linea "#DEC ...".
 *
 * Resolucion temporal real:
 *   - muestras ADC: 1 / fs_total por palabra; A y B alternan, B va 1 / fs_total
 *     despues de A (2 us a 500 kS/s). t0_us de cada bloque se calcula a partir del
 *     instante de arranque y del contador de bloques (reloj de muestreo), no de la
 *     hora de la IRQ.
 *   - bits digitales (b12-b14): muestreados por PIO una vez por palabra, es decir con
 *     la misma resolucion 1 / fs_total; el desfase fijo PIO <-> ADC es de hasta ~1
 *     muestra (arranques consecutivos, no simultaneos) y NO esta medido.
 *   - eventos de barrera: time_us_64() en la IRQ de GPIO; resolucion 1 us, latencia
 *     de IRQ de pocos us (no medida).
 *
 * Pines: GP26 canal A, GP27 canal B, GP2 comparador A, GP3 comparador B,
 *        GP4 barrera 1, GP5 barrera 2 (activas a nivel bajo), GP25 LED.
 */
#include <stdio.h>
#include <string.h>

#include "pico/stdlib.h"
#include "pico/stdio_usb.h"
#include "hardware/adc.h"
#include "hardware/clocks.h"
#include "hardware/dma.h"
#include "hardware/gpio.h"
#include "hardware/irq.h"
#include "hardware/pio.h"
#include "hardware/sync.h"

#include "dig_sample.pio.h"
#include "f2f_decode.h"
#include "mh_proto.h"

#define FW_VERSION "maghead_capture 0.1.0"

#define PIN_ADC_A   26
#define PIN_ADC_B   27
#define PIN_DIG0    2      /* GP2..GP5 consecutivos */
#define PIN_GATE1   4
#define PIN_GATE2   5
#ifdef PICO_DEFAULT_LED_PIN
#define PIN_LED     PICO_DEFAULT_LED_PIN
#else
#define PIN_LED     25
#endif

#define BLOCK_WORDS 1024u                 /* palabras ADC por bloque (par) */
#define DIG_WORDS   (BLOCK_WORDS / 8u)    /* palabras PIO de 32 bits por bloque */

/* Anillo de bloques: hace de colchon elastico cuando el USB no da abasto. */
#ifndef MH_RING_BLOCKS
#if PICO_RP2350
#define MH_RING_BLOCKS 128u               /* 262 kB + 66 kB de 520 kB */
#else
#define MH_RING_BLOCKS 48u                /* 98 kB + 25 kB de 264 kB */
#endif
#endif

#ifndef MH_ENABLE_DECODE
#define MH_ENABLE_DECODE 1                /* ~85 kB de RAM para los decodificadores */
#endif

static uint16_t adc_ring[MH_RING_BLOCKS][BLOCK_WORDS];
static uint32_t dig_ring[MH_RING_BLOCKS][DIG_WORDS];
static volatile uint32_t adc_done, dig_done;      /* bloques completados (IRQ) */
static int adc_ch[2], dig_ch[2];
static PIO dig_pio = pio0;
static uint dig_sm, dig_offset;

/* configuracion (comandos) */
static uint32_t cfg_fs_ch = 250000;
static uint8_t  cfg_chan = MH_CHAN_AB;
static int      cfg_trig = 0;
static int32_t  cfg_thr = 150;
static int      cfg_decode = -1;                  /* -1 apagado, si no f2f_fmt_t */
static int      cfg_stream = 1;

/* estado de captura */
static int      running;
static uint32_t fs_total;
static uint64_t t_start_us;
static uint32_t next_blk;                         /* siguiente bloque a examinar */
static uint32_t drop_count;
static int      overflow_pending;
static int      seg_first_pending;
static mh_trig_t trig;
static int32_t  mid[2] = { 2048, 2048 };
static uint32_t ev_seq;

static uint8_t frame[MH_HDR_LEN + 2 * BLOCK_WORDS + 2];

/* cola de eventos de barrera (IRQ -> bucle principal) */
#define EVQ_LEN 32u
typedef struct { uint64_t t_us; uint8_t src, level; } gate_ev_t;
static gate_ev_t evq[EVQ_LEN];
static volatile uint32_t evq_w, evq_r;

#if MH_ENABLE_DECODE
static f2f_multi_t dec_adc[2];
static f2f_t dec_cmp[2];
static int dec_active;
static uint8_t cmp_last[2];
static int64_t cmp_idx[2];
#endif

/* ------------------------------------------------------------------ USB */

static void usb_write(const uint8_t *p, size_t n)
{
    if (!stdio_usb_connected()) return;
    fwrite(p, 1, n, stdout);
    fflush(stdout);
}

/* ------------------------------------------------------------------ IRQ */

static void dma_irq_handler(void)
{
    uint32_t ints = dma_hw->ints0;
    int i;
    for (i = 0; i < 2; i++) {
        if (ints & (1u << adc_ch[i])) {
            dma_hw->ints0 = 1u << adc_ch[i];
            adc_done++;
            /* este canal volvera a dispararse (encadenado) para el bloque adc_done + 1 */
            dma_channel_set_write_addr(adc_ch[i], adc_ring[(adc_done + 1u) % MH_RING_BLOCKS], false);
        }
        if (ints & (1u << dig_ch[i])) {
            dma_hw->ints0 = 1u << dig_ch[i];
            dig_done++;
            dma_channel_set_write_addr(dig_ch[i], dig_ring[(dig_done + 1u) % MH_RING_BLOCKS], false);
        }
    }
}

static void gate_irq(uint gpio, uint32_t events)
{
    uint32_t w = evq_w;
    (void)events;
    if (w - evq_r < EVQ_LEN) {
        gate_ev_t *e = &evq[w % EVQ_LEN];
        e->t_us = time_us_64();
        e->src = (gpio == PIN_GATE1) ? 1 : 2;
        e->level = gpio_get(gpio) ? 0 : 1;        /* activa a nivel bajo: 1 = tarjeta presente */
        evq_w = w + 1;
    }
}

/* ------------------------------------------------------------------ captura */

static void dma_unchain_and_abort(int ch)
{
    /* encadenar el canal consigo mismo = sin encadenamiento, y abortar */
    hw_write_masked(&dma_hw->ch[ch].al1_ctrl, (uint32_t)ch << DMA_CH0_CTRL_TRIG_CHAIN_TO_LSB,
                    DMA_CH0_CTRL_TRIG_CHAIN_TO_BITS);
    dma_channel_abort(ch);
}

static void capture_stop(void)
{
    int i;
    if (!running) return;
    irq_set_enabled(DMA_IRQ_0, false);
    adc_run(false);
    pio_sm_set_enabled(dig_pio, dig_sm, false);
    for (i = 0; i < 2; i++) { dma_unchain_and_abort(adc_ch[i]); dma_unchain_and_abort(dig_ch[i]); }
    adc_fifo_drain();
    pio_sm_clear_fifos(dig_pio, dig_sm);
    running = 0;
    gpio_put(PIN_LED, 0);
}

static void capture_start(void)
{
    int i;
    capture_stop();
    fs_total = cfg_fs_ch * (cfg_chan == MH_CHAN_AB ? 2u : 1u);

    /* ADC */
    adc_select_input(cfg_chan == MH_CHAN_B ? 1 : 0);
    adc_set_round_robin(cfg_chan == MH_CHAN_AB ? 0x03 : 0x00);
    adc_fifo_setup(true, true, 1, false, false);  /* FIFO, DREQ, umbral 1, sin bit de error, 12 bits */
    adc_set_clkdiv((float)clock_get_hz(clk_adc) / (float)fs_total - 1.0f);
    adc_fifo_drain();

    /* PIO: una muestra de GP2..GP5 por palabra ADC */
    pio_sm_set_enabled(dig_pio, dig_sm, false);
    dig_sample_program_init(dig_pio, dig_sm, dig_offset, PIN_DIG0,
                            (float)clock_get_hz(clk_sys) / (float)fs_total);
    pio_sm_clear_fifos(dig_pio, dig_sm);

    /* DMA: dos canales en ping-pong por flujo; cada uno encadena al otro */
    for (i = 0; i < 2; i++) {
        dma_channel_config c = dma_channel_get_default_config(adc_ch[i]);
        channel_config_set_transfer_data_size(&c, DMA_SIZE_16);
        channel_config_set_read_increment(&c, false);
        channel_config_set_write_increment(&c, true);
        channel_config_set_dreq(&c, DREQ_ADC);
        channel_config_set_chain_to(&c, adc_ch[1 - i]);
        dma_channel_configure(adc_ch[i], &c, adc_ring[i], &adc_hw->fifo, BLOCK_WORDS, false);

        c = dma_channel_get_default_config(dig_ch[i]);
        channel_config_set_transfer_data_size(&c, DMA_SIZE_32);
        channel_config_set_read_increment(&c, false);
        channel_config_set_write_increment(&c, true);
        channel_config_set_dreq(&c, pio_get_dreq(dig_pio, dig_sm, false));
        channel_config_set_chain_to(&c, dig_ch[1 - i]);
        dma_channel_configure(dig_ch[i], &c, dig_ring[i], &dig_pio->rxf[dig_sm], DIG_WORDS, false);
    }
    adc_done = dig_done = 0;
    next_blk = 0; drop_count = 0; overflow_pending = 0; seg_first_pending = 0; ev_seq = 0;
    evq_r = evq_w;
    mh_trig_init(&trig, fs_total, BLOCK_WORDS);
#if MH_ENABLE_DECODE
    dec_active = 0;
#endif
    dma_hw->ints0 = (1u << adc_ch[0]) | (1u << adc_ch[1]) | (1u << dig_ch[0]) | (1u << dig_ch[1]);
    irq_set_enabled(DMA_IRQ_0, true);
    dma_channel_start(adc_ch[0]);
    dma_channel_start(dig_ch[0]);

    /* arranque casi simultaneo de PIO y ADC (desfase fijo de pocos us, no medido) */
    t_start_us = time_us_64();
    pio_sm_set_enabled(dig_pio, dig_sm, true);
    adc_run(true);
    running = 1;
    gpio_put(PIN_LED, cfg_trig ? 0 : 1);
}

/* un bloque sigue intacto en el anillo mientras el DMA no haya dado la vuelta */
static inline int block_valid(uint32_t b)
{
    uint32_t done = adc_done < dig_done ? adc_done : dig_done;
    return (uint32_t)(done - b) < MH_RING_BLOCKS - 1u;
}

/* ------------------------------------------------------------------ fase 2 */
#if MH_ENABLE_DECODE
static void decode_begin(void)
{
    int c;
    for (c = 0; c < 2; c++) {
        f2f_multi_init(&dec_adc[c], NULL, NULL);
        f2f_init(&dec_cmp[c], NULL, 1);
        cmp_last[c] = 0xFF;
        cmp_idx[c] = 0;
    }
    dec_active = 1;
}

static void decode_feed(const uint16_t *adc, const uint32_t *dig)
{
    uint32_t i;
    if (cfg_chan == MH_CHAN_AB) {
        f2f_multi_feed_samples(&dec_adc[0], adc, BLOCK_WORDS / 2, 2);
        f2f_multi_feed_samples(&dec_adc[1], adc + 1, BLOCK_WORDS / 2, 2);
    } else {
        f2f_multi_feed_samples(&dec_adc[cfg_chan == MH_CHAN_B], adc, BLOCK_WORDS, 1);
    }
    /* ruta de flancos: nivel del comparador muestreado por PIO; tick = 1 muestra de canal */
    for (i = 0; i < BLOCK_WORDS; i++) {
        uint32_t nib = (dig[i >> 3] >> ((i & 7u) * 4u)) & 0xFu;
        int c = (cfg_chan == MH_CHAN_B) || (cfg_chan == MH_CHAN_AB && (i & 1u));
        uint8_t lv = (nib & (c ? MH_DIG_COMP_B : MH_DIG_COMP_A)) ? 1 : 0;
        if (cmp_last[c] != 0xFF && lv != cmp_last[c]) f2f_feed_edge(&dec_cmp[c], cmp_idx[c]);
        cmp_last[c] = lv;
        cmp_idx[c]++;
    }
}

static void decode_print(char ch, const char *src, const f2f_result_t *r, uint32_t tick_hz)
{
    int i;
    printf("#DEC ch=%c src=%s st=%s fmt=%u dir=%c lz=%u ntr=%lu nbits=%u f2ferr=%lu pmin_us=%lu pmax_us=%lu lrc=%u perr=%u",
           ch, src, f2f_status_str(r->status), r->fmt, r->direction ? 'R' : 'F', r->leading_zeros,
           (unsigned long)r->n_transitions, r->n_bits, (unsigned long)r->f2f_errors,
           (unsigned long)((uint64_t)r->period_min * 1000000u / tick_hz),
           (unsigned long)((uint64_t)r->period_max * 1000000u / tick_hz), r->lrc_ok, r->n_parity_err);
    for (i = 0; i < r->n_parity_err && i < F2F_MAX_PERR; i++) printf("%c%u", i ? ',' : ' ', r->parity_pos[i]);
    printf(" txt=%s\n", r->text);
}

static void decode_end(void)
{
    static f2f_result_t r;
    int c;
    f2f_fmt_t fmt = (f2f_fmt_t)cfg_decode;
    if (!dec_active) return;
    dec_active = 0;
    for (c = 0; c < 2; c++) {
        if ((c == 0 && cfg_chan == MH_CHAN_B) || (c == 1 && cfg_chan == MH_CHAN_A)) continue;
        f2f_multi_finish(&dec_adc[c], fmt, &r);
        decode_print((char)('A' + c), "adc", &r, cfg_fs_ch * F2F_TICKS_PER_SAMPLE);
        f2f_finish(&dec_cmp[c], fmt, &r);
        decode_print((char)('A' + c), "cmp", &r, cfg_fs_ch);
    }
    fflush(stdout);
}
#endif

/* ------------------------------------------------------------------ envio */

static void send_block(uint32_t b, uint8_t flags)
{
    const uint16_t *adc = adc_ring[b % MH_RING_BLOCKS];
    const uint32_t *dig = dig_ring[b % MH_RING_BLOCKS];
    mh_hdr_t h;
    size_t len;

    memset(&h, 0, sizeof(h));
    if (cfg_trig) flags |= MH_FLAG_TRIGGERED;
    if (seg_first_pending) { flags |= MH_FLAG_SEG_FIRST; seg_first_pending = 0; }
    if (overflow_pending) { flags |= MH_FLAG_OVERFLOW; overflow_pending = 0; }
    h.flags = flags;
    h.chan_mode = cfg_chan;
    h.seq = b;
    h.fs_total_hz = fs_total;
    h.t0_us = t_start_us + (uint64_t)b * BLOCK_WORDS * 1000000ull / fs_total;
    h.drop_count = drop_count;
    len = mh_build_sample_frame(frame, &h, adc, dig, BLOCK_WORDS);
#if MH_ENABLE_DECODE
    if (dec_active) decode_feed(adc, dig);
#endif
    if (!block_valid(b)) {                 /* el DMA lo piso mientras se copiaba: descartar */
        drop_count++;
        overflow_pending = 1;
        return;
    }
    if (cfg_stream) usb_write(frame, len);
}

static void send_events(void)
{
    uint8_t ev[8 * MH_EVENT_LEN];
    uint8_t buf[MH_HDR_LEN + sizeof(ev) + 2];
    uint16_t n = 0;
    mh_hdr_t h;
    while (evq_r != evq_w && n < 8) {
        const gate_ev_t *e = &evq[evq_r % EVQ_LEN];
        mh_pack_event(ev + n * MH_EVENT_LEN, e->t_us, e->src, e->level);
        evq_r++;
        n++;
    }
    if (!n) return;
    memset(&h, 0, sizeof(h));
    h.chan_mode = cfg_chan;
    h.seq = ev_seq++;
    h.fs_total_hz = fs_total;
    h.t0_us = t_start_us;
    h.drop_count = drop_count;
    usb_write(buf, mh_build_event_frame(buf, &h, ev, n));
}

static void process_blocks(void)
{
    uint32_t done = adc_done < dig_done ? adc_done : dig_done;
    uint32_t b;
    int32_t mean[2];
    int act, st, c;

    /* El productor ha dado la vuelta al consumidor: bloques perdidos. Se salta hasta
     * dejar medio anillo de margen y se marca la siguiente trama con OVERFLOW; ademas
     * el hueco se ve en el numero de secuencia. */
    if ((uint32_t)(done - next_blk) > MH_RING_BLOCKS - 2u) {
        uint32_t skip = (done - next_blk) - MH_RING_BLOCKS / 2u;
        next_blk += skip;
        drop_count += skip;
        overflow_pending = 1;
    }
    if (next_blk == done) return;
    b = next_blk++;

    if (!cfg_trig) { send_block(b, 0); return; }

    act = mh_block_activity(adc_ring[b % MH_RING_BLOCKS], dig_ring[b % MH_RING_BLOCKS],
                            BLOCK_WORDS, cfg_chan, mid, cfg_thr, mean);
    st = mh_trig_step(&trig, act);
    switch (st) {
    case MH_TRIG_IDLE:
        for (c = 0; c < 2; c++) mid[c] += (mean[c] - mid[c]) / 8;   /* linea base, solo en reposo */
        break;
    case MH_TRIG_START: {
        uint32_t k = (b >= trig.pre_blocks) ? b - trig.pre_blocks : 0;
        while (k < b && !block_valid(k)) k++;                       /* pre-disparo aun disponible */
        gpio_put(PIN_LED, 1);
        seg_first_pending = 1;
#if MH_ENABLE_DECODE
        if (cfg_decode >= 0) decode_begin();
#endif
        for (; k < b; k++) send_block(k, 0);
        send_block(b, 0);
        break;
    }
    case MH_TRIG_SEND:
        send_block(b, 0);
        break;
    case MH_TRIG_LAST:
        send_block(b, MH_FLAG_SEG_LAST);
#if MH_ENABLE_DECODE
        decode_end();
#endif
        gpio_put(PIN_LED, 0);
        break;
    default:
        break;
    }
}

/* ------------------------------------------------------------------ comandos */

static void print_status(void)
{
    printf("#STATUS run=%d rate_ch=%lu chan=%s trig=%d thr=%ld decode=%d stream=%d blocks=%lu drops=%lu ring=%u\n",
           running, (unsigned long)cfg_fs_ch,
           cfg_chan == MH_CHAN_AB ? "AB" : (cfg_chan == MH_CHAN_A ? "A" : "B"),
           cfg_trig, (long)cfg_thr, cfg_decode, cfg_stream,
           (unsigned long)adc_done, (unsigned long)drop_count, (unsigned)MH_RING_BLOCKS);
}

static void handle_line(const char *line)
{
    mh_cmd_t c;
    switch (mh_parse_cmd(line, &c)) {
    case MH_CMD_NONE: return;
    case MH_CMD_START: capture_start(); printf("#OK START\n"); break;
    case MH_CMD_STOP: capture_stop(); printf("#OK STOP\n"); break;
    case MH_CMD_RATE:
        if (running) { printf("#ERR STOP primero\n"); break; }
        if (!mh_rate_valid((uint32_t)c.arg * (cfg_chan == MH_CHAN_AB ? 2u : 1u))) {
            printf("#ERR RATE: total admitido 50k/100k/125k/200k/250k/500k\n"); break;
        }
        cfg_fs_ch = (uint32_t)c.arg; printf("#OK RATE %lu\n", (unsigned long)cfg_fs_ch); break;
    case MH_CMD_CHAN:
        if (running) { printf("#ERR STOP primero\n"); break; }
        if (!mh_rate_valid(cfg_fs_ch * (c.arg == MH_CHAN_AB ? 2u : 1u))) {
            printf("#ERR CHAN: cambie RATE antes (total > 500k o no admitido)\n"); break;
        }
        cfg_chan = (uint8_t)c.arg; printf("#OK CHAN\n"); break;
    case MH_CMD_TRIG:
        if (running) { printf("#ERR STOP primero\n"); break; }
        cfg_trig = c.arg; printf("#OK TRIG %d\n", cfg_trig); break;
    case MH_CMD_THR: cfg_thr = c.arg; printf("#OK THR %ld\n", (long)cfg_thr); break;
    case MH_CMD_DECODE:
#if MH_ENABLE_DECODE
        if (running) { printf("#ERR STOP primero\n"); break; }
        cfg_decode = c.arg; printf("#OK DECODE %d\n", cfg_decode);
#else
        printf("#ERR DECODE no compilado\n");
#endif
        break;
    case MH_CMD_STREAM: cfg_stream = c.arg; printf("#OK STREAM %d\n", cfg_stream); break;
    case MH_CMD_STATUS: print_status(); break;
    case MH_CMD_VER: printf("#VER %s\n", FW_VERSION); break;
    case MH_CMD_HELP:
        printf("#HELP START|STOP|RATE <Hz/canal>|CHAN AB|A|B|TRIG ON|OFF|THR <cuentas>|"
               "DECODE OFF|AUTO|T1|T2|STREAM ON|OFF|STATUS|VER\n");
        break;
    default: printf("#ERR comando\n"); break;
    }
    fflush(stdout);
}

static void poll_commands(void)
{
    static char line[64];
    static unsigned n;
    int ch;
    while ((ch = getchar_timeout_us(0)) != PICO_ERROR_TIMEOUT) {
        if (ch == '\n' || ch == '\r') {
            line[n] = 0;
            n = 0;
            handle_line(line);
        } else if (n < sizeof(line) - 1) {
            line[n++] = (char)ch;
        }
    }
}

/* ------------------------------------------------------------------ main */

int main(void)
{
    int i;
    stdio_init_all();
    stdio_set_translate_crlf(&stdio_usb, false);   /* flujo binario: sin traduccion LF -> CRLF */

    gpio_init(PIN_LED);
    gpio_set_dir(PIN_LED, GPIO_OUT);
    for (i = 0; i < 4; i++) {
        gpio_init(PIN_DIG0 + i);
        gpio_set_dir(PIN_DIG0 + i, GPIO_IN);
    }
    gpio_pull_up(PIN_GATE1);                        /* barreras de colector abierto */
    gpio_pull_up(PIN_GATE2);
    gpio_set_irq_enabled_with_callback(PIN_GATE1, GPIO_IRQ_EDGE_RISE | GPIO_IRQ_EDGE_FALL, true, &gate_irq);
    gpio_set_irq_enabled(PIN_GATE2, GPIO_IRQ_EDGE_RISE | GPIO_IRQ_EDGE_FALL, true);

    adc_init();
    adc_gpio_init(PIN_ADC_A);
    adc_gpio_init(PIN_ADC_B);

    dig_sm = (uint)pio_claim_unused_sm(dig_pio, true);
    dig_offset = (uint)pio_add_program(dig_pio, &dig_sample_program);

    for (i = 0; i < 2; i++) {
        adc_ch[i] = dma_claim_unused_channel(true);
        dig_ch[i] = dma_claim_unused_channel(true);
    }
    dma_set_irq0_channel_mask_enabled((1u << adc_ch[0]) | (1u << adc_ch[1]) |
                                      (1u << dig_ch[0]) | (1u << dig_ch[1]), true);
    irq_set_exclusive_handler(DMA_IRQ_0, dma_irq_handler);

    for (;;) {
        poll_commands();
        if (!running) { sleep_ms(1); continue; }
        if (!cfg_trig || trig.active) send_events();
        else evq_r = evq_w;                         /* en reposo los eventos antiguos no interesan */
        process_blocks();
    }
}
