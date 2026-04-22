#!/usr/bin/env python3

import socket
import json
import time
import os
import threading
import random

SOCKET_PATH = "/tmp/rfid_vision.sock"

def start_test_server():
    """Test server that mimics the vision processor"""
    if os.path.exists(SOCKET_PATH):
        os.unlink(SOCKET_PATH)
    
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(SOCKET_PATH)
    server.listen(1)
    
    print(f"Test server listening on {SOCKET_PATH}")
    
    try:
        conn, _ = server.accept()
        print("Client connected!")
        
        buffer = ""
        while True:
            data = conn.recv(1024).decode('utf-8')
            if not data:
                break
            
            buffer += data
            while '\n' in buffer:
                line, buffer = buffer.split('\n', 1)
                if line:
                    msg = json.loads(line)
                    print(f"Received: {msg}")
                    assert msg.get("type") == "rfid"
                    assert "tag_id" in msg
                    assert "timestamp" in msg
        
    except Exception as e:
        print(f"Server error: {e}")
    finally:
        server.close()
        os.unlink(SOCKET_PATH)

def test_client():
    """Test client that mimics the RFID reader"""
    time.sleep(1)  # Let server start
    
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    
    try:
        client.connect(SOCKET_PATH)
        print("Connected to server!")
        
        # Send test RFID events
        test_tags = [
            "E20000172211010118905449",
            "E20000172211010218905450",
            "E20000172211010318905451"
        ]
        
        for tag in test_tags:
            msg = {
                "type": "rfid",
                "tag_id": tag,
                "timestamp": time.time()
            }
            client.send((json.dumps(msg) + "\n").encode('utf-8'))
            print(f"Sent: {msg}")
            time.sleep(random.uniform(0.5, 2.0))
        
        print("All test messages sent!")
        
    except Exception as e:
        print(f"Client error: {e}")
    finally:
        client.close()

def run_test():
    """Run the IPC test"""
    print("Starting IPC communication test...")
    print("-" * 40)
    
    server_thread = threading.Thread(target=start_test_server)
    server_thread.start()
    
    time.sleep(0.5)
    
    client_thread = threading.Thread(target=test_client)
    client_thread.start()
    
    client_thread.join()
    server_thread.join(timeout=2)
    
    print("-" * 40)
    print("Test completed successfully!")

if __name__ == "__main__":
    run_test()