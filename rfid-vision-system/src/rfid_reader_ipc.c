#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <time.h>
#include <pthread.h>
#include <signal.h>
#include <errno.h>
#include <stdint.h>
#include <stdbool.h>

#include "CAENRFIDLib_Light.h"
#include "host.h"

#define SOCKET_PATH "/tmp/rfid_vision.sock"
#define MAX_ID_LENGTH 64
#define MAX_TAGS 1024
#define RECONNECT_DELAY 2

volatile sig_atomic_t running = 1;
int sock_fd = -1;
pthread_mutex_t socket_mutex = PTHREAD_MUTEX_INITIALIZER;

typedef struct {
    char tag_id[MAX_ID_LENGTH * 2 + 1];
    time_t timestamp;
    int seen_count;
} TagInfo;

TagInfo seen_tags[MAX_TAGS];
int tag_count = 0;
pthread_mutex_t tags_mutex = PTHREAD_MUTEX_INITIALIZER;

void signal_handler(int sig) {
    printf("\nReceived signal %d, shutting down...\n", sig);
    running = 0;
}

void cleanup() {
    if (sock_fd >= 0) {
        close(sock_fd);
        sock_fd = -1;
    }
}

int connect_to_socket() {
    struct sockaddr_un addr;
    int retries = 5;
    
    while (retries-- > 0 && running) {
        sock_fd = socket(AF_UNIX, SOCK_STREAM, 0);
        if (sock_fd < 0) {
            perror("socket");
            sleep(RECONNECT_DELAY);
            continue;
        }
        
        memset(&addr, 0, sizeof(addr));
        addr.sun_family = AF_UNIX;
        strncpy(addr.sun_path, SOCKET_PATH, sizeof(addr.sun_path) - 1);
        
        if (connect(sock_fd, (struct sockaddr*)&addr, sizeof(addr)) < 0) {
            fprintf(stderr, "Failed to connect to socket: %s\n", strerror(errno));
            close(sock_fd);
            sock_fd = -1;
            sleep(RECONNECT_DELAY);
            continue;
        }
        
        printf("Connected to vision processor socket\n");
        return 0;
    }
    
    fprintf(stderr, "Failed to connect after %d attempts\n", 5);
    return -1;
}

void send_tag_event(const char* tag_id) {
    char message[256];
    struct timespec ts;
    clock_gettime(CLOCK_REALTIME, &ts);
    
    snprintf(message, sizeof(message), 
             "{\"type\":\"rfid\",\"tag_id\":\"%s\",\"timestamp\":%.6f}\n",
             tag_id, ts.tv_sec + ts.tv_nsec / 1e9);
    
    pthread_mutex_lock(&socket_mutex);
    if (sock_fd >= 0) {
        ssize_t bytes_sent = send(sock_fd, message, strlen(message), MSG_NOSIGNAL);
        if (bytes_sent < 0) {
            perror("send failed");
            close(sock_fd);
            sock_fd = -1;
            if (connect_to_socket() == 0) {
                send(sock_fd, message, strlen(message), MSG_NOSIGNAL);
            }
        } else {
            printf("Sent: %s", message);
        }
    }
    pthread_mutex_unlock(&socket_mutex);
}

static void printHex(uint8_t* vect, uint16_t length, char* result) {
    for (int i = 0; i < length; i++) {
        sprintf(result + (i * 2), "%02X", vect[i]);
    }
    result[length * 2] = '\0';
}

bool is_new_tag(const char* tag_id) {
    pthread_mutex_lock(&tags_mutex);
    for (int i = 0; i < tag_count; i++) {
        if (strcmp(seen_tags[i].tag_id, tag_id) == 0) {
            seen_tags[i].seen_count++;
            seen_tags[i].timestamp = time(NULL);
            pthread_mutex_unlock(&tags_mutex);
            return false;
        }
    }
    
    if (tag_count < MAX_TAGS) {
        strcpy(seen_tags[tag_count].tag_id, tag_id);
        seen_tags[tag_count].timestamp = time(NULL);
        seen_tags[tag_count].seen_count = 1;
        tag_count++;
    }
    pthread_mutex_unlock(&tags_mutex);
    return true;
}

void* tag_cleanup_thread(void* arg) {
    while (running) {
        sleep(60);
        time_t now = time(NULL);
        pthread_mutex_lock(&tags_mutex);
        int new_count = 0;
        for (int i = 0; i < tag_count; i++) {
            if (now - seen_tags[i].timestamp < 300) {
                if (i != new_count) {
                    seen_tags[new_count] = seen_tags[i];
                }
                new_count++;
            }
        }
        tag_count = new_count;
        pthread_mutex_unlock(&tags_mutex);
    }
    return NULL;
}

int main(int argc, char* argv[]) {
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
        .flowControl = 0
    };
    
    char model[64], serial[64], source[32] = "Source_0";
    pthread_t cleanup_thread;
    
    signal(SIGINT, signal_handler);
    signal(SIGTERM, signal_handler);
    
    printf("RFID Reader IPC Client Starting...\n");
    
    if (connect_to_socket() != 0) {
        fprintf(stderr, "Cannot connect to vision processor. Ensure it's running first.\n");
        return 1;
    }
    
    ec = CAENRFID_Connect(&reader, CAENRFID_RS232, &port_params);
    if (ec != CAENRFID_StatusOK) {
        fprintf(stderr, "Failed to connect to RFID reader: %d\n", ec);
        cleanup();
        return 1;
    }
    
    ec = CAENRFID_GetReaderInfo(&reader, model, serial);
    printf("Reader: %s, Serial: %s\n", model, serial);
    
    ec = CAENRFID_SetPower(&reader, 100);
    if (ec != CAENRFID_StatusOK) {
        fprintf(stderr, "Failed to set power: %d\n", ec);
    }
    
    pthread_create(&cleanup_thread, NULL, tag_cleanup_thread, NULL);
    
    int scan_rate_ms = 50;
    printf("Starting continuous inventory (scan rate: %dms)\n", scan_rate_ms);
    
    while (running) {
        CAENRFIDTagList *tags = NULL, *current;
        uint16_t num_tags = 0;
        
        ec = CAENRFID_InventoryTag(&reader, source, 0, 0, 0, NULL, 0, 0, &tags, &num_tags);
        
        if (ec == CAENRFID_StatusOK && num_tags > 0) {
            current = tags;
            while (current != NULL) {
                char tag_str[MAX_ID_LENGTH * 2 + 1];
                printHex(current->Tag.ID, current->Tag.Length, tag_str);
                
                if (is_new_tag(tag_str)) {
                    printf("New tag detected: %s\n", tag_str);
                    send_tag_event(tag_str);
                }
                
                CAENRFIDTagList *next = current->Next;
                free(current);
                current = next;
            }
        }
        
        usleep(scan_rate_ms * 1000);
    }
    
    running = 0;
    pthread_join(cleanup_thread, NULL);
    
    CAENRFID_Disconnect(&reader);
    cleanup();
    printf("RFID reader shutdown complete\n");
    
    return 0;
}