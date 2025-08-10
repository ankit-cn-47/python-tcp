import socket
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
# Send a chat message
# =========================
def send_message(sock, message):
    sock.sendall(f"MSG:{message}".encode())
    ack = sock.recv(1024).decode()
    if ack == "DELIVERED":
        print("[MESSAGE DELIVERED]")

# =========================
# Send a file
# =========================
def send_file(sock, filepath):
    if not os.path.exists(filepath):
        print("[ERROR] File not found")
        return

    filesize = os.path.getsize(filepath)
    filename = os.path.basename(filepath)

    sock.sendall(f"FILE:{filename}|{filesize}".encode())

    with open(filepath, "rb") as f:
        sent = 0
        while (chunk := f.read(1024)):
            sock.sendall(chunk)
            sent += len(chunk)
            print_progress(sent, filesize)

    print("\n[FILE TRANSFER COMPLETE]")
    ack = sock.recv(1024).decode()
    if ack == "FILE_RECEIVED":
        print("[SERVER CONFIRMED FILE RECEIPT]")

# =========================
# Main client function
# =========================
def start_client(server_ip="192.168.64.10", port=8888):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((server_ip, port))

    try:
        while True:
            choice = input("\n1. Send Message\n2. Send File\n3. Quit\nChoice: ")
            if choice == "1":
                msg = input("Enter message: ")
                send_message(sock, msg)
            elif choice == "2":
                path = input("Enter file path: ")
                send_file(sock, path)
            elif choice == "3":
                break
            else:
                print("[INVALID CHOICE]")
    finally:
        sock.close()

if __name__ == "__main__":
    start_client()
