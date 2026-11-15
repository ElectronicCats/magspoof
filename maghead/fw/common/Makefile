# Compilacion y pruebas EN HOST de los modulos portables (f2f_decode, mh_proto).
#   make            -> build/test_host y build/libf2f_host.so (para Python/ctypes)
#   make test       -> pruebas unitarias internas (selftest)
#   make asan       -> selftest con AddressSanitizer + UBSan
CC ?= gcc
CFLAGS ?= -std=c99 -O2 -Wall -Wextra -Wshadow -Wconversion -Wno-sign-conversion -Werror
SRC = f2f_decode.c mh_proto.c host_api.c
B = build

all: $(B)/test_host $(B)/libf2f_host.so

$(B)/test_host: $(SRC) test_host.c f2f_decode.h mh_proto.h
	@mkdir -p $(B)
	$(CC) $(CFLAGS) -o $@ $(SRC) test_host.c

$(B)/libf2f_host.so: $(SRC) f2f_decode.h mh_proto.h
	@mkdir -p $(B)
	$(CC) $(CFLAGS) -fPIC -shared -o $@ $(SRC)

$(B)/test_host_asan: $(SRC) test_host.c f2f_decode.h mh_proto.h
	@mkdir -p $(B)
	$(CC) -std=c99 -O1 -g -Wall -Wextra -fsanitize=address,undefined -fno-sanitize-recover=all -o $@ $(SRC) test_host.c

test: $(B)/test_host
	$(B)/test_host selftest

asan: $(B)/test_host_asan
	$(B)/test_host_asan selftest

clean:
	rm -rf $(B)

.PHONY: all test asan clean
