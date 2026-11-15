# Herramientas MagHead (adquisicion y analisis)

Software de PC para el banco de pruebas de cabezales LECTORES experimentales: captura de la
senal (firmware `fw/maghead_capture`, WAV o CSV de osciloscopio), decodificacion F2F / ISO 7811
y metricas por pasada. Las tarjetas son de laboratorio, con contenido sintetico conocido.

Requisitos: Python >= 3.10, `pip install -r requirements.txt` (numpy, scipy, matplotlib,
pyserial, pytest). Para el decodificador C en host: gcc y make.

```
tools/
  maghead/
    synth.py      generador de senal sintetica (con verdad-terreno)
    decode.py     decodificador de referencia (mismo algoritmo que el C) + variante no causal
    cdecode.py    el modulo C del firmware compilado en host, via ctypes
    capture.py    puerto serie (firmware), WAV, CSV de osciloscopio -> .npz + .json
    swipefile.py  formato de archivo y esquema de metadatos
    metrics.py    metricas por pasada y veredictos L1 / L2 / L3
    report.py     agregado de una carpeta: CSV + tabla resumen
    sim_grid.py   mapa de exito L3 frente a SNR y PW50 (simulacion)
  tests/          pytest (172 pruebas)
  out/            decode_vs_snr_pw50.{png,md,json}
  meta_template.json   plantilla de metadatos
```

## Uso

```
# 1. Captura desde el firmware (modo disparado, una pasada por archivo)
python -m maghead.capture serial --port /dev/ttyACM0 --out datos/V1 --meta meta_template.json --swipes 20
#    ... o importando
python -m maghead.capture wav pasada.wav --out datos/V1/p001 --meta meta_template.json --volts-full-scale 2.0
python -m maghead.capture csv scope.csv  --out datos/V1/p002 --meta meta_template.json
python -m maghead.capture bin flujo.bin  --out datos/V1 --meta meta_template.json     # flujo CDC guardado

# 2. Metricas de una pasada / informe de una carpeta
python -m maghead.metrics datos/V1/p001
python -m maghead.report datos/ --out informe/

# 3. Datos sinteticos y simulacion
python -m maghead.synth demo/a --speed 0.3 --pw50 40 --snr 30
python -m maghead.sim_grid --trials 200 --out out/

# 4. Pruebas
python -m pytest tests
```

## Formato de archivo: una pasada = `<base>.npz` + `<base>.json`

`.npz` (numpy comprimido):

| Array | Tipo | Contenido |
|---|---|---|
| `chA` | int16[N] | codigos ADC del canal A, 0..4095, centro 2048 |
| `chB` | int16[N] | canal B, o vacio |
| `dig` | uint8[N] | bits por muestra: b0 barrera 1, b1 barrera 2 (1 = tarjeta presente), b2 comparador A, b3 comparador B; o vacio |
| `fs` | float | frecuencia de muestreo POR CANAL (Hz) |
| `gate_edges` | float[K,3] | flancos de barrera: t (s desde la primera muestra), barrera (1 o 2), nivel (1 = tarjeta presente) |

`.json` - esquema de metadatos (version 1; `swipefile.SCHEMA`, validado con
`swipefile.validate_meta`). "Oblig." = necesario para el analisis o para agrupar el informe.

