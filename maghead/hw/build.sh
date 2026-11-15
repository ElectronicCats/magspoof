#!/bin/sh
# Regenera PCBs, las pasa por KiCad 9 (contenedor), corre DRC y exporta vistas. Uso: sh build.sh
set -e
cd "$(dirname "$0")"
python3 gen_pcbs.py > /dev/null
chmod -R a+rwX .
B="coupon_H/maghead_H coupon_A/maghead_A fixture/maghead_base fixture/maghead_spacer"
K="docker run --rm -v $PWD/..:/work -w /work/hw kicad/kicad:9.0"
$K python3 kicad_post.py $(for b in $B; do echo $b.kicad_pcb; done) 2>&1 | grep -v Debug
for b in $B; do
  $K kicad-cli pcb drc --severity-all --format json --units mm -o $b.drc.json $b.kicad_pcb 2>&1 | grep -v Debug | tail -1
  d=$(dirname $b); n=$(basename $b)
  L="F.Cu,B.Cu,Edge.Cuts,B.SilkS,F.SilkS"; [ $n = maghead_H ] && L="F.Cu,In1.Cu,In2.Cu,B.Cu,Edge.Cuts"
  $K kicad-cli pcb export svg --layers $L --mode-single --page-size-mode 2 --exclude-drawing-sheet -o $d/$n.svg $b.kicad_pcb 2>&1 | grep -v Debug | tail -1
done
# Archivos de fabricacion (candidatos rev A; ver docs/05 antes de ordenar)
for b in $B; do
  d=$(dirname $b); n=$(basename $b); mkdir -p $d/fab_$n; rm -f $d/fab_$n/*; chmod a+rwx $d/fab_$n
  L="F.Cu,B.Cu,F.Mask,B.Mask,F.SilkS,B.SilkS,B.Paste,Edge.Cuts"; [ $n = maghead_H ] && L="F.Cu,In1.Cu,In2.Cu,B.Cu,F.Mask,B.Mask,F.SilkS,B.SilkS,Edge.Cuts"
  $K kicad-cli pcb export gerbers --layers $L --subtract-soldermask --no-protel-ext -o $d/fab_$n/ $b.kicad_pcb 2>&1 | grep -v Debug | tail -1
  $K kicad-cli pcb export drill --format excellon --drill-origin absolute --excellon-units mm --generate-map --map-format gerberx2 -o $d/fab_$n/ $b.kicad_pcb 2>&1 | grep -v Debug | tail -1
  (cd $d/fab_$n && zip -q -r ../${n}_revA_gerbers.zip .)
done
chmod -R a+rwX .
