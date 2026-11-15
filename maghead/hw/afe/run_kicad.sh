#!/bin/sh
# Ejecuta kicad-cli 9 (docker) dentro de hw/afe. Uso: ./run_kicad.sh sch erc ...
# Instala las tablas globales de librerias de stock (la imagen arranca sin
# configuracion de usuario) para que el ERC pueda comparar simbolos/huellas.
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
exec docker run --rm --user 0 -v "$ROOT":/work -w /work/hw/afe kicad/kicad:9.0 sh -c '
  mkdir -p "$HOME/.config/kicad/9.0" &&
  cp /usr/share/kicad/template/sym-lib-table /usr/share/kicad/template/fp-lib-table "$HOME/.config/kicad/9.0/" &&
  kicad-cli "$@"' kicad-cli "$@"
