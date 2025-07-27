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
    """
    Splits raw HTTP bytes into (head, body) on the first b'\r\n\r\n'.
    """
    parts = raw.split(b'\r\n\r\n', 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    else:
        return parts[0], b''

def parse_http_request(raw: bytes) -> HTTPRequest:
    """
    Parse raw bytes of an HTTP request (client→proxy) into an HTTPRequest.
    """
    head, body = _split_head_body(raw)
    # Separate request-line from header block
    request_line, header_block = head.split(b'\r\n', 1)
    method, url, version = request_line.decode('ascii').split(' ', 2)

    req = HTTPRequest(method, url, version)
    # Parse headers
    for line in header_block.decode('ascii').split('\r\n'):
        if not line:
            continue
        key, value = line.split(': ', 1)
        req.headers[key] = value

    req.body = body
    return req

def parse_http_response(raw: bytes) -> HTTPResponse:
    """
    Parse raw bytes of an HTTP response (server→proxy) into an HTTPResponse.
    """
    head, body = _split_head_body(raw)
    # Separate status-line from header block
    status_line, header_block = head.split(b'\r\n', 1)
    parts = status_line.decode('ascii').split(' ', 2)
    version = parts[0]
    status_code = int(parts[1])
    reason = parts[2] if len(parts) > 2 else ''

    resp = HTTPResponse(version, status_code, reason)
    # Parse headers
    for line in header_block.decode('ascii').split('\r\n'):
        if not line:
            continue
        key, value = line.split(': ', 1)
        resp.headers[key] = value

    resp.body = body
    return resp


with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as proxy_socket:
    proxy_socket.bind((HOST, PORT))
    proxy_socket.listen()
    print(f"Proxy server listening on {HOST}:{PORT}")
    client_ip, client_port = proxy_socket.accept()
    with client_ip:
        print(f"Connection established with {client_ip.getpeername()}")
        while True:
            data = client_ip.recv(4096)
            if not data:
                break

            request = parse_http_request(data)
            
            print(request)
            print("Headers:", request.headers)
            print("Body:", request.body)
            
            # with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
            #     # Connect to the target server
            #     server_socket.connect((url, 80))

            # Here you would handle the request and send a response
            # prepare body
            body = b"Hello from the proxy server!"
            # build a proper status‐line + headers
            lines = [
                "HTTP/1.1 200 OK",                     # status‐line
                "Content-Type: text/plain",            # MIME
                f"Content-Length: {len(body)}",        # MUST have this
                "Connection: close",                   # or keep‐alive if you plan to reuse
                "",                                    # <--- blank line ends headers
                ""                                     # (the join will add CRLFs)
            ]
            header_block = "\r\n".join(lines).encode("ascii")

            # send headers + body bytes
            client_ip.sendall(header_block + body)
            # if you said Connection: close, then close the socket
            client_ip.close()
            break

    

