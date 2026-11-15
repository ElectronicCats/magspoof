# 01 · Investigación y cálculos

Convención de etiquetas usada en todo el proyecto:

| Etiqueta | Significado |
|---|---|
| **[H]** | Hecho verificado en fuente primaria o en el repositorio (se cita) |
| **[H\*]** | Dato tomado de un extracto de búsqueda de la fuente citada; la sesión no pudo abrir el PDF completo (red restringida). Abrir la fuente antes de depender de él |
| **[E]** | Estimación propia, con supuestos explícitos |
| **[S]** | Hipótesis apoyada en simulación ideal (falta simulación 3D o medición) |
| **[F]** | Solo se puede validar físicamente |
| **[NV]** | No verificado |

## 1. Punto de partida: MagSpoof V5 (verificado en este repositorio)

- **[H]** Revisión vigente: carpeta `V5/`, serigrafía "Magspoof V5.0", PCB 32.5 × 76.5 mm, espesor 0.8 mm (`V5/Hw/Magspoof_V5.kicad_pcb`).
- **[H]** MCU CH552G, driver TC4424 (BOM `V5/Hw/BOM.csv`; la tabla del wiki dice TC4422: inconsistencia documental), LDO AP2112K-3.3, cargador MCP73831, bobina impresa "30t_30mm" con R = 11.52 Ω y L = 14.18 µH según el texto de la propia PCB.
- **[H]** Emulación: `playBit()` invierte la polaridad del puente cada `CLOCK_US = 200 µs`, es decir ≈ 2.5 kb/s; pista 1 (7 bits) y pista 2 (5 bits), `TRACKS = 2`. El README hereda del proyecto original la frase "soporta las tres pistas"; el firmware V5 solo maneja dos.
- **[H]** "Lectura": no hay cabezal ni frente analógico en V5. El firmware abre `Serial0` a 9600 baud y trata cada línea recibida que empieza con `%` o `;` como pista 1 o 2 ya decodificada en ASCII. El wiki dice solo que "se puede conectar un lector externo al UART"; no documenta modelo, pistas ni cableado del lector.
- **[NV]** Página de la tienda (`electroniccats.com/store/magspoof-v5/`): el host no es alcanzable desde esta sesión. Precio, contenido del paquete y descripción comercial quedan sin verificar aquí.

Consecuencia: el producto nuevo no hereda nada del camino de lectura; todo el frente analógico y la decodificación F2F son desarrollo nuevo. Lo único reutilizable es el conocimiento del lado de emulación.

## 2. Requisitos derivados de ISO/IEC 7811

| Parámetro | Pista 1 | Pista 2 | Pista 3 | Etiqueta |
|---|---|---|---|---|
| Densidad | 210 bpi | 75 bpi | 210 bpi | [H\*] MagTek 99800004 |
| Bits por carácter (con paridad impar) | 7 | 5 | 5 | [H\*] |
| Caracteres máx. | 79 | 40 | 107 | [H\*] |
| Celda de bit | 121.0 µm | 338.7 µm | 121.0 µm | [H] aritmética |
| **Separación mínima entre transiciones** (bit "1") | **60.5 µm** | **169.3 µm** | 60.5 µm | [H] |
| Longitud de onda fundamental, unos / ceros | 121 / 242 µm | 339 / 677 µm | 121 / 242 µm | [H] |
| Eje de pista desde el canto de referencia | 7.06 mm | 10.36 mm | 13.92 mm | [H\*] Q-Card, MagTek 99821002 |
| Ancho grabado | 2.80 mm | 2.80 mm | 2.80 mm | [H\*] |
| Ancho de lectura típico de cabezales | 1.4–1.5 mm | | | [H\*] Techreco TG142, Brush |

Otros: tarjeta ID-1 85.60 × 53.98 × 0.76 mm **[H\*]**; la banda puede sobresalir hasta 0.038 mm y su rugosidad Ra ≤ 0.40 µm (edición 1996) **[H\*]**; LoCo ≈ 300 Oe, HiCo 2750–4000 Oe **[H\*]**; la norma define la amplitud solo relativa a una tarjeta de referencia (UR), no publica flujo absoluto **[H\*]**. LRC: paridad par por columna sobre SS…ES…LRC **[H\*]**; el bit de paridad del propio LRC es impar **[NV, memoria]**.

