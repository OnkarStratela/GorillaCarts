CC = gcc
CFLAGS = -Wall -O2 -pthread
LDFLAGS = -lCAENRFIDLib_Light -lpthread -lm
TARGET = rfid_reader_ipc
SRC = src/rfid_reader_ipc.c

all: $(TARGET)

$(TARGET): $(SRC)
	@echo "Checking for CAEN library headers..."
	@if [ ! -f "src/CAENRFIDLib_Light.h" ] || [ ! -f "src/host.h" ]; then \
		echo "Error: CAEN headers not found in src/"; \
		echo "Copy CAENRFIDLib_Light.h and host.h to src/ directory"; \
		echo "Run: ./install_caen.sh for help"; \
		exit 1; \
	fi
	@echo "Compiling RFID reader..."
	$(CC) $(CFLAGS) -o $(TARGET) $(SRC) $(LDFLAGS)
	@echo "Compilation complete: $(TARGET)"

clean:
	rm -f $(TARGET)
	rm -rf output/matched/* output/unmatched/* logs/*.log

setup: install
	@echo "Running system setup..."
	./setup.sh

install:
	mkdir -p output/matched output/unmatched logs
	chmod +x scripts/*.sh setup.sh install_caen.sh
	@echo "Installation complete"

run: all
	./scripts/run_system.sh

test:
	python3 scripts/test_ipc.py

check:
	@echo "Checking system requirements..."
	@echo "Python3: $$(python3 --version 2>/dev/null || echo 'Not found')"
	@echo "OpenCV: $$(python3 -c 'import cv2; print(cv2.__version__)' 2>/dev/null || echo 'Not installed')"
	@echo "NumPy: $$(python3 -c 'import numpy; print(numpy.__version__)' 2>/dev/null || echo 'Not installed')"
	@echo "CAEN Library: $$(ldconfig -p | grep libCAENRFIDLib_Light || echo 'Not installed')"
	@echo "CAEN Headers: $$(if [ -f 'src/CAENRFIDLib_Light.h' ] && [ -f 'src/host.h' ]; then echo 'Found'; else echo 'Missing'; fi)"

help:
	@echo "Available targets:"
	@echo "  all     - Compile the RFID reader (default)"
	@echo "  clean   - Remove compiled files and output"
	@echo "  setup   - Run complete system setup"
	@echo "  install - Create directories and set permissions"
	@echo "  run     - Start the complete system"
	@echo "  test    - Test IPC communication"
	@echo "  check   - Check system requirements"
	@echo "  help    - Show this help message"

.PHONY: all clean setup install run test check help