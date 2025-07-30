import sys
import socket

print(sys.argv)

if len(sys.argv) != 5:
    print("Usage: python proxy.py <port> <timeout> <max_object_size> <max_cache_size>")
    sys.exit(1)

PORT = int(sys.argv[1])
TIMEOUT = int(sys.argv[2])
MAX_OBJECT_SIZE = int(sys.argv[3])
MAX_CACHE_SIZE = int(sys.argv[4])

if PORT < 1 or PORT > 65535:
    print("Port must be between 1 and 65535")
    sys.exit(1)

if TIMEOUT < 1:
    print("Timeout must be a positive integer")
    sys.exit(1)

if MAX_OBJECT_SIZE < 1 or MAX_CACHE_SIZE < MAX_OBJECT_SIZE:
    print("Max object size must be a positive integer and less than max cache size")
    sys.exit(1)

# PORT = 8080
# TIMEOUT = 10
# MAX_OBJECT_SIZE = 1024 * 1024  # 1 MB
# MAX_CACHE_SIZE = 10 * 1024 * 1024  # 10 MB

HOST = "127.0.0.1"

from typing import Dict, Tuple

class HTTPRequest:
    def __init__(self, method: str, url: str, version: str):
        self.method: str = method
        self.url: str = url
        self.version: str = version
        self.headers: Dict[str, str] = {}
        self.body: bytes = b''

    def __str__(self) -> str:
        return f"{self.method} {self.url} {self.version}"

class HTTPResponse:
    def __init__(self, version: str, status_code: int, reason: str):
        self.version: str = version
        self.status_code: int = status_code
        self.reason: str = reason
        self.headers: Dict[str, str] = {}
        self.body: bytes = b''

    def __str__(self) -> str:
        return f"{self.version} {self.status_code} {self.reason}"

def _split_head_body(raw: bytes) -> Tuple[bytes, bytes]:
    parts = raw.split(b'\r\n\r\n', 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return parts[0], b''


def parse_http_request(raw: bytes) -> HTTPRequest:
    head, body = _split_head_body(raw)
    request_line, header_block = head.split(b'\r\n', 1)
    method, url, version = request_line.decode('ascii').split(' ', 2)
    req = HTTPRequest(method, url, version)
    for line in header_block.decode('ascii').split('\r\n'):
        if not line:
            continue
        key, value = line.split(': ', 1)
        req.headers[key] = value
    req.body = body
    return req


def parse_http_response(raw: bytes) -> HTTPResponse:
    head, body = _split_head_body(raw)
    status_line, header_block = head.split(b'\r\n', 1)
    parts = status_line.decode('ascii').split(' ', 2)
    version, status_code = parts[0], int(parts[1])
    reason = parts[2] if len(parts) > 2 else ''
    resp = HTTPResponse(version, status_code, reason)
    for line in header_block.decode('ascii').split('\r\n'):
        if not line:
            continue
        key, value = line.split(': ', 1)
        resp.headers[key] = value
    resp.body = body
    return resp


def split_url(url: str) -> Tuple[str, str]:
    # returns (host:port, path+query)
    if url.startswith("http://"):
        rest = url[len("http://"):]
    elif url.startswith("https://"):
        rest = url[len("https://"):]
    else:
        rest = url
    parts = rest.split('/', 1)
    host_port = parts[0]
    path_query = '/' + parts[1] if len(parts) == 2 else '/'
    return host_port, path_query


def handle_client(client_conn: socket.socket):
    try:
        # receive request from client
        header_bytes = b''
        while True:
            chunk = client_conn.recv(4096)
            if not chunk:
                break
            header_bytes += chunk
            if len(header_bytes) > MAX_OBJECT_SIZE:
                print("Request exceeds max object size, closing connection.")
                client_conn.close()
                return
            if b'\r\n\r\n' in header_bytes:
                break
        
        head, body = _split_head_body(header_bytes)
        req = parse_http_request(head + b'\r\n\r\n' + body)
        req.body = body
        if 'Content-Length' in req.headers and req.method not in ['GET', 'HEAD']:
            content_length = int(req.headers['Content-Length'])
            while len(req.body) < content_length:
                chunk = client_conn.recv(4096)
                if not chunk:
                    break
                req.body += chunk

        print(f"Request: {req}")
        print(f"Headers: {req.headers}")
        print(f"Body: {req.body.decode('utf-8', errors='ignore')}")

        # parse URL to get host and port, transform absolute form to origin form
        host_port, path = split_url(req.url)
        if ':' in host_port:
            host, port_str = host_port.split(':', 1)
            port = int(port_str)
        else:
            host = host_port
            port = 80

        # rebuild the request to forward to origin
        if req.headers['Connection'] != 'close':
            req.headers['Connection'] = 'keep-alive'
        req.headers.pop('Proxy-Connection', None)
        req.headers['Via'] = "1.1 z5592060"
        req.headers['Host'] = host_port
        request_line = f"{req.method} {path} {req.version}\r\n"
        headers = ''.join(f"{k}: {v}\r\n" for k, v in req.headers.items())
        forward_data = (request_line + headers + '\r\n').encode('ascii') + req.body

        # forward the request to the origin server
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_sock:
            server_sock.settimeout(TIMEOUT)
            server_sock.connect((host, port))
            print(f"Forwarding request to {host}:{port}")
            print(f"Forward data: {forward_data.decode('ascii', errors='ignore')}")
            server_sock.sendall(forward_data)
            while True:
                chunk = server_sock.recv(4096)
                if not chunk:
                    break
                # parse the response from the server
                response = parse_http_response(chunk)
                print(f"Response: {response}")
                print(f"Response Headers: {response.headers}")
                print(f"Response Body: {response.body.decode('utf-8', errors='ignore')}")

                # rebuild the response to send back to the client
                response.headers['Via'] = "1.1 z5592060"
                response_line = f"{response.version} {response.status_code} {response.reason}\r\n"
                headers = ''.join(f"{k}: {v}\r\n" for k, v in response.headers.items())
                response_data = (response_line + headers + '\r\n').encode('ascii') + response.body
                client_conn.sendall(response_data)
    except Exception as e:
        print(f"Error handling client: {e}")
    finally:
        client_conn.close()


def main():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as proxy_sock:
        proxy_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        proxy_sock.bind((HOST, PORT))
        proxy_sock.listen()
        print(f"Proxy server listening on {HOST}:{PORT}")
        while True:
            client_conn, client_addr = proxy_sock.accept()
            print(f"Connection from {client_addr}")
            handle_client(client_conn)


if __name__ == '__main__':
    main()
    

