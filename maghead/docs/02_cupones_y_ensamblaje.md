# 02 · Cupones experimentales, banco y ensamblaje (rev A)

Archivos: `hw/coupon_H/`, `hw/coupon_A/`, `hw/fixture/` (KiCad 9, generados por `hw/gen_pcbs.py`; regenerar con `sh hw/build.sh`). Dibujos acotados en `drawings/`.

Sistema de ejes: **x** = deslizamiento; **z** = transversal, z = 0 en el canto de referencia de la tarjeta (borde de la guía), tarjeta en z < 0; **y** = normal a la tarjeta. Cara **F** de los cupones = la que mira a la tarjeta.

## 1. Qué se fabrica y por qué

| Pieza | Capas / espesor | Para qué | Ensamblaje |
|---|---|---|---|
| **Cupón H** `maghead_H` | 4 capas, 0.8 mm | Cabezal híbrido: bobinas de PCB + cinta magnética blanda. Dos sitios escalonados | Manual: cinta, separador, adhesivo |
| **Cupón A** `maghead_A` | 2 capas, 0.8 mm, ENIG | Pistas sin núcleo: referencia absoluta de flujo y de pérdida por separación | Ninguno |
| **Base** `maghead_base` | 2 capas, 1.0 mm | Mitad inferior del "sándwich": superficie de deslizamiento, lengüetas de presión, 2 compuertas ópticas | 2 sensores + 2 resistencias + pads de presión |
| **Separador/guía** `maghead_spacer` | sin cobre, 1.0 mm | Define la altura de la ranura y el canto guía | Ninguno |

No se fabrica en esta tanda: cupón magnetorresistivo, cabezal de núcleo perpendicular, PCB del frente analógico (ver `01`, §5 y `05`).

El banco reproduce la idea de producto: dos placas forman la ranura; **los elementos de lectura están en una sola placa** (el cupón, rígido, plano) y la otra aporta la presión (lengüeta de FR4 fresada en la base). Solo entra en la ranura el borde de la tarjeta que lleva la banda, como en un lector de deslizamiento; el cupón trabaja en voladizo de 18 mm.

## 2. Cupón H — cabezal híbrido

### 2.1 Geometría (por sitio)

| Parámetro | Valor |
|---|---|
| Ranuras para la cinta | 2 por sitio, no metalizadas, 1.0 × 3.0 mm, centradas en el eje de pista, a x = ±6.0 mm de la línea del entrehierro |
| Bobina alrededor de cada ranura | espiral rectangular, 12 espiras/capa × 3 capas (In1, In2, B.Cu) = 36 espiras |
| Pista / espacio | 0.127 / 0.127 mm (paso 0.254) |
| Hueco interior / exterior de la espiral | 1.8 × 5.5 mm / 7.4 × 11.6 mm (ejes de pista) |
| Vías | pasantes 0.3 mm de taladro / 0.6 mm de corona, 3 por bobina + 5 de enlace por sitio; todas cubiertas de máscara |
| Conexión | las dos bobinas en serie y en oposición: 72 espiras por cabezal |
| Longitud de conductor / R estimada | 1.92 m / ≈ 12 Ω (interiores de 17.5 µm, exterior de 35 µm) |
| Área por bobina / área no compensada | 1437 mm²·espira / 12 mm² (S1), 25 mm² (S2) → rechazo geométrico a campo uniforme −42 / −35 dB |
| Sitios | S1 en x = −12.5, z = −7.06; S2 en x = +12.5, z = −10.36 |
| Contorno | 56 × 32 mm; 3 ranuras M3 (3.2 × 8.5); 2 pares de taladros Ø2.1 para pasador (P1 y P2) |
| Terminales | 2 pads de soldar cable por sitio (N, P) en cara B |

Decisiones de trazado que afectan a la medición:

- **No hay espiras en F.Cu.** Una pista perpendicular al deslizamiento a 40–60 µm de la banda es un captador sin núcleo (lo que mide el cupón A). La capa de bobina más cercana (In1) queda a ≈ 0.25 mm: la captación directa de la pista 1 queda > 90 dB abajo y la de pista 2 > 40 dB.
- En F.Cu solo hay dos tramos de salida **paralelos al deslizamiento** (insensibles a magnetización longitudinal) y cuatro marcas flotantes de la línea del entrehierro, fuera del ancho de la cinta.
- Los tramos en z que cruzan pistas grabadas van por B.Cu o In2 (0.5–0.8 mm de profundidad).
- El DRC de KiCad no puede detectar cortos entre espiras porque toda la bobina es una sola red. `gen_pcbs.py` hace una comprobación geométrica propia entre todos los segmentos no contiguos de cada capa y entre vías y segmentos: separación mínima encontrada 0.127 mm, 0 violaciones.

