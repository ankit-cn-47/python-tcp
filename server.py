import socket
import threading
import os
import sys

# =========================
# Helper function for progress display
# =========================
def print_progress(sent, total):
    percent = (sent / total) * 100
    sys.stdout.write(f"\rProgress: {percent:.2f}%")
    sys.stdout.flush()

# =========================
# Handle each client connection
# =========================
def handle_client(conn, addr):
    print(f"[NEW CONNECTION] {addr} connected.")

    try:
        while True:
            # First receive a header indicating the type of data
            header = conn.recv(1024).decode()
            if not header:
                break

            if header.startswith("MSG:"): # Chat message
                message = header[4:]
                print(f"[MESSAGE from {addr}]: {message}")
                conn.sendall(b"DELIVERED") # Acknowledge

            elif header.startswith("FILE:"): # File transfer
                filename, filesize = header[5:].split("|")
                filesize = int(filesize)

                # Create received_files directory if it doesn't exist
                os.makedirs("received_files", exist_ok=True)

                print(f"[FILE TRANSFER] Receiving '{filename}' ({filesize} bytes) from {addr}")
                with open(f"received_files/received_{filename}", "wb") as f:
                    received = 0
                    while received < filesize:
                        data = conn.recv(1024)
                        if not data:
                            break
                        f.write(data)
                        received += len(data)
                        print_progress(received, filesize)
                print("\n[TRANSFER COMPLETE]")
                conn.sendall(b"FILE_RECEIVED") # Acknowledge

    except ConnectionResetError:
        print(f"[DISCONNECTED] {addr}")
    finally:
        conn.close()

# =========================
# Main TCP server function
# =========================
def start_server(host="0.0.0.0", port=8888):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((host, port))
    server.listen()

    print(f"[LISTENING] Server is listening on {host}:{port}")

    while True:
        conn, addr = server.accept()
        thread = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
        thread.start()
        print(f"[ACTIVE CONNECTIONS] {threading.active_count() - 1}")

if __name__ == "__main__":
    start_server()
