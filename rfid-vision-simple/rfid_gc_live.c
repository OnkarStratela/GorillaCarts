// rfid_gc_live.c
// Live state RFID scanner - prints current tags in range each scan cycle.
// Output format:
//   []                        <- nothing in range
//   [tagcode]                 <- one tag in range
//   [tagcode,tagcode2]        <- multiple tags in range
//
// Unlike the event-based scanners, this re-evaluates on every cycle
// and prints the full current array, so removing a tag from range
// will reflect immediately.

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <stdbool.h>
#include <time.h>
#include <unistd.h>
#include <signal.h>

#include "CAENRFIDLib_Light.h"
#include "host.h"

// ── Configuration ────────────────────────────────────────────────────────────
#define GC_PORT          "/dev/ttyACM0"   // change to /dev/ttyUSB0 if needed
#define GC_BAUDRATE      921600
#define GC_POWER         316              // mW - lower = shorter range
#define GC_SCAN_MS       100              // ms between each scan cycle
#define GC_MAX_TAGS      64               // max tags visible in one cycle
#define MAX_ID_LENGTH    64
// ─────────────────────────────────────────────────────────────────────────────

// ANSI colours
#define GREEN  "\033[0;32m"
#define YELLOW "\033[0;33m"
#define CYAN   "\033[0;36m"
#define RESET  "\033[0m"

volatile int running = 0;

// ── Helpers ──────────────────────────────────────────────────────────────────

static void hex_str(uint8_t *bytes, uint16_t len, char *out) {
    for (int i = 0; i < len; i++)
        sprintf(out + (i * 2), "%02X", bytes[i]);
    out[len * 2] = '\0';
}

static void handle_sigint(int sig) {
    (void)sig;
    printf("\n" YELLOW "[GC] Stopping..." RESET "\n");
    running = 0;
}

// Print the current tag array in the requested format.
// []  /  [A]  /  [A,B,C]
static void print_tag_array(char tags[][2 * MAX_ID_LENGTH + 1], int count) {
    printf(GREEN "[");
    for (int i = 0; i < count; i++) {
        if (i > 0) printf(",");
        printf("%s", tags[i]);
    }
    printf("]" RESET "\n");
}

// ── Main ─────────────────────────────────────────────────────────────────────

int main(void) {

    CAENRFIDErrorCodes ec;
    CAENRFIDReader reader = {
        .connect        = _connect,
        .disconnect     = _disconnect,
        .tx             = _tx,
        .rx             = _rx,
        .clear_rx_data  = _clear_rx_data,
        .enable_irqs    = _enable_irqs,
        .disable_irqs   = _disable_irqs
    };

    RS232_params port_params = {
        .com         = GC_PORT,
        .baudrate    = GC_BAUDRATE,
        .dataBits    = 8,
        .stopBits    = 1,
        .parity      = 0,
        .flowControl = 0,
    };

    char source[32] = "Source_0";
    char model[64]  = {0};
    char serial[64] = {0};

    signal(SIGINT, handle_sigint);

    printf(CYAN "===== GC RFID Live State Scanner =====" RESET "\n");
    printf("Port   : %s @ %d baud\n", GC_PORT, GC_BAUDRATE);
    printf("Power  : %d mW\n", GC_POWER);
    printf("Cycle  : %d ms\n\n", GC_SCAN_MS);

    // ── Connect ───────────────────────────────────────────────────────────────
    printf("[GC] Connecting...\n");
    ec = CAENRFID_Connect(&reader, CAENRFID_RS232, &port_params);
    if (ec != CAENRFID_StatusOK) {
        printf("[GC] ERROR: Could not connect (code %d)\n", ec);
        printf("  - Check USB cable\n");
        printf("  - Try: sudo chmod 666 %s\n", GC_PORT);
        printf("  - Or:  sudo usermod -a -G dialout $USER  (then re-login)\n");
        return -1;
    }

    ec = CAENRFID_GetReaderInfo(&reader, model, serial);
    if (ec == CAENRFID_StatusOK)
        printf("[GC] Reader: %s  Serial: %s\n", model, serial);

    CAENRFID_SetPower(&reader, GC_POWER);
    printf("[GC] Ready. Press Ctrl+C to stop.\n\n");

    // ── Scan loop ─────────────────────────────────────────────────────────────
    running = 1;

    // Storage for tags visible in the current cycle
    char current_tags[GC_MAX_TAGS][2 * MAX_ID_LENGTH + 1];
    int  current_count = 0;

    // Track previous printout so we only re-print when state changes.
    // Remove this block and always call print_tag_array() if you prefer
    // a continuous scrolling output every cycle regardless of change.
    char prev_tags[GC_MAX_TAGS][2 * MAX_ID_LENGTH + 1];
    int  prev_count = -1;   // -1 forces first print

    while (running) {

        CAENRFIDTagList *tag_list = NULL, *node;
        uint16_t num_tags = 0;
        current_count = 0;

        // Single inventory round with RSSI data
        ec = CAENRFID_InventoryTag(&reader, source,
                                   0, 0, 0,        // no mask
                                   NULL, 0,
                                   RSSI,
                                   &tag_list, &num_tags);

        if (ec == CAENRFID_StatusOK && num_tags > 0) {
            node = tag_list;
            while (node != NULL && current_count < GC_MAX_TAGS) {
                hex_str(node->Tag.ID, node->Tag.Length,
                        current_tags[current_count]);
                current_count++;

                CAENRFIDTagList *next = node->Next;
                free(node);
                node = next;
            }
            // Free any remaining nodes if we hit GC_MAX_TAGS
            while (node != NULL) {
                CAENRFIDTagList *next = node->Next;
                free(node);
                node = next;
            }
        }
        // On any other error code the list is empty - that is intentional:
        // a failed scan means nothing is confidently in range.

        // ── Print only when state has changed ─────────────────────────────────
        bool changed = (current_count != prev_count);
        if (!changed) {
            for (int i = 0; i < current_count; i++) {
                if (strcmp(current_tags[i], prev_tags[i]) != 0) {
                    changed = true;
                    break;
                }
            }
        }

        if (changed) {
            print_tag_array(current_tags, current_count);

            // Save current state as previous
            prev_count = current_count;
            for (int i = 0; i < current_count; i++)
                strcpy(prev_tags[i], current_tags[i]);
        }

        usleep(GC_SCAN_MS * 1000);
    }

    // ── Cleanup ───────────────────────────────────────────────────────────────
    CAENRFID_Disconnect(&reader);
    printf("[GC] Disconnected.\n");
    return 0;
}