### 2.2 Stackup pedido

4 capas, 0.8 mm total, cobre exterior 35 µm, interior 17.5 µm, FR4 Tg estándar, máscara en ambas caras, ENIG, serigrafía solo en cara B. La construcción interna (preimpregnado ≈ 0.2 mm / núcleo ≈ 0.27 mm) es la típica de fabricantes de prototipos y **no está verificada** contra un fabricante concreto; solo afecta a la capacitancia entre capas y a la profundidad de In1, ninguna crítica.

### 2.3 Posiciones de montaje

- **P1** (pasadores en los taladros inferiores): S1 sobre pista 1, S2 sobre pista 2.
- **P2** (cupón desplazado 3.30 mm hacia −z): S1 sobre pista 2, S2 a 13.66 mm (pista 3 nominal 13.92: queda 0.26 mm descentrado, dentro del ancho grabado).
- Sin pasadores: ajuste libre ±2.6 mm con las ranuras M3 y la escala de 0.5 mm serigrafiada, para las pruebas de desalineación.

### 2.4 Variantes de ensamblaje (misma PCB)

Con 5 PCBs del pedido mínimo hay 10 sitios. Propuesta de primera tanda:

| Variante | Entrehierro | Circuito magnético | Hipótesis que prueba |
|---|---|---|---|
| **H-0** | — (sin cinta) | — | Control: captación directa de las bobinas y ruido de fondo. Todo lo que se mida aquí no es señal del cabezal |
| **H-S25** | solape, Kapton 25 µm | cinta enhebrada | ¿Un entrehierro definido solo por el espesor de una película, hecho a mano, lee pista 2 y pista 1? |
| **H-S12** | solape, Kapton 12.5 µm | cinta enhebrada | Sensibilidad al espesor del separador |
| **H-B** | a tope: ranura cortada in situ | cinta enhebrada | ¿Cuánto mejora un entrehierro coplanar (mejor resolución y eficiencia según el modelo) y qué ancho real se consigue con cada método de corte? |
| **H-P** | a tope o solape | polos en cara F + yugo en cara B, **sin enhebrar** (0.8 mm de FR4 entre ambos) | ¿Basta el acoplamiento a través de la PCB? Es la única variante compatible con colocación automática de preformas |

Variables secundarias a registrar por unidad: material y espesor de la cinta, longitud de solape medida, ancho de la cinta, con/sin cinta antidesgaste.

### 2.5 Materiales magnéticos

| Material | Estado | Uso |
|---|---|---|
| Lámina MuMETAL recocida 0.002" (50 µm), Magnetic Shield Corp. MU002-8, hoja 8" × 12" | Listada en Digi-Key | **Material base de rev A** por disponibilidad |
| Cinta amorfa de cobalto Metglas 2714A, 18 µm | Preferida técnicamente (µ alta sin recocido, magnetostricción ≈ 0, dura); **no se encontró canal de compra en cantidad pequeña** — pedir muestra al fabricante | Segunda tanda o en paralelo si llega |
| Película Kapton HN sin adhesivo 12.5 y 25 µm | Varios proveedores | Separador del entrehierro |

La cinta de Kapton con adhesivo no sirve como separador: el adhesivo de silicona añade ~35 µm blandos y no controlados.

### 2.6 Procedimiento de ensamblaje — variante H-S (solape, enhebrada)

Herramienta: lupa o microscopio estereoscópico (≥ 20×, con retícula o cámara calibrada), cúter con hoja nueva o guillotina, regla de acero, placa de vidrio, pinzas planas, cianoacrilato de baja viscosidad o epoxi de curado lento, hisopos, alcohol isopropílico, mordaza con dos bloques planos y película antiadherente (PTFE o poliéster siliconado), micrómetro.