Frecuencias de la señal (f = v/λ), de `calc/out/results.json`:

| Velocidad | T2 ceros | T2 unos | T1 ceros | T1 unos |
|---|---|---|---|---|
| 0.05 m/s | 74 Hz | 148 Hz | 207 Hz | 413 Hz |
| 0.25 m/s | 369 Hz | 738 Hz | 1.03 kHz | 2.07 kHz |
| 1.0 m/s | 1.48 kHz | 2.95 kHz | 4.13 kHz | 8.27 kHz |
| 1.5 m/s | 2.21 kHz | 4.43 kHz | 6.20 kHz | 12.4 kHz |
| 2.54 m/s (100 ips, tope citado en ADI AN5094 **[H\*]**) | 3.75 kHz | 7.5 kHz | 10.5 kHz | 21 kHz |

Banda útil del frente analógico: ~50 Hz a ~40 kHz (tercer armónico de T1 a 1.5 m/s ≈ 37 kHz).

## 3. Física usada (fórmulas y origen)

- Pérdida por separación (Wallace 1951): `L = 54.6·d/λ dB` **[H\*]**. Para T1-unos (λ = 121 µm) son **0.45 dB por micrómetro**; para T2-unos 0.16 dB/µm. Es el número que gobierna todo el diseño mecánico.
- Pérdida de entrehierro ideal: `sin(πg/λ)/(πg/λ)`, nulo en g = λ **[H\*]** (Westmijze 1953).
- Campo de Karlqvist y reciprocidad: `e(t) = −µ0·N·η·W·v·∬(∂M/∂x)·hx dx dy`, con `hx` = campo del cabezal por unidad de FMM en el entrehierro **[E, fórmulas de memoria; contrastadas numéricamente abajo]**.
- Eficiencia: `η = R_gap/(R_gap + R_núcleo + R_entrehierros_traseros)` **[E]**.

Dos resultados analíticos que ordenan la comparación de arquitecturas **[E]**:

1. Lejos del entrehierro, un cabezal ideal da `hx = (N·η/π)·y/(x²+y²)`; un conductor recto con corriente da `hx = (1/2π)·y/(x²+y²)`. **Una pista de cobre aislada equivale exactamente a media espira de un cabezal perfecto con entrehierro cero**, colocada a la profundidad del cobre. No es que "no detecte": resuelve igual que un cabezal a esa distancia, pero con N·η = 0.5 en vez de cientos.
2. Sobre el plano de los polos, el campo solo depende del potencial magnético en ese plano. Por eso **dos láminas delgadas coplanares separadas g dan la misma función de lectura que un cabezal de anillo clásico de entrehierro g** (comprobado: el solver por diferencias finitas reproduce Karlqvist con 1.5 % de error en el pico, `solver_check… = 0.986`). El núcleo no necesita profundidad perpendicular a la tarjeta; eso es lo que permite un cabezal plano.

## 4. Resultados del modelo (`calc/head_model.py`)

Supuestos del medio **[NV]**: capa magnética δ = 10 µm, parámetro de transición a = 8 µm, magnetización longitudinal. Polos ideales (µ→∞), 2D.

### 4.1 Resolución: relación de amplitudes unos/ceros y PW50 [S]

| Geometría | d = 5 µm | 12.5 µm | 25 µm | 37.5 µm | 50 µm | 75 µm |
|---|---|---|---|---|---|---|
| **T1**, a tope g = 12.5 µm | 0.90 | 0.81 | 0.65 | 0.50 | 0.38 | 0.22 |
| **T1**, a tope g = 25 µm | 0.88 | 0.79 | 0.63 | 0.49 | 0.36 | 0.21 |
| **T1**, a tope g = 50 µm | 0.80 | 0.70 | 0.54 | 0.40 | 0.30 | 0.17 |
| **T1**, solape s = 12.5 µm, lámina 20 µm | 0.75 | 0.66 | 0.51 | 0.39 | 0.29 | 0.18 |
| **T1**, solape s = 25 µm, lámina 20 µm | 0.72 | 0.64 | 0.49 | 0.37 | 0.28 | 0.18 |
| **T2**, a tope g = 25 µm | 0.98 | 0.97 | 0.94 | 0.90 | 0.85 | 0.73 |
| **T2**, solape s = 25 µm | 0.93 | 0.91 | 0.87 | 0.82 | 0.76 | 0.65 |
| PW50 (a tope g = 25) | 43 µm | 57 µm | 79 µm | 105 µm | 129 µm | 181 µm |

