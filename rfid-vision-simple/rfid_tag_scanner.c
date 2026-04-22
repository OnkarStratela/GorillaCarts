// RFID Tag Scanner - Scans and saves unique tags to CSV (with resume support)
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

#define MAX_ID_LENGTH 64
#define MAX_TAGS 2500

// ANSI color codes
#define GREEN "\033[0;32m"
#define YELLOW "\033[0;33m"
#define CYAN "\033[0;36m"
#define RESET "\033[0m"

volatile int running = 0;

// Store unique tags
char unique_tags[MAX_TAGS][2 * MAX_ID_LENGTH + 1];
int tag_count = 0;

static bool onError(CAENRFIDErrorCodes ec) {
    if (ec != CAENRFID_StatusOK) {
        printf("ERROR (%d)\n", ec);
        return true;
    }
    return false;
}

static void printHex(uint8_t* vect, uint16_t length, char* result) {
    for (int i = 0; i < length; i++) {
        sprintf(result + (i * 2), "%02X", vect[i]);
    }
    result[length * 2] = '\0';
}

static void handle_sigint(int sig) {
    printf("\n\n%s[SCANNER] Stopping...%s\n", YELLOW, RESET);
    running = 0;
}

// Check if tag already exists
static bool tag_exists(const char* tag) {
    for (int i = 0; i < tag_count; i++) {
        if (strcmp(unique_tags[i], tag) == 0) {
            return true;
        }
    }
    return false;
}

// Load existing tags from CSV
static void load_from_csv() {
    FILE* csv = fopen("scanned_tags.csv", "r");
    if (csv == NULL) {
        printf("%s[CSV] No existing file found. Starting fresh.%s\n", YELLOW, RESET);
        return;
    }
    
    char line[256];
    
    // Skip header
    fgets(line, sizeof(line), csv);
    
    // Read all existing tags
    while (fgets(line, sizeof(line), csv) != NULL) {
        int num;
        char tag[2 * MAX_ID_LENGTH + 1];
        
        if (sscanf(line, "%d,%s", &num, tag) == 2) {
            // Remove newline if present
            tag[strcspn(tag, "\n\r")] = 0;
            
            if (tag_count < MAX_TAGS) {
                strcpy(unique_tags[tag_count], tag);
                tag_count++;
            }
        }
    }
    
    fclose(csv);
    
    if (tag_count > 0) {
        printf("%s[CSV] Loaded %d existing tags from scanned_tags.csv%s\n", GREEN, tag_count, RESET);
        printf("%s[CSV] Will continue from tag #%d%s\n", GREEN, tag_count + 1, RESET);
    }
}

// Save all tags to CSV
static void save_to_csv() {
    FILE* csv = fopen("scanned_tags.csv", "w");
    if (csv == NULL) {
        printf("ERROR: Could not create CSV file!\n");
        return;
    }
    
    fprintf(csv, "Number,Tag_ID\n");
    for (int i = 0; i < tag_count; i++) {
        fprintf(csv, "%d,%s\n", i + 1, unique_tags[i]);
    }
    
    fclose(csv);
    printf("%s[CSV] Saved %d tags to scanned_tags.csv%s\n", GREEN, tag_count, RESET);
}

int main() {
    CAENRFIDErrorCodes ec;
    CAENRFIDReader reader = {
        .connect = _connect,
        .disconnect = _disconnect,
        .tx = _tx,
        .rx = _rx,
        .clear_rx_data = _clear_rx_data,
        .enable_irqs = _enable_irqs,
        .disable_irqs = _disable_irqs
    };
    
    RS232_params port_params = {
        .com = "/dev/ttyACM0",
        .baudrate = 921600,
        .dataBits = 8,
        .stopBits = 1,
        .parity = 0,
        .flowControl = 0,
    };
    
    char model[64], serial[64], source[32] = "Source_0";
    int power = 316;
    int tags_before_session;
    
    signal(SIGINT, handle_sigint);
    
    printf("%s===== RFID TAG SCANNER =====%s\n", CYAN, RESET);
    printf("Max capacity: %d tags\n\n", MAX_TAGS);
    
    // Load existing tags from previous session
    load_from_csv();
    tags_before_session = tag_count;
    
    // Connect to reader
    printf("\n[SCANNER] Connecting to reader...\n");
    ec = CAENRFID_Connect(&reader, CAENRFID_RS232, &port_params);
    if (onError(ec)) {
        printf("[SCANNER] Failed to connect!\n");
        printf("  - Check USB connection\n");
        printf("  - Try: sudo chmod 666 /dev/ttyACM0\n");
        return -1;
    }
    
    ec = CAENRFID_GetReaderInfo(&reader, model, serial);
    if (ec == CAENRFID_StatusOK) {
        printf("[SCANNER] Reader: %s, Serial: %s\n", model, serial);
    }
    
    ec = CAENRFID_SetPower(&reader, power);
    printf("[SCANNER] Power set to %d mW\n\n", power);
    
    // Wait for user to start
    printf("%sPress ENTER to start scanning...%s", YELLOW, RESET);
    getchar();
    
    printf("\n%s[SCANNER] Scanning started! Press Ctrl+C to stop.%s\n\n", GREEN, RESET);
    
    running = 1;
    
    // Main scanning loop
    while (running) {
        CAENRFIDTagList *tags = NULL, *aux;
        uint16_t numTags = 0;
        
        ec = CAENRFID_InventoryTag(&reader, source, 0, 0, 0, 
                                   NULL, 0, RSSI, &tags, &numTags);
        
        if (ec == CAENRFID_StatusOK && numTags > 0) {
            aux = tags;
            while (aux != NULL) {
                char epcStr[2 * MAX_ID_LENGTH + 1];
                printHex(aux->Tag.ID, aux->Tag.Length, epcStr);
                
                // Check if this is a new unique tag
                if (!tag_exists(epcStr)) {
                    if (tag_count < MAX_TAGS) {
                        strcpy(unique_tags[tag_count], epcStr);
                        tag_count++;
                        
                        // Display in green with count
                        printf("%s[%d] %s%s\n", GREEN, tag_count, epcStr, RESET);
                    } else {
                        printf("%s[WARNING] Max capacity reached!%s\n", YELLOW, RESET);
                        running = 0;
                        break;
                    }
                }
                
                CAENRFIDTagList *next = aux->Next;
                free(aux);
                aux = next;
            }
        }
        
        usleep(25000);  // 25ms scan rate
    }
    
    // Disconnect
    CAENRFID_Disconnect(&reader);
    
    // Save to CSV
    printf("\n");
    save_to_csv();
    
    // Final summary
    printf("\n%s===== SCAN COMPLETE =====%s\n", CYAN, RESET);
    printf("Tags from previous session: %d\n", tags_before_session);
    printf("New tags this session: %d\n", tag_count - tags_before_session);
    printf("Total unique tags: %d\n", tag_count);
    printf("Saved to: scanned_tags.csv\n");
    
    return 0;
}