1. **Cortar la tira.** Sobre vidrio, con regla de acero, cortar una tira de 1.5–2.0 mm de ancho y ≈ 40 mm de largo. Un solo pase firme; descartar tiras con rebaba visible o arrugas. Medir el ancho real (±0.05 mm) y anotarlo. No tocar con los dedos la zona de los polos.
2. **Preparar el borde de lectura.** Uno de los extremos será el borde superior del solape: cortarlo perpendicular a la tira con hoja nueva, apoyando la tira entre dos portaobjetos. Inspeccionar al microscopio: el borde debe ser recto dentro de ±10 µm a lo ancho de la tira y sin rebaba hacia el lado de la tarjeta. Si hay rebaba, repetir.
3. **Enhebrar.** Con la cara F hacia arriba: bajar un extremo por la ranura izquierda, pasarlo por la cara B y subirlo por la ranura derecha. Quedan dos extremos en la cara F apuntando al centro. Dobleces a 90° con radio amplio (no marcar el pliegue con la pinza). En mu-metal cada doblez degrada la permeabilidad local: es parte de lo que se mide.
4. **Fijar el polo inferior.** Pegar a la cara F el extremo que queda debajo en el solape (el que no es el borde de lectura), con una película mínima de adhesivo; debe sobrepasar la línea del entrehierro (marcas de cobre) entre 0.1 y 0.3 mm. Recortar el exceso antes de pegar. Prensar entre bloques planos con película antiadherente hasta curar.
5. **Separador.** Colocar un rectángulo de Kapton (≈ 3 × 4 mm) sobre el polo inferior cubriendo la zona del entrehierro. Sin adhesivo en la zona de solape, o con la mínima cantidad posible exprimida a presión.
6. **Polo superior.** Tensar ligeramente el otro extremo, llevar su borde de lectura a la línea del entrehierro y pegarlo: adhesivo solo desde 0.5 mm del borde hacia atrás. Prensar de nuevo. La tensión de la cinta en el yugo (cara B) debe quedar justa, sin holgura; fijar el yugo a la cara B con una gota de adhesivo.
7. **Medir y registrar** (hoja de ensamblaje, una por sitio): ancho de cinta, longitud de solape (microscopio), rectitud del borde, espesor total sobre la cara F en el entrehierro (micrómetro o comparador), desalineación del borde respecto a las marcas, fotos.
8. **Comprobación eléctrica.** R en continua entre N y P (esperado ≈ 12 Ω; fuera de 9–16 Ω indica defecto de fabricación de la PCB) e inductancia a 1 kHz y 10 kHz antes y después de montar la cinta. El incremento de L con la cinta da una estimación independiente de la reluctancia total del circuito: `ΔL ≈ N²/R_total`.
9. **Cinta antidesgaste (opcional, registrar):** película de 12.5 µm de Kapton o cinta de PTFE fina sobre la zona de contacto. Cuesta ≈ 5.6 dB en T1-unos por cada 12.5 µm.

### 2.7 Variante H-B (entrehierro a tope)

1. Enhebrar y pegar una tira continua que cruza la línea del entrehierro (pasos 1, 3 y prensado; adhesivo en toda la zona central).
2. Cortar el entrehierro **después de pegar**, sobre la línea marcada. Métodos, en orden de preferencia; registrar cuál se usa y el ancho obtenido:
   - marcadora láser de fibra o UV (corte de 20–50 µm de ancho típico, a verificar con la máquina disponible; probar parámetros en un retal pegado sobre FR4);
   - preforma fotograbada o cortada por láser por un proveedor de grabado químico o de esténciles, con la ranura ya hecha y puentes de sujeción fuera del ancho de lectura que se cortan tras pegar;
   - cuchilla con guía (método de referencia, ancho y rebaba poco controlados).
3. Verificar al microscopio que la ranura atraviesa todo el ancho de la cinta (cualquier puente metálico es un cortocircuito magnético: un puente de 0.2 mm de ancho ya deriva la mayor parte del flujo) y medir su ancho en 3 puntos.

### 2.8 Variante H-P (sin enhebrar)

Dos polos planos en la cara F que terminan sobre el centro de cada bobina (cubriendo la ranura, área ≥ 2.5 × 2.5 mm) y un yugo plano en la cara B que une ambos centros. Entrehierro a tope o por solape como arriba. No hay dobleces.

### 2.9 Tolerancias

| Magnitud | Alcanzable con PCB convencional | Requiere proceso adicional |
|---|---|---|
| Posición de taladros y ranuras | ±0.075–0.1 mm (típico) | — |
| Canto fresado (guía) respecto a taladros | ±0.1–0.2 mm | — |
| Registro lateral cabezal–pista (cadena completa) | ≈ ±0.3 mm; margen disponible ±0.65 mm (lectura 1.5 dentro de 2.8) | — |
| Espesor de placa / altura de ranura | ±10 % (±0.1 mm en 1.0 mm) | medir cada lote; ajustar con cinta de Kapton |
| Planitud de la cara F bajo los polos | relieve de cobre+máscara ≤ 40 µm; por eso no hay cobre bajo los polos | — |
| Ancho de pista mínimo | 0.10 mm (2 capas), 0.09–0.127 mm (4 capas) | < 75 µm: proceso HDI |
| **Entrehierro 12.5–50 µm** | **No** | espesor de película (solape) o corte láser/grabado (tope) |
| **Rectitud del borde de lectura ±10 µm** | **No** | corte con hoja nueva + inspección, o preforma grabada |
| **Separación banda–polo ≤ 25 µm** | **No se garantiza** | presión controlada, limpieza, superficie del polo sin rebaba; es el objeto principal del experimento |
| Azimut del entrehierro | marcas de cobre ±0.1 mm sobre 8 mm ≈ ±0.7° | con preforma grabada mejora |