Lecturas:

- En pista 1 la separación efectiva d manda mucho más que el entrehierro: pasar de g = 12.5 a 50 µm cuesta ~15 % de resolución; pasar de d = 12.5 a 50 µm la reduce a menos de la mitad y además baja la amplitud absoluta de unos 17 dB. **El control de la distancia banda–polo es el problema de ingeniería dominante, no el entrehierro.**
- Pista 2 tolera d ≈ 75–100 µm con cualquiera de las geometrías.
- El entrehierro por solape pierde ~15–20 % de resolución frente al de tope y ~7 dB de amplitud en T1 (el polo inferior queda retranqueado), pero su valor está definido por el espesor de una película, no por un corte de precisión.
- Qué relación unos/ceros necesita el decodificador se obtiene de la simulación del decodificador (ver `tools/out/`), no de esta tabla.

### 4.2 Eficiencia del circuito magnético [E]

Cinta 1.5 mm × 18 µm, recorrido 28 mm:

| Construcción | µr = 1 000 | µr = 10 000 | µr = 80 000 |
|---|---|---|---|
| Entrehierro a tope 25 µm, cinta enhebrada (sin entrehierro trasero) | 0.12 | 0.58 | 0.92 |
| Igual, pero polos + yugo separados por 0.8 mm de FR4 (sin enhebrar) | 0.10 | 0.28 | 0.34 |
| Solape 25 µm, longitud de solape 0.1 mm | 0.10 | 0.52 | 0.90 |
| Solape 25 µm, solape 0.3 mm | 0.04 | 0.32 | 0.79 |
| Solape 25 µm, solape 1.0 mm | 0.015 | 0.13 | 0.55 |

- La permeabilidad real de la cinta después de cortarla, doblarla y pegarla es **[F]**. Metglas 2714A declara µ > 80 000 sin recocer y magnetostricción < 1 ppm **[H\*]**; el mu-metal recocido pierde permeabilidad con el trabajo en frío y el fabricante pide recocido en hidrógeno tras conformar **[H\*]**; cuánto pierde exactamente es **[NV]**.
- En el solape, la longitud solapada es un cortocircuito magnético parcial: hay que mantenerla ≤ 0.3 mm o compensar con µr alto. Es una variable del experimento.
- Con lámina de 50 µm (mu-metal disponible) la reluctancia del núcleo baja 2.8×, lo que mejora η, pero el escalón del solape crece y empeora la resolución en T1.

### 4.3 Amplitud esperada [E], con Mr·δ desconocido

No se encontró ninguna fuente con el flujo remanente absoluto de una banda **[NV]**. Se barre Mr = 40–120 kA/m con δ = 10 µm.

Verificación cruzada con un cabezal real: el Techreco TG142 declara 19 mVpp a 210 bpi y 7.5 ips, 28 mH, 140 Ω, entrehierro 30 µm, ancho 1.4 mm **[H\*]**. Con el mismo modelo eso exige N·η ≈ 2500 / 1250 / 830 para Mr = 40 / 80 / 120 kA/m. Son valores verosímiles para un devanado de hilo fino, así que el modelo no está fuera de escala; pero no permite separar N de Mr.

| Caso, a 0.19 m/s (7.5 ips) | Mr = 40 | 80 | 120 kA/m |
|---|---|---|---|
| Cupón H (N = 72, η = 0.4), T1 unos, d = 25 µm, pico | 45 µV | 90 µV | 135 µV |
| Cupón H, T2 ceros, d = 25 µm, pico | 82 µV | 164 µV | 246 µV |
| Cupón A, una pista de 100 µm sin máscara, T2 ceros, pico | 1.9 µV | 3.9 µV | 5.8 µV |

Todo escala linealmente con la velocidad: a 0.05 m/s divide entre 3.8; a 1 m/s multiplica por 5.3. El cupón H queda entre 15 y 50 veces por debajo de un cabezal comercial (0.1–0.3 mV frente a ~10 mV de pico), enteramente por número de espiras.

### 4.4 Ruido y margen [E]

