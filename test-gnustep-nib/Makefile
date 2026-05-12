CC = gcc
CFLAGS = -fobjc-exceptions -std=gnu99 -pthread -fexceptions
LIBS = -lgnustep-gui -lgnustep-base -lobjc -lm
FRAMEWORKS = -rdynamic

all: MakeModel TestModel

MakeModel: make_model.m
	$(CC) $(CFLAGS) $(FRAMEWORKS) -o $@ $< $(LIBS)

TestModel: main.m Model.gmodel
	$(CC) $(CFLAGS) $(FRAMEWORKS) -o $@ $< $(LIBS)

Model.gmodel: MakeModel
	./MakeModel

run: TestModel
	./TestModel

clean:
	rm -f MakeModel TestModel Model.gmodel
