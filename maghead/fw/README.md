# Firmware MagHead (banco de pruebas de cabezales lectores)

Instrumentacion de laboratorio: adquisicion de la senal de cabezales LECTORES experimentales
con tarjetas ISO 7811 de laboratorio de contenido sintetico conocido.

```
fw/
  common/            modulos PORTABLES (C99, sin SDK) + pruebas en host
    f2f_decode.[ch]    decodificador F2F / ISO 7811 (fase 2)
    mh_proto.[ch]      tramas USB, CRC16, comandos ASCII, maquina de disparo
    host_api.c         envoltorio solo-host (malloc) para ctypes / test_host
    test_host.c        arnes de pruebas en host
    Makefile           make | make test | make asan | make syntax
  maghead_capture/   firmware Pico SDK (fase 1 + fase 2 opcional)
    main.c  dig_sample.pio  CMakeLists.txt
    host_stub/         prototipos del SDK escritos a mano, SOLO para comprobar sintaxis
```

## Estado real (leer antes de fiarse de nada)

| Parte | Estado |
|---|---|
| `common/f2f_decode.c`, `common/mh_proto.c` | Compilados con gcc en host (`-Wall -Wextra -Wconversion -Werror`), pruebas unitarias propias (`make test`: 125 comprobaciones), tambien bajo ASan/UBSan (`make asan`), y comparados bit a bit con la referencia Python sobre vectores sinteticos (`tools/tests/test_c_decoder.py`). |
| `maghead_capture/main.c`, `dig_sample.pio` | **Compilados sin errores ni advertencias** contra pico-sdk (commit 079c6f3, TinyUSB 86ad6e5) con arm-none-eabi-gcc 13.2, para `pico2` (RP2350: 50.6 kB de codigo, 419 kB de RAM estatica) y `pico` (RP2040: 54.6 kB, 215 kB de 264 kB). Binarios en `prebuilt/`. **NO probados en hardware**: temporizacion ADC/PIO, caudal USB y comportamiento real sin verificar. |
| Caudal USB, temporizacion del ADC, alineacion PIO/ADC, perdida de bloques, carga de CPU de la fase 2 | **No medidos.** Ver "Limites esperados". |

La primera sesion con hardware debe empezar por: compilar, comprobar `VER`/`STATUS`, capturar un
generador de funciones (seno de 1 kHz) y verificar frecuencia de muestreo, orden A/B, ausencia de
saltos de `seq` y alineacion de los bits digitales con el analogico.

## Compilar (cuando haya SDK)

```
export PICO_SDK_PATH=/ruta/a/pico-sdk            # SDK >= 2.0 para RP2350
cd fw/maghead_capture
# pico_sdk_import.cmake ya esta incluido en maghead_capture/
cmake -B build -DPICO_BOARD=pico2 && cmake --build build     # Pico 2 (RP2350)
cmake -B build -DPICO_BOARD=pico  && cmake --build build     # Pico (RP2040)
```

`MH_RING_BLOCKS` (bloques del anillo: 128 en RP2350, 48 en RP2040) y `MH_ENABLE_DECODE`
(fase 2, ~85 kB de RAM) son macros de compilacion.

## Hardware

| Pin | Funcion |
|---|---|
| GP26 / ADC0 | canal A: cabezal bajo prueba (salida del AFE, centrada en 1.65 V, banda 16 Hz - 40 kHz) |
| GP27 / ADC1 | canal B: cabezal de referencia o segundo cabezal |
| GP2, GP3 | comparadores A y B (F2F digital, comparador con histeresis) |
| GP4, GP5 | barreras opticas 1 y 2 (tarjeta presente = nivel bajo; separadas 20.00 mm; pull-up interno activado) |
| GP25 | LED: encendido mientras se transmite |

## Fase 1: adquisicion

* ADC en round-robin A/B, DMA en ping-pong (dos canales encadenados) sobre un anillo de bloques
  de 1024 palabras. Por defecto 250 kS/s por canal (500 kS/s en total).
* Frecuencias admitidas (total = por canal x n. de canales): 500k, 250k, 200k, 125k, 100k, 50k.
  Con `CHAN A` o `CHAN B`, un solo canal hasta 500 kS/s. Solo se admiten esas porque dan
  divisores enteros de 48 MHz (ADC) y de 125/150 MHz (PIO): asi el muestreo digital no deriva
  respecto al analogico.