- Bobina del cupón H: 1.92 m de pista, R ≈ 12 Ω estimada → 0.45 nV/√Hz térmicos. L estimada del orden de 30–100 µH: a 20 kHz la reactancia es comparable a R, sin efecto con entrada de alta impedancia. Capacitancia entre capas del orden de 10 pF → resonancia propia en MHz, fuera de banda.
- Con un amplificador de 2.7 nV/√Hz y 20 kHz de banda: ≈ 0.4 µV rms referidos a la entrada. Peor caso del cupón H (T1, 0.05 m/s, Mr bajo, η = 0.4): 12 µV de pico → **SNR ≈ 26 dB** (≈ 34 dB si se limita la banda a 3 kHz a esa velocidad). Con η = 0.1 se pierden otros 12 dB. El margen existe pero no sobra: por eso la eficiencia y las espiras sí importan, y por eso el siguiente paso natural si la geometría funciona es subir a 6 capas / más espiras, no cambiar el amplificador.
- Cupón A: 4 µV a 0.19 m/s contra 0.4 µV rms → detectable (SNR ~17 dB), útil como medidor, no como lector.

## 5. Comparación de arquitecturas

### 5.1 Bobina impresa sin núcleo — no como lector; sí como instrumento

- Resolución **[S]**: una pista de 100 µm sin máscara da unos/ceros = 0.88 en T2 pero 0.21 en T1; con máscara (25 µm más de separación) 0.78 y 0.12. La pista mínima estándar (100 µm) ya es mayor que la separación entre transiciones de T1 (60.5 µm). Haría falta pista ≤ 50 µm, sin máscara y en contacto directo con la banda: fuera de PCB convencional y con desgaste del cobre.
- Amplitud **[E]**: N·η = 0.5. Sumar espiras no ayuda: las pistas contiguas muestrean posiciones distintas (filtro peine) y las capas inferiores quedan ≥ 100 µm más lejos, donde T1 ya perdió > 45 dB.
- Valor experimental: es el único transductor de la familia cuya sensibilidad se calcula sin parámetros desconocidos de núcleo. **Mide el flujo absoluto de la banda (Mr·δ) y la pérdida por separación real**, que son las dos incógnitas que hoy impiden cerrar los números del híbrido. Cuesta una PCB de 2 capas sin ensamblaje. Se fabrica como cupón A con ese propósito declarado.

### 5.2 Híbrido: devanado en PCB + cinta magnética blanda — ruta principal

- Físicamente equivalente a un cabezal de anillo en resolución (§3, punto 2) con entrehierro alcanzable de 12.5–50 µm.
- Señal 15–50× menor que un cabezal comercial, pero con fuente de ~12 Ω el ruido también es mucho menor; SNR estimada ≥ 26 dB en el peor caso.
- Espesor añadido a la PCB: 20–100 µm. Es la única ruta encontrada que puede dar un cabezal de "espesor de PCB".
- Riesgos reales, todos **[F]**: (1) mantener d ≤ 25 µm con una superficie plana contra una tarjeta flexible; (2) permeabilidad efectiva de la cinta tras el ensamblaje; (3) definir y repetir el entrehierro; (4) desgaste de una lámina de 18–50 µm; (5) las bobinas ocupan ~8 × 12 mm por polo, así que dos pistas a 3.30 mm de paso obligan a escalonar los cabezales a lo largo del deslizamiento (más superficie a cambio de espesor).
- Arte previo: no se encontró ningún cabezal de banda magnética hecho con bobina de PCB y núcleo de lámina **[NV: búsqueda sin resultados, no prueba de inexistencia]**. Lo más cercano son cabezales de película delgada con espirales planas (EP0189793A2, US5745329, US4985985) y los emuladores de tarjeta dinámica con bobinas en PCB multicapa y material blando (familia Dynamics, US7246752B2) **[H\*]**. Antes de un producto conviene una búsqueda de libertad de operación.

### 5.3 Magnetorresistivos — no se fabrica en la primera tanda

