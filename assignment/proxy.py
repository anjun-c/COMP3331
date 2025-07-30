#!/usr/bin/env python3
import sys
import socket
from typing import Dict, Tuple

# --- Argument parsing ---
if len(sys.argv) != 5:
    print("Usage: python proxy.py <port> <timeout> <max_object_size> <max_cache_size>")
    sys.exit(1)

PORT = int(sys.argv[1])
TIMEOUT = int(sys.argv[2])
MAX_OBJECT_SIZE = int(sys.argv[3])
MAX_CACHE_SIZE = int(sys.argv[4])

if not (1 <= PORT <= 65535):
    print("Port must be between 1 and 65535")
    sys.exit(1)
if TIMEOUT < 1:
    print("Timeout must be a positive integer")
    sys.exit(1)
if MAX_OBJECT_SIZE < 1 or MAX_CACHE_SIZE < MAX_OBJECT_SIZE:
    print("Max object size must be >0 and <= max cache size")
    sys.exit(1)

HOST = '127.0.0.1'

# --- HTTP data classes ---
class HTTPRequest:
    def __init__(self, method: str, url: str, version: str):
        self.method = method
        self.url = url
        self.version = version
        self.headers: Dict[str,str] = {}
        self.body: bytes = b''
    def __str__(self) -> str:
        return f"{self.method} {self.url} {self.version}"  

class HTTPResponse:
    def __init__(self, version: str, status_code: int, reason: str):
        self.version = version
        self.status_code = status_code
        self.reason = reason
        self.headers: Dict[str,str] = {}
        self.body: bytes = b''
    def __str__(self) -> str:
        return f"{self.version} {self.status_code} {self.reason}"  

# --- Helpers for framing ---
def recv_until(sock: socket.socket, delim: bytes = b"\r\n\r\n") -> bytes:
    buf = bytearray()
    while delim not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            break
        buf.extend(chunk)
    return bytes(buf)

def recv_exact(sock: socket.socket, length: int) -> bytes:
    buf = bytearray()
    while len(buf) < length:
        chunk = sock.recv(length - len(buf))
        if not chunk:
            break
        buf.extend(chunk)
    return bytes(buf)

# --- Parsing ---
def _split_head_body(raw: bytes) -> Tuple[bytes,bytes]:
    parts = raw.split(b"\r\n\r\n", 1)
    if len(parts)==2:
        return parts[0], parts[1]
    return parts[0], b''

def parse_http_request(raw: bytes) -> HTTPRequest:
    head, body = _split_head_body(raw)
    request_line, header_block = head.split(b"\r\n",1)
    method, url, version = request_line.decode('ascii').split(' ',2)
    req = HTTPRequest(method, url, version)
    for line in header_block.decode('ascii').split("\r\n"):
        if not line: continue
        key,val = line.split(': ',1)
        req.headers[key]=val
    req.body = body
    return req

def parse_http_response(raw: bytes) -> HTTPResponse:
    head, body = _split_head_body(raw)
    status_line, header_block = head.split(b"\r\n",1)
    parts = status_line.decode('ascii').split(' ',2)
    version = parts[0]
    code = int(parts[1])
    reason = parts[2] if len(parts)>2 else ''
    resp = HTTPResponse(version, code, reason)
    for line in header_block.decode('ascii').split("\r\n"):
        if not line: continue
        key,val = line.split(': ',1)
        resp.headers[key]=val
    resp.body = body
    return resp

# --- URL split ---
def split_url(url: str) -> Tuple[str,str]:
    if url.startswith("http://"): rest = url[7:]
    elif url.startswith("https://"): rest = url[8:]
    else: rest = url
    parts = rest.split('/',1)
    host_port = parts[0]
    path = '/' + parts[1] if len(parts)==2 else '/'
    return host_port, path

# --- Client handler ---
def handle_client(client_conn: socket.socket):
    try:
        # ---- Read and parse client request ----
        req_buf = recv_until(client_conn)
        if not req_buf: return
        head, body = _split_head_body(req_buf)
        req = parse_http_request(req_buf)
        # read remaining request-body if any
        if 'Content-Length' in req.headers and req.method not in ('GET','HEAD'):
            total = int(req.headers['Content-Length'])
            already = len(body)
            if total > already:
                body += recv_exact(client_conn, total-already)
            req.body = body
        else:
            req.body = b''

        # ---- Transform request headers ----
        req.headers.pop('Proxy-Connection', None)
        req.headers.pop('Connection', None)
        req.headers['Connection'] = 'close'
        via = '1.1 z5592060'
        if 'Via' in req.headers:
            req.headers['Via'] += ', ' + via
        else:
            req.headers['Via'] = via

        # ---- Extract host, port, path ----
        host_port, path = split_url(req.url)
        if ':' in host_port:
            host,port_str = host_port.split(':',1)
            port = int(port_str)
        else:
            host = host_port; port = 80
        req.headers['Host'] = host_port

        # ---- Build and forward request ----
        request_line = f"{req.method} {path} {req.version}\r\n"
        hdrs = ''.join(f"{k}: {v}\r\n" for k,v in req.headers.items())
        forward_data = (request_line + hdrs + '\r\n').encode('ascii') + req.body
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_sock:
            server_sock.settimeout(TIMEOUT)
            server_sock.connect((host,port))
            server_sock.sendall(forward_data)

            # ---- Read and parse server response headers ----
            resp_hdr_buf = recv_until(server_sock)
            head_s, rest = _split_head_body(resp_hdr_buf)
            res = parse_http_response(resp_hdr_buf)
            body_buf = bytearray(rest)

            # ---- Read response body ----
            # no-body cases
            if req.method=='HEAD' or 100<=res.status_code<200 or res.status_code in (204,304):
                full_body = b''
            # Content-Length
            elif 'Content-Length' in res.headers:
                total = int(res.headers['Content-Length'])
                needed = total - len(rest)
                if needed>0:
                    body_buf.extend(recv_exact(server_sock, needed))
                full_body = bytes(body_buf)
            # chunked
            elif res.headers.get('Transfer-Encoding','').lower()=='chunked':
                buf = body_buf
                while True:
                    size_line = recv_until(server_sock, b'\r\n')
                    buf.extend(size_line)
                    size = int(size_line.split(b';',1)[0],16)
                    chunk = recv_exact(server_sock, size+2)
                    buf.extend(chunk)
                    if size==0:
                        trailer = recv_until(server_sock)
                        buf.extend(trailer)
                        break
                full_body = bytes(buf)
            # until close
            else:
                while True:
                    chunk = server_sock.recv(4096)
                    if not chunk: break
                    body_buf.extend(chunk)
                full_body = bytes(body_buf)

        # ---- Transform and send response back ----
        res.headers.pop('Proxy-Connection', None)
        res.headers['Connection'] = 'close'
        vis = res.headers.get('Via','')
        res.headers['Via'] = (vis + ', ' if vis else '') + via
        status = f"{res.version} {res.status_code} {res.reason}\r\n"
        hdr_lines = ''.join(f"{k}: {v}\r\n" for k,v in res.headers.items())
        client_conn.sendall(status.encode('ascii') + hdr_lines.encode('ascii') + b"\r\n" + full_body)

    except Exception as e:
        print(f"Error handling client: {e}")
    finally:
        client_conn.close()

# --- Main loop ---
def main():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as proxy_sock:
        proxy_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        proxy_sock.bind((HOST, PORT))
        proxy_sock.listen()
        print(f"Proxy server listening on {HOST}:{PORT}")
        while True:
            client_conn, client_addr = proxy_sock.accept()
            handle_client(client_conn)

if __name__=='__main__':
    main()