* Bits digitales: un programa PIO muestrea GP2..GP5 una vez por palabra ADC (otro DMA) y el bucle
  principal los fusiona en la palabra de 16 bits:
  `b0-11` codigo ADC, `b12` barrera 1, `b13` barrera 2 (1 = tarjeta presente),
  `b14` nivel del comparador de ese canal, `b15` canal (0 = A, 1 = B).
* **Resolucion temporal real**: analogico y digitales, 1/fs_total por palabra (2 us a 500 kS/s);
  B se muestrea 1/fs_total despues de A. El desfase fijo PIO-ADC (arranques consecutivos) es de
  hasta ~1 muestra y no esta medido. Los **flancos de barrera** se envian ademas como eventos
  con marca `time_us_64()` (1 us de resolucion, latencia de IRQ de pocos us, no medida): la
  velocidad media debe calcularse con esos eventos.
* `t0_us` de cada bloque = instante de arranque + n. de bloque x duracion de bloque (reloj de
  muestreo), en la misma base de tiempos que los eventos.

### Trama (little-endian) - definicion completa en `common/mh_proto.h`

| Off | Tam | Campo |
|---|---|---|
| 0 | 4 | magic `"MHB1"` |
| 4 | 1 | tipo: 1 = muestras, 2 = eventos de barrera |
| 5 | 1 | flags: 0x01 OVERFLOW (se perdieron bloques justo antes), 0x02 modo disparado, 0x04 primera trama del segmento, 0x08 ultima trama del segmento |
| 6 | 1 | modo de canales: 0 = A/B alternados, 1 = solo A, 2 = solo B |
| 7 | 1 | version de protocolo (1) |
| 8 | 4 | `seq`: numero de bloque DMA desde START (un salto = bloques perdidos) |
| 12 | 2 | numero de palabras (o de eventos) |
| 14 | 2 | bytes de carga util |
| 16 | 4 | frecuencia total, palabras/s |
| 20 | 8 | `t0_us`: marca de tiempo de la primera muestra |
| 28 | 4 | bloques perdidos acumulados |
| 32 | N | carga util: palabras de 16 bits, o eventos de 12 bytes (u64 t_us, u8 barrera, u8 nivel, u16 0) |
| 32+N | 2 | CRC-16/CCITT-FALSE (poli 0x1021, init 0xFFFF) de cabecera + carga |

Bloques perdidos: se detectan cuando el DMA da la vuelta al anillo antes de que el bucle
principal envie el bloque. Se senalan por triplicado: salto en `seq`, flag OVERFLOW en la trama
siguiente y contador `drop_count`. El PC (`tools/maghead/capture.py`) rellena el hueco con el
valor medio, conserva la base de tiempos y lo anota en los metadatos.

### Comandos ASCII (misma CDC, terminados en LF; respuestas `#...`)

| Comando | Efecto |
|---|---|
| `START` / `STOP` | arranca / para la captura |
| `RATE <Hz>` | frecuencia POR CANAL (parado) |
| `CHAN AB\|A\|B` | modo de canales (parado) |
| `TRIG ON\|OFF` | modo disparado (parado) |
| `THR <cuentas>` | umbral de disparo sobre \|muestra - linea base\| (defecto 150) |
| `DECODE OFF\|AUTO\|T1\|T2` | fase 2 en modo disparado (parado) |
| `STREAM ON\|OFF` | enviar o no las tramas de muestras (p. ej. solo `#DEC`) |
| `STATUS`, `VER`, `HELP` | estado, version, ayuda |

Modo disparado: se evalua por bloques (2.05 ms a 500 kS/s). Un bloque esta activo si alguna
muestra se aparta mas de `THR` de la linea base seguida en reposo, o si alguna barrera esta
activa. Al activarse se envian tambien los bloques anteriores que cubren >= 20 ms (pre-disparo,
10 bloques a 500 kS/s) y se sigue enviando hasta 100 ms sin actividad (49 bloques). La logica
(`mh_trig_*`, `mh_block_activity`) es portable y esta probada en host.

## Fase 2: decodificacion en placa (`common/f2f_decode.[ch]`)

Todo en enteros (sirve en RP2040 sin FPU), sin malloc, por flujo:

1. Diezmado: suma de bloques de M muestras, `y[j] = b[j] + b[j-1]` (ventana de 2M muestras).
2. Detector de picos de polaridad alternada: sigue el extremo actual y lo da por pico cuando
   la senal retrocede mas que una histeresis = 0.20 x envolvente pico-pico seguida (ataque
   rapido, caida lenta, caida forzada si dejan de llegar picos), con un suelo minimo
   (`noise_floor`, 24 cuentas p-p). No necesita linea base. Tiempo de pico interpolado con una
   parabola por 3 puntos (1/64 de muestra).
