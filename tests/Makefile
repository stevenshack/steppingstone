CC = gcc
CFLAGS = -fobjc-exceptions -std=gnu99 -pthread -fexceptions
LIBS = -lgnustep-gui -lgnustep-base -lobjc -lm
FRAMEWORKS = -rdynamic

all: CreateAndArchive

CreateAndArchive: create_and_archive.m
	$(CC) $(CFLAGS) $(FRAMEWORKS) -o $@ $< $(LIBS)

run: CreateAndArchive
	./CreateAndArchive /tmp/envelopemaker_test.gmodel 2>&1 | grep -v "^20[0-9][0-9]" || true

verify: CreateAndArchive
	./CreateAndArchive /tmp/envelopemaker_test.gmodel

clean:
	rm -f CreateAndArchive

.PHONY: all run verify clean