- Ningún sensor encapsulado con distribución establecida tiene geometría verificada para pista 1: los GMR de NVE (AA/AAH) integran sobre milímetros con concentradores de flujo; los gradiómetros ABL tienen 0.5–1.0 mm entre elementos; los "cabezales" TMR de MultiDimension (TMR6401/6501) son sensores de billetes con 0.475 mm de resolución e imán de polarización de 800 G, superior a la coercitividad de una tarjeta LoCo **[H\*]**.
- Candidatos plausibles solo para pista 2: NVE ALT025-14E (ULLGA 1.1 × 1.1 × 0.35 mm) y Allegro CT100 (DFN 1.5 × 1.5 × 0.45 mm o dado), ambos listados en Digi-Key **[H\*]**. La distancia del elemento a la cara superior del encapsulado y la longitud del elemento en la dirección de lectura no aparecen en ningún dato accesible **[NV]**. Con 125–200 µm de profundidad supuesta, T1-unos pierde 56–90 dB: inviable; T2-unos pierde 20–32 dB: posible con ecualización.
- Decisión: no diseñar cupón MR hasta tener esos dos datos del fabricante (pregunta concreta en `05_incertidumbres_y_pendientes.md`). Un cupón que solo puede leer pista 2 no resuelve la incertidumbre principal del producto.

### 5.4 Núcleo convencional (láminas o ferrita perpendiculares) — reserva

Dos medias piezas de ferrita o permalloy con separador, lapeadas y pasadas por ranuras con bobinas planas alrededor. Es la opción de menor riesgo magnético y mayor riesgo de fabricación: exige rectificado/lapeado de la cara de contacto, y un entrehierro de 10–50 µm en ferrita sufre desportillado del borde **[H\*, patentes; NV en cifras]**. En ese punto se está fabricando un cabezal clásico, que es justo el componente que hoy solo ofrecen fabricantes especializados (Brush, Techreco, MagTek venden a OEM; no se encontró ningún cabezal desnudo en Digi-Key, Mouser, Farnell, RS o TME **[H\*/NV]**). Se pospone: solo se justifica si el híbrido plano falla por contacto o desgaste y no por magnetismo.

## 6. Qué pista primero

**Empezar por pista 2, y exigir pista 1 antes de declarar viable la geometría.**

- Pista 2 (75 bpi) tolera 3–4 veces más separación y entrehierro; su decodificación es la más simple (5 bits, 40 caracteres). Sirve para validar la cadena completa —mecánica, AFE, adquisición, decodificador— sin que el cabezal sea el factor limitante.
- Pista 1 (210 bpi) es la prueba discriminante del cabezal y además representa a la pista 3. Un cabezal que lee pista 2 y no pista 1 no sirve para el producto.
- Por eso el cupón H lleva dos sitios y dos posiciones de montaje con pasadores (P1/P2, desplazadas 3.30 mm): el mismo cabezal ensamblado se prueba primero sobre pista 2 y después sobre pista 1 sin reconstruirlo.
- Para soportar las dos pistas a la vez falta demostrar: diafonía entre sitios escalonados, registro lateral simultáneo de ambos ejes con las tolerancias de PCB, y decodificación de dos canales con el desfase espacial de 25 mm entre entrehierros.

## 7. Acoplamiento de la bobina transmisora [E]

- Bobina V5: 30 espiras, 30 mm, ~0.3 A con 3.3–4.2 V sobre 11.5 Ω, τ = L/R ≈ 1.2 µs. Campo en el centro ~0.4 mT; dB/dt en los flancos ~300 T/s.
- Cada bobina del cupón H tiene 1437 mm²·espira (`hw/gen_report.json`). Un campo uniforme perpendicular de 300 T/s induciría ~0.43 V por bobina. Las dos bobinas están en oposición; el área no compensada calculada del trazado completo es 12 mm² (sitio S1) y 25 mm² (S2), es decir **−42 y −35 dB** de rechazo geométrico a campo uniforme → picos de ~4–8 mV, 20–100 veces la señal de lectura. El campo real no es uniforme, y la cinta además concentra flujo en el plano, que no se cancela: el valor real es **[F]**.
- Conclusión de diseño: no se intenta leer mientras se transmite. El frente analógico se diseña para no dañarse y recuperarse en decenas de ms; en el producto, lectura y emulación se multiplexan en el tiempo y conviene separar físicamente la bobina de emulación de los polos. La prueba T8 del plan mide el acoplamiento real con un MagSpoof V5.

## 8. Importación a México

