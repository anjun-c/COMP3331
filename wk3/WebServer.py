#!/usr/bin/env python3
import socket
import sys
import os
import mimetypes

def handle_client(conn, addr):
    with conn:
        while True:
            data = b""
            while b"\r\n\r\n" not in data:
                chunk = conn.recv(1024)
                if not chunk:
                    return
                data += chunk

            header_text = data.split(b"\r\n\r\n")[0].decode('iso-8859-1')
            lines = header_text.split("\r\n")
            request_line = lines[0].split()
            if len(request_line) < 3:
                return
            method, path, version = request_line

            if method != 'GET':
                response = f"{version} 405 Method Not Allowed\r\nConnection: close\r\n\r\n"
                conn.sendall(response.encode())
                return

            if path == '/favicon.ico':
                response = f"{version} 204 No Content\r\nConnection: close\r\n\r\n"
                conn.sendall(response.encode())
                return

            file_path = path.lstrip('/') or 'index.html'

            if not os.path.isfile(file_path):
                body = b"<html><body><h1>404 Not Found</h1></body></html>"
                headers = [
                    f"{version} 404 Not Found",
                    "Content-Type: text/html; charset=utf-8",
                    f"Content-Length: {len(body)}",
                    "Connection: close",
                    "",
                    ""
                ]
                header_data = "\r\n".join(headers).encode()
                conn.sendall(header_data + body)
                return

            with open(file_path, 'rb') as f:
                body = f.read()

            mime_type, _ = mimetypes.guess_type(file_path)
            if not mime_type:
                mime_type = 'application/octet-stream'

            headers = [
                f"{version} 200 OK",
                f"Content-Type: {mime_type}",
                f"Content-Length: {len(body)}",
                "Connection: keep-alive",
                "",
                ""
            ]
            header_data = "\r\n".join(headers).encode()
            conn.sendall(header_data + body)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print(f"Usage: python3 {sys.argv[0]} <port>")
        sys.exit(1)

    PORT = int(sys.argv[1])
    HOST = '0.0.0.0'

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((HOST, PORT))
        server_socket.listen(1)
        print(f"Listening on {HOST}:{PORT}...")

        while True:
            conn, addr = server_socket.accept()
            print(f"Connection from {addr}")
            handle_client(conn, addr)