Efecto del azimut **[E]**: la pérdida es `sinc(π·W·tanθ/λ)`; con W = 1.5 mm, 1° equivale a 26 µm de entrehierro añadido: aceptable para T2, apreciable en T1. Se mide en la prueba T6.

## 3. Cupón A — pistas sin núcleo

Mismo contorno y montaje que H. Elementos sobre el eje z = −7.06 (pista 1 en P1, pista 2 en P2):

| Elemento | Geometría | Hipótesis |
|---|---|---|
| A1 | 1 pista de 0.10 mm, sin máscara (ENIG), 3.8 mm de largo, retorno por B.Cu | Amplitud absoluta por conductor → Mr·δ de la banda |
| A2 | igual, **con** máscara | Pérdida por ~20–30 µm de separación adicional, medida directamente |
| A3 | 1 pista de 0.20 mm, sin máscara | Efecto del ancho del conductor (equivalente a "entrehierro") |
| A4 | meandro de 10 conductores de 0.15 mm a paso 0.3387 mm (media longitud de onda de los ceros de pista 2) | Filtro adaptado a los ceros de sincronía de pista 2: +20 dB de señal, para medir con buena SNR |

Requiere ENIG (las pistas desnudas de 0.10 mm no deben quedar con HASL). El contacto cobre–banda desgasta: es un instrumento de laboratorio, no un cabezal.

## 4. Banco

| Elemento | Valor |
|---|---|
| Base | 120 × 44 mm, FR4 1.0 mm; cara F sin cobre ni serigrafía (superficie de deslizamiento) |
| Separador/guía | 120 × 14 mm, FR4 1.0 mm → ranura nominal 1.00 mm para tarjeta de 0.76 mm |
| Fijación | 5 tornillos M3 en z = +7; 2 pasadores Ø2.0 en (x = ±26, z = +3) |
| Lengüetas de presión | 2, bajo cada sitio; 20 mm de raíz a punto de presión, 5 mm de ancho, canal fresado de 1.2 mm; rigidez estimada 3.4 N/mm (E = 22 GPa supuesto) — **calibrar con báscula** |
| Pad de presión | apilado de cinta UHMW-PE o PTFE en el punto marcado "PAD", con rampa hacia la entrada; altura a ajustar para 0.5–1.5 N |
| Compuertas ópticas | 2 × Everlight ITR8307 en montaje inverso (cuerpo en la cara B, mira hacia arriba por un recorte de 3.7 × 3.6 mm), a x = −55 y −35 (20.00 mm), z = −19; resistencia de LED 150 Ω; colector con pull-up en el MCU |

Orden de montaje: base → pasadores → separador → cupón (cara F hacia abajo) → tornillos M3 con arandela y tuerca; separadores hexagonales de ≥ 5 mm bajo la base para librar los componentes.

Ajuste de la presión: con la tarjeta dentro y el cupón montado, la lengüeta debe flectar entre 0.15 y 0.45 mm. Medir la fuerza empujando la lengüeta con una báscula de precisión hasta la misma flecha.

## 5. Presupuesto de espesor (para no confundir cotas)

| Concepto | Valor |
|---|---|
| "Altura de cabezal" en esta arquitectura | 0.8 mm de PCB + 0.02–0.10 mm de cinta = **≈ 0.9 mm**; no hay cuerpo que sobresalga |
| Espacio para la tarjeta | 1.00 mm nominal (0.76 de tarjeta + holgura); una tarjeta con relieve necesita más o un lado elástico |
| Placa opuesta (presión) | 1.0 mm |
| **Apilado del banco sin componentes** | **2.8 mm** |
| Espesor final de un dispositivo | 2.8 mm + componentes de la cara exterior (o alojados fuera de la zona de ranura) + batería + carcasa: **no determinado**; no se promete |
| Referencia: cabezales comerciales | "perfil bajo" de 3–5 mm de cuerpo más su muelle **[H\*]** |