- **[H\*]** Como análogo de EE. UU.: resoluciones CBP N304629 y N224576 clasifican lectores de banda completos en HTSUS 8471.90 ("magnetic or optical readers").
- **[NV]** Fracción mexicana (TIGIE) de un lector completo, de un cabezal desnudo (¿8473.30 u 8522.90?) y de lámina magnética o sensores; aplicabilidad de NOM-019-SE-2021 a un lector completo; todo esto debe confirmarlo un agente aduanal. Que comprar componentes en lugar del módulo reduzca impuestos o trámites **no está verificado** y no se usa como argumento del proyecto.

## 9. Pistas de la conversación previa: resultado de la comprobación

| Pista | Resultado |
|---|---|
| Silicon Labs AN148 | **[H\*]** Existe: "Magnetic Stripe Reader", C8051F330. Conecta los cabezales directamente al ADC diferencial de 10 bits, sin amplificador, 200 ksps, detección de picos por software con umbral de periodo al 75 %. Útil como referencia de algoritmo; no da datos del cabezal |
| Brush Industries | **[H\*]** Existe (Sunbury, PA); vende cabezales de 5 mm de perfil y lectores. No publica datos eléctricos; hay que pedirlos |
| MagTek | **[H\*]** Vende cabezales y ASIC (Delta, 21006541) a OEM. El documento 99821002 es solo mecánico |
| Techreco TG214C | **[NV]** No se encontró ese número. Sí existe el **TG142** con hoja de datos (usado arriba como referencia) |
| Gitec 2TRHEAD(HNR) | **[NV]** Sin resultados para fabricante ni número de parte |

## 10. Fuentes

- Repositorio y wiki: https://github.com/ElectronicCats/magspoof · https://github.com/ElectronicCats/magspoof/wiki
- MagTek, Magnetic Stripe Card Standards: https://www.magtek.com/content/documentationfiles/d99800004.pdf
- MagTek 99821002: https://www.magtek.com/content/documentationfiles/d99821002.pdf
- Q-Card, glosario: https://www.q-card.com/about-us/magnetic-stripe-glossary/page.aspx?id=1456
- ISO 7811-4/-5 (1985, muestras): https://cdn.standards.iteh.ai/samples/14722/dd262c0ac5bf4d529dd815814ef2f3ce/ISO-7811-4-1985.pdf
- ISO/IEC 7811-6:2018 (muestra): https://cdn.standards.iteh.ai/samples/73639/8906b407274641f0b6be49a3693e7b8d/ISO-IEC-7811-6-2018.pdf
- EN ISO/IEC 7811-2:1996: https://standards.iteh.ai/catalog/standards/cen/a4762488-9d0c-4007-a713-41fe9a10ea36/en-iso-iec-7811-2-1996
- Silicon Labs AN148: https://www.silabs.com/documents/public/application-notes/AN148.pdf
- Techreco TG142: https://techreco.jp/files/libs/17/201604011727235145.pdf
- ADI/Maxim AN5094: https://www.analog.com/media/en/technical-documentation/app-notes/improve-magnetic-card-reading-in-the-presence-of-noise.pdf
- Brush Industries: https://www.brushindustries.com/products/products/page.aspx?id=1079
- Wallace / manual STL: http://aes-media.org/historical/pdf/morrison_stl-manual.pdf · Westmijze 1953: https://www.lorentz.leidenuniv.nl/history/proefschriften/sources/Westmijze_1953.pdf
- Metglas 2714A: https://metglas.com/wp-content/uploads/2016/12/2714A-Technical-Bulletin.pdf
- Magnetic Shield Corp., lámina MuMETAL: https://magnetic-shield.com/mumetal-perfection-annealed-foil · en Digi-Key: https://www.digikey.nl/en/products/detail/magnetic-shield-corporation/MU002-8/13160829
- NVE ALT025: https://www.nve.com/Downloads/ALT025-14E-EVB01.pdf · Allegro CT100: https://www.allegromicro.com/-/media/files/datasheets/ct100-datasheet.pdf
- MDT TMR6401 en Digi-Key: https://www.digikey.de/en/products/detail/multidimension/TMR6401/15198015
- Patentes citadas: EP0189793A2, US5745329, US4985985, US7246752B2, US11397863, US9104922 (Google Patents / USPTO)
- CBP N304629 (vía agregador): https://www.tarifflens.ai/rulings/N304629
