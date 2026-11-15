/* Sustituto para la comprobacion de sintaxis: lo que generaria pioasm a partir de
 * ../dig_sample.pio (escrito a mano; el real lo genera pico_generate_pio_header). */
#include "pico_stub.h"
static const uint16_t dig_sample_program_instructions[] = { 0x4004 /* in pins, 4 */ };
static const pio_program_t dig_sample_program = { dig_sample_program_instructions, 1, -1 };
static inline pio_sm_config dig_sample_program_get_default_config(uint offset) { pio_sm_config c = { offset }; return c; }
static inline void dig_sample_program_init(PIO pio, uint sm, uint offset, uint pin_base, float clkdiv) {
    pio_sm_config c = dig_sample_program_get_default_config(offset);
    sm_config_set_in_pins(&c, pin_base);
    sm_config_set_in_shift(&c, true, true, 32);
    sm_config_set_fifo_join(&c, PIO_FIFO_JOIN_RX);
    sm_config_set_clkdiv(&c, clkdiv);
    pio_sm_set_consecutive_pindirs(pio, sm, pin_base, 4, false);
    pio_sm_init(pio, sm, offset, &c);
}
