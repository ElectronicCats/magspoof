/*
 * pico_stub.h - Prototipos MINIMOS del Pico SDK escritos a mano (de memoria) para poder
 * pasar a main.c una comprobacion de SINTAXIS Y TIPOS en el host (make -C .. syntax).
 * NO es el SDK: que main.c compile contra esto no demuestra que compile ni funcione
 * contra el SDK real.
 */
#ifndef PICO_STUB_H
#define PICO_STUB_H
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
typedef unsigned int uint;
#define PICO_ERROR_TIMEOUT (-1)
#define GPIO_OUT 1
#define GPIO_IN 0
#define GPIO_IRQ_EDGE_FALL 0x4u
#define GPIO_IRQ_EDGE_RISE 0x8u
typedef void (*gpio_irq_callback_t)(uint gpio, uint32_t events);
typedef struct { int dummy; } stdio_driver_t;
extern stdio_driver_t stdio_usb;
bool stdio_init_all(void);
void stdio_set_translate_crlf(stdio_driver_t *d, bool en);
bool stdio_usb_connected(void);
int getchar_timeout_us(uint32_t us);
void sleep_ms(uint32_t ms);
uint64_t time_us_64(void);
void gpio_init(uint g); void gpio_set_dir(uint g, bool out); void gpio_put(uint g, bool v);
bool gpio_get(uint g); void gpio_pull_up(uint g);
void gpio_set_irq_enabled_with_callback(uint g, uint32_t ev, bool en, gpio_irq_callback_t cb);
void gpio_set_irq_enabled(uint g, uint32_t ev, bool en);
/* adc */
typedef struct { volatile uint32_t fifo; } adc_hw_t;
extern adc_hw_t *adc_hw;
void adc_init(void); void adc_gpio_init(uint g); void adc_select_input(uint i);
void adc_set_round_robin(uint mask); void adc_fifo_setup(bool en, bool dreq, uint16_t thr, bool err, bool shift);
void adc_set_clkdiv(float d); void adc_fifo_drain(void); void adc_run(bool r);
/* clocks */
enum clock_index { clk_sys, clk_adc };
uint32_t clock_get_hz(enum clock_index c);
/* dma */
typedef struct { uint32_t ctrl; } dma_channel_config;
typedef struct { volatile uint32_t al1_ctrl; } dma_channel_hw_t;
typedef struct { dma_channel_hw_t ch[16]; volatile uint32_t ints0; } dma_hw_t;
extern dma_hw_t *dma_hw;
#define DMA_SIZE_16 1
#define DMA_SIZE_32 2
#define DREQ_ADC 36
#define DMA_IRQ_0 11
#define DMA_CH0_CTRL_TRIG_CHAIN_TO_LSB 11
#define DMA_CH0_CTRL_TRIG_CHAIN_TO_BITS 0x00007800u
int dma_claim_unused_channel(bool required);
dma_channel_config dma_channel_get_default_config(uint ch);
void channel_config_set_transfer_data_size(dma_channel_config *c, int size);
void channel_config_set_read_increment(dma_channel_config *c, bool incr);
void channel_config_set_write_increment(dma_channel_config *c, bool incr);
void channel_config_set_dreq(dma_channel_config *c, uint dreq);
void channel_config_set_chain_to(dma_channel_config *c, uint chain_to);
void dma_channel_configure(uint ch, const dma_channel_config *c, volatile void *w, const volatile void *r, uint n, bool trig);
void dma_channel_set_write_addr(uint ch, volatile void *w, bool trig);
void dma_channel_start(uint ch); void dma_channel_abort(uint ch);
void dma_set_irq0_channel_mask_enabled(uint32_t mask, bool en);
void hw_write_masked(volatile uint32_t *addr, uint32_t values, uint32_t mask);
/* irq */
typedef void (*irq_handler_t)(void);
void irq_set_exclusive_handler(uint num, irq_handler_t h); void irq_set_enabled(uint num, bool en);
/* pio */
typedef struct { volatile uint32_t rxf[4]; } pio_hw_t;
typedef pio_hw_t *PIO;
extern pio_hw_t pio0_hw_stub;
#define pio0 (&pio0_hw_stub)
typedef struct { uint32_t x; } pio_sm_config;
typedef struct { const uint16_t *instructions; uint8_t length; int8_t origin; } pio_program_t;
enum pio_fifo_join { PIO_FIFO_JOIN_NONE, PIO_FIFO_JOIN_TX, PIO_FIFO_JOIN_RX };
int pio_claim_unused_sm(PIO pio, bool required); int pio_add_program(PIO pio, const pio_program_t *p);
void pio_sm_set_enabled(PIO pio, uint sm, bool en); void pio_sm_clear_fifos(PIO pio, uint sm);
uint pio_get_dreq(PIO pio, uint sm, bool is_tx);
void sm_config_set_in_pins(pio_sm_config *c, uint base);
void sm_config_set_in_shift(pio_sm_config *c, bool right, bool autopush, uint thr);
void sm_config_set_fifo_join(pio_sm_config *c, enum pio_fifo_join j);
void sm_config_set_clkdiv(pio_sm_config *c, float div);
void pio_sm_set_consecutive_pindirs(PIO pio, uint sm, uint base, uint count, bool out);
void pio_sm_init(PIO pio, uint sm, uint offset, const pio_sm_config *c);
#endif