3. Seguidor de periodo de bit: engancha con 4 intervalos concordantes (ceros de cabecera);
   intervalo < 0.72 P = media celda; dos medias cuya suma <= 1.25 P = bit 1 (el criterio de la
   suma es inmune al desplazamiento de pico de la transicion central); P se actualiza con un IIR
   (alfa 1/4) con correccion acotada a +-25 %. Se desengancha con huecos > 4 P o con una tasa de
   errores sostenida; los tramos enganchados de menos de 24 bits (ruido) se descartan.
4. ISO 7811: pista 1 (7 bits, +0x20, SS `%`) y pistas 2/3 (5 bits, +0x30, SS `;`), ES `?`,
   paridad impar por caracter, LRC (paridad par por columna sobre SS..ES..LRC, con su bit de
   paridad impar). Se prueba el flujo directo y el invertido (ambos sentidos de pasada) y, con
   `F2F_FMT_AUTO`, los dos formatos.
5. `f2f_multi_*`: 7 instancias en paralelo con M = 1, 2, 4 ... 64 (coste < 2x una instancia)
   para cubrir 0.05 - 1.5 m/s sin conocer la velocidad; si varias decodifican bien se toma la
   central.

Estados (`f2f_status_t`): `F2F_OK`, `F2F_NO_SIGNAL` (menos de 10 transiciones), `F2F_NO_START`
(transiciones pero sin centinela de inicio), `F2F_NO_END` (SS sin ES+LRC), `F2F_PARITY_ERR`
(numero y posiciones de caracter), `F2F_LRC_ERR`. El resultado incluye sentido, ceros de
cabecera, periodo de bit minimo/maximo, numero de transiciones y errores de trama F2F.
La ruta de flancos del comparador entra con `f2f_feed_edge()` (marcas de tiempo enteras).

En el firmware (`DECODE ...` + `TRIG ON`) cada pasada produce lineas
`#DEC ch=A src=adc|cmp st=OK fmt=2 dir=F lz=20 ... txt=;...?`. `src=cmp` usa el nivel del
comparador muestreado por PIO (resolucion 1/fs por canal), no un temporizador de captura.

Por debajo del umbral de deteccion el estado deja de ser informativo: con SNR muy baja el
ruido genera transiciones y un "SS" casual puede dar `PARITY_ERR`/`NO_END` en vez de
`NO_START`. En las pruebas nunca ha dado `OK` con una cadena incorrecta (lo protegen paridad +
LRC + ceros de cabecera coherentes), pero el LRC es de 4 o 6 bits: no es una garantia.

## Limites esperados (estimaciones, NO medidas)

* **USB**: 500 kS/s x 2 bytes = 1.0 MB/s de carga util, mas ~1.7 % de cabeceras. Un CDC a
  Full Speed tiene un techo teorico de ~1.2 MB/s y en la practica bastante menos, asi que **no se
  debe esperar flujo continuo sin perdidas a 250 kS/s por canal en dos canales**. El anillo
  (128 bloques = 0.26 s a 500 kS/s en RP2350; 48 bloques = 0.10 s en RP2040) absorbe pasadas
  cortas en modo disparado; para pasadas lentas a plena frecuencia habra perdidas, que quedan
  senaladas. Alternativas si aparecen: `RATE 125000` (dos canales), un solo canal, o `STREAM OFF`
  con `DECODE`. Hay que medirlo.
* **CPU de la fase 2**: 2 canales x 250 kS/s x ~2 instancias equivalentes; no medido. En RP2040
  puede no llegar a tiempo real junto con el envio USB.
* **ENOB/ruido del ADC, diafonia entre canales en round-robin, jitter**: no caracterizados.
* El envio usa `stdio_usb` (`fwrite` + `fflush`); si el caudal no basta, el siguiente paso es
  usar TinyUSB directamente (`tud_cdc_write`).

## Pruebas en host

```
make -C fw/common test     # 125 comprobaciones internas
make -C fw/common asan     # lo mismo con AddressSanitizer + UBSan
make -C fw/common syntax   # sintaxis de main.c contra stubs (ver "Estado real")
cd tools && python3 -m pytest tests   # incluye C vs Python y el camino de tramas simulado
```
