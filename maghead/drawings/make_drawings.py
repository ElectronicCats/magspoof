#!/usr/bin/env python3
"""Dibujos de seccion y ensamblaje con cotas (SVG editable + PNG). Cotas en mm salvo indicacion.
Las secciones 1 y 3 tienen escala vertical exagerada (indicado en cada dibujo)."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Polygon

def dim(ax, p1, p2, txt, off=0.0, vertical=False, fs=7, color="k"):
    ax.annotate("", xy=p1, xytext=p2, arrowprops=dict(arrowstyle="<->", lw=0.7, color=color, shrinkA=0, shrinkB=0))
    mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
    if vertical: ax.text(mx + off, my, txt, fontsize=fs, va="center", ha="left", color=color)
    else: ax.text(mx, my + off, txt, fontsize=fs, va="bottom", ha="center", color=color)

def note(ax, xy, xytext, txt, fs=7):
    ax.annotate(txt, xy=xy, xytext=xytext, fontsize=fs, arrowprops=dict(arrowstyle="-", lw=0.5), va="center")

C = dict(fr4="#c9d7a0", cu="#c87533", card="#f2f2f2", stripe="#3b2a1a", foil="#5a6f8f", kap="#e0a020", pad="#9ad0e6", steel="#888")

# ---------------------------------------------------------------- 1. seccion longitudinal (plano x-y por el eje de pista)
VS = 4.0   # exageracion vertical
fig, ax = plt.subplots(figsize=(13, 6.2))
y = 0.0
def layer(x1, x2, t, col, **kw):
    global y
    ax.add_patch(Rectangle((x1, y * VS), x2 - x1, t * VS, fc=col, ec="k", lw=0.5, **kw)); y0 = y; y += t; return y0
# base con lengueta
ax.add_patch(Rectangle((-30, 0), 22.5, 1.0 * VS, fc=C["fr4"], ec="k", lw=0.5))
ax.add_patch(Rectangle((3.2, 0), 26.8, 1.0 * VS, fc=C["fr4"], ec="k", lw=0.5))
ax.add_patch(Polygon([(-20, 0), (2, 0.20 * VS), (2, 1.20 * VS), (-20, 1.0 * VS)], fc="#b4c98a", ec="k", lw=0.5))
ax.text(-27, 0.5 * VS, "BASE FR4 1.0", fontsize=7, va="center")
ax.text(-15, 0.52 * VS, "lengueta (flexion) k~3.4 N/mm (est.)", fontsize=6.5, va="center", rotation=2.5)
# pad de presion
ax.add_patch(Polygon([(-3.5, 1.15 * VS), (-2.0, 1.60 * VS), (2.0, 1.63 * VS), (2.0, 1.20 * VS)], fc=C["pad"], ec="k", lw=0.5))
note(ax, (0.5, 1.4 * VS), (8, 0.55 * VS), "pad de presion: capas de cinta UHMW-PE/PTFE\naltura ajustable ~0.4-0.7 mm, con rampa de entrada")
# tarjeta (levantada por el pad contra el cabezal)
yc = 1.72
ax.add_patch(Rectangle((-30, yc * VS), 60, 0.76 * VS, fc=C["card"], ec="k", lw=0.5))
ax.add_patch(Rectangle((-30, (yc + 0.76 - 0.012) * VS), 60, 0.012 * VS, fc=C["stripe"], ec="none"))
ax.text(-27, (yc + 0.38) * VS, "TARJETA ID-1  0.76 (banda arriba)", fontsize=7, va="center")
ax.annotate("deslizamiento  x", xy=(27, (yc + 0.38) * VS), xytext=(14, (yc + 0.38) * VS), fontsize=7, va="center", arrowprops=dict(arrowstyle="->"))
# cinta magnetica (polos sobre cara F del cupon) y cupon
yf = yc + 0.76            # superficie de la banda = cara inferior de la cinta
tf_ = 0.06                # cinta + adhesivo dibujado (real 0.018-0.05)
ycp = yf + tf_            # cara F del cupon
ax.add_patch(Rectangle((-28, ycp * VS), 56, 0.8 * VS, fc=C["fr4"], ec="k", lw=0.5))
for xs in (-6, 6):
    ax.add_patch(Rectangle((xs - 0.5, ycp * VS), 1.0, 0.8 * VS, fc="w", ec="k", lw=0.5))
# cobre: 3 capas de bobina
for xs in (-6, 6):
    for (yy, lab) in ((0.25, "In1"), (0.53, "In2"), (0.765, "B.Cu")):
        for sgn in (-1, 1):
            ax.add_patch(Rectangle((xs + sgn * 0.84 if sgn > 0 else xs - 0.84 - 3.05, (ycp + yy) * VS), 3.05, 0.035 * VS, fc=C["cu"], ec="none"))
ax.text(-27.5, (ycp + 0.4) * VS, "CUPON H\nFR4 0.8, 4 capas", fontsize=7, va="center")
note(ax, (8.5, (ycp + 0.27) * VS), (16, (ycp + 1.5) * VS), "bobinas: 12 espiras x 3 capas (In1, In2, B.Cu)\nalrededor de cada ranura; 72 espiras en serie-oposicion")
# cinta: polo A (izq), baja por ranura izq, yugo por arriba (cara B), ranura der, polo B
fo = C["foil"]; t = 0.05
ax.add_patch(Rectangle((-6.3, yf * VS), 6.3 - 0.02, t * VS, fc=fo, ec="k", lw=0.3))           # polo A
ax.add_patch(Rectangle((0.02, yf * VS), 6.3 - 0.02, t * VS, fc=fo, ec="k", lw=0.3))           # polo B
for xs in (-6.3, 6.3 - 0.0):
    ax.add_patch(Rectangle((xs - (0.0 if xs < 0 else 0.25), yf * VS), 0.25, (0.8 + tf_ + t) * VS, fc=fo, ec="k", lw=0.3))
ax.add_patch(Rectangle((-6.3, (ycp + 0.8) * VS), 12.6, t * VS, fc=fo, ec="k", lw=0.3))        # yugo en cara B
note(ax, (0, (ycp + 0.83) * VS), (-12, (ycp + 1.5) * VS), "yugo: la misma cinta, por la cara B")
note(ax, (-3.0, (yf + 0.02) * VS), (-25, (yc - 0.35) * VS), "polos: cinta magnetica blanda 18-50 um\npegada a la cara F (ver detalle del entrehierro)")
note(ax, (0, yf * VS), (4, (yc - 0.38) * VS), "ENTREHIERRO en x=0")
ax.plot([0, 0], [(yc - 0.2) * VS, (ycp + 1.2) * VS], "k-.", lw=0.4)
# cotas
dim(ax, (-6, (ycp + 1.05) * VS), (6, (ycp + 1.05) * VS), "12.0 entre ranuras (2 x Xc)", off=0.1)
dim(ax, (-6.5, (ycp + 0.95) * VS), (-5.5, (ycp + 0.95) * VS), "ranura 1.0 x 3.0", off=-0.9)
dim(ax, (29, ycp * VS), (29, (ycp + 0.8) * VS), "0.80", off=0.3, vertical=True)
dim(ax, (29, yc * VS), (29, (yc + 0.76) * VS), "0.76", off=0.3, vertical=True)
dim(ax, (29, 0), (29, 1.0 * VS), "1.00", off=0.3, vertical=True)
dim(ax, (31.5, 1.0 * VS), (31.5, ycp * VS), "ranura 1.00 nominal\n(separador; +cinta Kapton)", off=0.3, vertical=True)
dim(ax, (-20, -0.5), (0, -0.5), "20.0 (raiz de lengueta a punto de presion)", off=-1.3)
ax.set_xlim(-31, 43); ax.set_ylim(-2.5, (ycp + 1.9) * VS); ax.set_aspect("equal"); ax.axis("off")
ax.set_title("SECCION 1 - longitudinal por el eje de la pista (escala vertical x4; espesores de cinta exagerados)\n"
             "Variante H-T (cinta enhebrada). Apilado real: base 1.0 + ranura 1.0 + cupon 0.8 = 2.8 mm sin componentes ni tornillos", fontsize=9)
fig.tight_layout(); fig.savefig("seccion_1_longitudinal.svg"); fig.savefig("seccion_1_longitudinal.png", dpi=140); plt.close(fig)

# ---------------------------------------------------------------- 2. detalle de entrehierros (um, escala 1:1 en ambos ejes)
fig, axs = plt.subplots(1, 3, figsize=(14, 4.6))
def base_det(ax, title):
    ax.add_patch(Rectangle((-200, 0), 400, 60, fc=C["fr4"], ec="k", lw=0.5)); ax.text(-195, 40, "cupon: mascara + FR4 (cara F)", fontsize=7)
    ax.add_patch(Rectangle((-200, -140), 400, 12, fc=C["stripe"], ec="none")); ax.add_patch(Rectangle((-200, -200), 400, 60, fc=C["card"], ec="k", lw=0.5))
    ax.text(-195, -180, "tarjeta (capa magnetica ~10 um, NO verificado)", fontsize=7)
    ax.set_xlim(-205, 205); ax.set_ylim(-205, 75); ax.set_aspect("equal"); ax.axis("off"); ax.set_title(title, fontsize=8.5)
# (a) a tope
ax = axs[0]; base_det(ax, "(a) H-B: entrehierro a tope / ranura cortada\ng = 25 um (objetivo), cinta 18-25 um")
ax.add_patch(Rectangle((-200, -8), 400, 8, fc="#ddd", ec="none"))                       # adhesivo
ax.add_patch(Rectangle((-200, -28), 187.5, 20, fc=C["foil"], ec="k", lw=0.4)); ax.add_patch(Rectangle((12.5, -28), 187.5, 20, fc=C["foil"], ec="k", lw=0.4))
dim(ax, (-12.5, -45), (12.5, -45), "g = 25", off=-22); dim(ax, (150, -28), (150, -8), "t = 18-25", off=6, vertical=True)
dim(ax, (-150, -128), (-150, -28), "d: separacion efectiva\n(recubrimiento + rugosidad\n+ cinta antidesgaste)", off=6, vertical=True)
ax.text(-195, -3, "adhesivo 5-10 um", fontsize=6)
# (b) solape con separador
ax = axs[1]; base_det(ax, "(b) H-S: entrehierro por solape; g = espesor del separador\nKapton 12.5 o 25 um; solape objetivo <= 0.3 mm")
ax.add_patch(Rectangle((-60, -20), 260, 20, fc=C["foil"], ec="k", lw=0.4))             # lamina inferior (contra el cupon)
ax.add_patch(Rectangle((-60, -45), 260, 25, fc=C["kap"], ec="k", lw=0.4))              # separador
ax.add_patch(Rectangle((-200, -65), 200, 20, fc=C["foil"], ec="k", lw=0.4))            # lamina superior termina en x=0
ax.add_patch(Polygon([(-200, 0), (-60, 0), (-60, -45), (-200, -45)], fc="#ddd", ec="none"))
ax.text(-190, -25, "relleno/adhesivo", fontsize=6)
dim(ax, (-60, -78), (0, -78), "solape", off=-22); dim(ax, (120, -45), (120, -20), "s = 12.5 / 25", off=6, vertical=True)
ax.text(5, -62, "borde recto = linea de lectura", fontsize=6.5)
# (c) pista al aire
ax = axs[2]; base_det(ax, "(c) Cupon A: pista de cobre sin nucleo\nancho 100 um, espesor ~35 um + ENIG, sin mascara")
ax.add_patch(Rectangle((-50, -38), 100, 38, fc=C["cu"], ec="k", lw=0.4))
dim(ax, (-50, -52), (50, -52), "w = 100", off=-22); dim(ax, (80, -38), (80, 0), "~35-40", off=6, vertical=True)
ax.text(-195, -100, "la pista sobresale: contacto directo cobre/ENIG-banda", fontsize=6.5)
fig.suptitle("DETALLE 2 - geometria del entrehierro, cotas en micrometros, escala 1:1 (la separacion tarjeta-polo se dibuja abierta para acotar)", fontsize=9)
fig.tight_layout(); fig.savefig("detalle_2_entrehierros.svg"); fig.savefig("detalle_2_entrehierros.png", dpi=140); plt.close(fig)

# ---------------------------------------------------------------- 3. seccion transversal (plano z-y)
VS = 5.0
fig, ax = plt.subplots(figsize=(13, 5))
ax.add_patch(Rectangle((-30, 0), 44, 1.0 * VS, fc=C["fr4"], ec="k", lw=0.5)); ax.text(-29.5, 0.5 * VS, "BASE 1.0", fontsize=7, va="center")
ax.add_patch(Rectangle((0, 1.0 * VS), 14, 1.0 * VS, fc="#d9c9a0", ec="k", lw=0.5)); ax.text(3.2, 1.5 * VS, "SEPARADOR / GUIA 1.0", fontsize=7, va="center")
ax.add_patch(Rectangle((-18, 2.0 * VS), 32, 0.8 * VS, fc=C["fr4"], ec="k", lw=0.5)); ax.text(2, 2.4 * VS, "CUPON 0.8 (voladizo 18 mm)", fontsize=7, va="center")
ax.add_patch(Rectangle((-40, 1.2 * VS), 40, 0.76 * VS, fc=C["card"], ec="k", lw=0.5)); ax.text(-39, 1.58 * VS, "TARJETA (53.98 de ancho; sobresale)", fontsize=7, va="center")
for zc, nm, col in ((-7.06, "T1", "#b03030"), (-10.36, "T2", "#3050b0"), (-13.92, "T3", "#777")):
    ax.add_patch(Rectangle((zc - 1.4, (1.96 - 0.03) * VS), 2.8, 0.03 * VS, fc=col, ec="none"))
    ax.plot([zc, zc], [1.3 * VS, 3.5 * VS], "-.", color=col, lw=0.5); ax.text(zc, 3.55 * VS, f"{nm}\nz={zc}", fontsize=7, ha="center", color=col)
ax.add_patch(Rectangle((-7.06 - 0.75, 1.96 * VS), 1.5, 0.04 * VS, fc=C["foil"], ec="k", lw=0.3))
ax.add_patch(Rectangle((-11.2, 1.0 * VS), 5.0, 0.2 * VS, fc=C["pad"], ec="k", lw=0.4)); ax.text(-12.5, 0.75 * VS, "lengueta + pad (z=-8.7)", fontsize=6.5)
for z, lab in ((7.0, "M3"), (3.0, "pasador 2.0")):
    ax.add_patch(Rectangle((z - (1.6 if lab == "M3" else 1.0), 0), 3.2 if lab == "M3" else 2.0, 2.8 * VS, fc="none", ec=C["steel"], lw=0.8, ls="--")); ax.text(z, 2.95 * VS, lab, fontsize=6.5, ha="center")
ax.plot([0, 0], [-1, 3.3 * VS], "k-", lw=0.6); ax.text(0.2, -1.6, "z = 0  canto de referencia de la tarjeta = borde de la guia", fontsize=7)
dim(ax, (-7.81, 1.9 * VS), (-6.31, 1.9 * VS), "ancho de lectura 1.5 (cinta)", off=-1.6)
dim(ax, (-8.46, 1.25 * VS), (-5.66, 1.25 * VS), "pista grabada 2.80", off=-1.6)
dim(ax, (-10.36, 3.2 * VS), (-7.06, 3.2 * VS), "3.30", off=0.1)
dim(ax, (0, 3.0 * VS), (-18, 3.0 * VS), "", off=0.1); ax.text(-16, 3.03 * VS, "18.0 voladizo", fontsize=7)
dim(ax, (15, 1.0 * VS), (15, 2.0 * VS), "ranura 1.00", off=0.3, vertical=True)
ax.set_xlim(-41, 22); ax.set_ylim(-2.5, 4.2 * VS); ax.set_aspect("equal"); ax.axis("off")
ax.set_title("SECCION 3 - transversal (escala vertical x5). Cupon en posicion P1: sitio S1 sobre pista 1. "
             "Posicion P2 = cupon desplazado 3.30 mm hacia -z (S1 sobre pista 2)", fontsize=9)
fig.tight_layout(); fig.savefig("seccion_3_transversal.svg"); fig.savefig("seccion_3_transversal.png", dpi=140); plt.close(fig)
print("ok")