| Clave | Tipo | Oblig. | Significado |
|---|---|---|---|
| `schema_version` | int | si | Version del esquema (1). |
| `swipe_id` | str | no | Identificador de la pasada (por defecto, el nombre del archivo). |
| `card_id` | str | si | Identificador de la tarjeta de laboratorio. |
| `expected_tracks` | dict | si | Cadenas esperadas por pista, con centinelas: `{"1": "%...?", "2": ";...?"}`. |
| `track_under_test` | int | si | Pista bajo el cabezal del canal analizado: 1, 2 o 3. |
| `channel_under_test` | str | no | Canal del cabezal bajo prueba: "A" (defecto) o "B". |
| `head_variant` | str | si | Identificador de la variante de cabezal. |
| `head_gap_um` | float o null | no | Entrehierro nominal (um). |
| `head_spacer` | str o null | no | Material/espesor del separador del entrehierro. |
| `assembly_serial` | str o null | no | Numero de serie del montaje. |
| `spacing_shim_um` | float o null | si | Calza de separacion cabezal-tarjeta (um); 0 = contacto. |
| `pad_force_N` | float o null | no | Fuerza de la almohadilla de presion (N). |
| `lateral_offset_mm` | float o null | no | Desplazamiento lateral respecto al centro de pista (mm). |
| `azimuth_deg` | float o null | no | Angulo de azimut del entrehierro (grados). |
| `afe_gain_a` | float o null | si | Ganancia total del AFE del canal A (V/V); necesaria para uV*s/m. |
| `afe_gain_b` | float o null | no | Ganancia total del AFE del canal B (V/V). |
| `bpi` | float | no | Densidad si no es la de la pista (210 / 75 / 210 bpi). |
| `volts_per_count` | float | no | Voltios por cuenta de chA/chB (defecto 3.3/4096). |
| `nominal_speed_m_s` | float o null | si | Velocidad nominal de la pasada (m/s). |
| `speed_source` | str | si | Como se produjo la velocidad: "hand", "motor" o "synthetic". |
| `operator` | str o null | no | Persona que hizo la pasada. |
| `date` | str | si | Fecha y hora ISO 8601. |
| `firmware_version` | str o null | no | Version del firmware (respuesta a `VER`). |
| `capture_source` | str | no | "serial", "wav", "csv" o "synth". |
| `dropped_blocks` | int | no | Bloques perdidos por el firmware dentro de la pasada. |
| `gaps` | list | no | Huecos rellenados con el valor medio: `[[muestra_inicial, n_muestras], ...]`. |
| `notes` | str | no | Texto libre. |
| `synthetic` | dict | no | Solo datos sinteticos: verdad-terreno (`t_trans`, `pw50_um`, `snr_db`...). |

Notas de alfabeto: la pista 1 admite 0x20-0x5F; las pistas 2/3 solo `0-9 : ; < = > ?`. Una
cadena de pista 2 con letras (p. ej. `X`) no es codificable y `synth.encode_chars` la rechaza.

## Metricas (`metrics.analyze`) y veredictos

Tres niveles **separados**; un cabezal puede dar senal sin que se pueda decodificar:

| Nivel | Significado | Criterio |
|---|---|---|
| L1 | senal detectada | SNR > 12 dB (`--l1-snr`) |
| L2 | transiciones recuperadas | 100 % de las transiciones esperadas en la zona de datos (SS..LRC), sin sobrantes |
| L3 | decodificacion completa correcta | cadena == esperada, estado OK (paridad + LRC) |

