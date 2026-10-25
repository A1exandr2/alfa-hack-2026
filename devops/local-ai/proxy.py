"""Bounded TCP-to-Unix-socket bridge; the Unix socket is an SSH reverse forward."""
import os
import select
import socket
import socketserver
import threading


def unavailable(connection):
    body = b'{"error":"Local AI is unavailable"}'
    try:
        connection.sendall(
            b"HTTP/1.1 503 Service Unavailable\r\n"
            b"Content-Type: application/json\r\nConnection: close\r\n"
            + f"Content-Length: {len(body)}\r\n\r\n".encode()
            + body
        )
    except OSError:
        pass


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as upstream:
            upstream.settimeout(10)
            try:
                upstream.connect(self.server.socket_path)
            except OSError:
                unavailable(self.request)
                return
            upstream.settimeout(240)
            self.request.settimeout(240)
            peers = {self.request: upstream, upstream: self.request}
            try:
                while True:
                    ready, _, _ = select.select(list(peers), [], [], 240)
                    if not ready:
                        return
                    for source in ready:
                        data = source.recv(65536)
                        if not data:
                            return
                        peers[source].sendall(data)
            except OSError:
                return


class Bridge(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address, socket_path, max_connections=8):
        self.socket_path = socket_path
        self.slots = threading.BoundedSemaphore(max_connections)
        super().__init__(address, Handler)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            unavailable(request)
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()


if __name__ == "__main__":
    with Bridge(("0.0.0.0", 11434), os.getenv("OLLAMA_SOCKET", "/bridge/ollama.sock")) as server:
        server.serve_forever()
