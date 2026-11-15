# maghead_capture - firmware de adquisicion (Pico 2 / RP2350; compatible con Pico / RP2040)
#
#   export PICO_SDK_PATH=/ruta/a/pico-sdk          (SDK >= 2.0 para RP2350)
#   cp $PICO_SDK_PATH/external/pico_sdk_import.cmake .
#   cmake -B build -DPICO_BOARD=pico2 && cmake --build build      (Pico 2)
#   cmake -B build -DPICO_BOARD=pico  && cmake --build build      (Pico / RP2040)
#
# NOTA: pico_sdk_import.cmake NO esta en este repositorio (viene con el SDK); hay que
# copiarlo aqui como se indica arriba. No se ha podido compilar para el objetivo en el
# entorno donde se escribio (sin acceso al SDK): ver ../README.md.
cmake_minimum_required(VERSION 3.13)

if(NOT DEFINED PICO_BOARD)
    set(PICO_BOARD pico2 CACHE STRING "Placa")
endif()

include(pico_sdk_import.cmake)

project(maghead_capture C CXX ASM)
set(CMAKE_C_STANDARD 11)

pico_sdk_init()

add_executable(maghead_capture
    main.c
    ../common/f2f_decode.c
    ../common/mh_proto.c
)

pico_generate_pio_header(maghead_capture ${CMAKE_CURRENT_LIST_DIR}/dig_sample.pio)

target_include_directories(maghead_capture PRIVATE ${CMAKE_CURRENT_LIST_DIR}/../common)

target_compile_options(maghead_capture PRIVATE -Wall -Wextra -O2)

# Fase 2 (decodificacion en placa): 0 para quitarla y ahorrar ~85 kB de RAM.
target_compile_definitions(maghead_capture PRIVATE
    MH_ENABLE_DECODE=1
    PICO_STDIO_USB_STDOUT_TIMEOUT_US=100000
)

target_link_libraries(maghead_capture
    pico_stdlib
    hardware_adc
    hardware_dma
    hardware_pio
    hardware_irq
    hardware_clocks
    hardware_sync
)

pico_enable_stdio_usb(maghead_capture 1)
pico_enable_stdio_uart(maghead_capture 0)
pico_add_extra_outputs(maghead_capture)