| Metrica | Definicion |
|---|---|
| `noise_rms_counts` | desviacion tipica en una ventana sin senal (antes o despues de la pasada, hallada por envolvente; si no se puede, mediana del 20 % mas tranquilo de tramos de 5 ms: ver `noise_window`). Incluye el zumbido de red. |
| `amp_preamble_counts`, `amp_data_*` | mediana de \|pico - linea base\| en los ceros de cabecera y en la zona de datos (todos / ceros / unos). El pico se mide sobre la senal cruda promediada en +-10 % de la anchura del pulso. |
| `snr_db` | 20 log10(amplitud de los ceros de cabecera / ruido RMS). Ojo: es la amplitud con interferencia entre pulsos, no la del pulso aislado. |
| `resolution` | amplitud mediana de los pulsos de '1' / de los pulsos de '0'. |
| `speed_gates_mm_s` | 20.00 mm / (t barrera 2 - t barrera 1). Velocidad media ENTRE barreras, antes de llegar al cabezal. |
| `speed_bits_mm_s` (min, max) | celda / periodo de bit (mediana y extremos por bit sobre cabecera + datos). |
| `amp_norm_uV_s_per_m` | uV referidos al cabezal (con `afe_gain_*`) / velocidad local, mediana sobre los ceros de cabecera. `amp_norm_iso_...`: lo mismo corregido a pulso aislado suponiendo lorentzianas. |
| `pw50_raw_um`, `pw50_um`, `pw50_valid` | anchura a media altura del pulso MEDIO de las transiciones aisladas (ceros), en um. `pw50_um` corrige la interferencia de los vecinos **suponiendo pulsos lorentzianos**. `pw50_valid = 0` si la correccion no es invertible (PW50 >~ 0.9 celda), si el pulso dura < 30 us (limitado por el paso bajo de 40 kHz: usar pasadas lentas) o si SNR < 20 dB. Usar la pista 2 (celda 339 um) para medir PW50. |
| `exp_transitions`, `trans_matched/missed/extra` | transiciones esperadas segun la cadena conocida frente a las detectadas, alineadas en unidades de media celda (ambos sentidos, todos los desfases). Si el alineamiento se pierde a mitad de pista los recuentos de perdidas/sobrantes dejan de ser exactos, pero L2 = 0 sigue siendo correcto. |
| `bit_errors` | distancia de Hamming entre los bits decodificados y los esperados (alineados por el SS, o al mejor desfase si no hay SS). |
| `truth_*`, `timing_rms_us` | solo sintetico: comparacion con los tiempos de transicion verdaderos. |

`report.py` agrupa por variante de cabezal / tramo de velocidad (0-0.1, 0.1-0.2, 0.2-0.4,
0.4-0.8, 0.8-1.6, >=1.6 m/s; velocidad de barreras, o de bits, o nominal) / calza, y da N,
% L1, % L2, % L3 con intervalo de Wilson al 95 %, mediana del SNR y de la amplitud normalizada.

## Decodificador

`decode.decode()` replica entero a entero `fw/common/f2f_decode.c` (descripcion del algoritmo
en `fw/README.md`); `cdecode.decode()` ejecuta ese mismo C compilado en host (y es lo que usan
`metrics` y `sim_grid` cuando hay gcc). `decode.decode_noncausal()` es una variante solo-host
(filtro gaussiano de fase cero, periodo local suavizado mirando a ambos lados); en las pruebas
hechas no supera al causal multi-instancia, se deja como segunda opinion.

## Generador sintetico (`synth.py`)

Cadena -> bits ISO 7811 (+ ceros delante/detras, LRC) -> transiciones sobre la tarjeta
(celda 25.4/210 o 25.4/75 mm) -> perfil de velocidad (constante, aceleracion lineal, variacion
de mano +-30 %, ambos sentidos) -> suma de lorentzianas alternas de anchura PW50 espacial y
amplitud proporcional a la velocidad instantanea -> + zumbido de 60 Hz + ruido blanco (RMS
definido en banda) + deriva lenta -> AFE (HPF 16 Hz de 1 polo, LPF 40 kHz de 2 polos) -> ADC de
12 bits centrado. Devuelve senal, barreras y verdad-terreno. Es un modelo idealizado: no incluye
perdida por separacion (eso es lo que se quiere medir), azimut, diafonia entre pistas, saltos de
contacto ni ruido no gaussiano.

## Que NO esta probado

* Nada de esto ha visto una senal real: todas las pruebas usan datos sinteticos.
* `capture.read_serial` (pyserial contra el firmware real) no se ha ejecutado; el analizador de
  tramas si, contra tramas generadas por el codigo C del firmware en host.
* Los umbrales por defecto (histeresis 0.20, suelo 24 cuentas, L1 a 12 dB) se han elegido con
  la simulacion; habra que revisarlos con senales reales.
