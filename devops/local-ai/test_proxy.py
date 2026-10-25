"""Exercise real Unix/TCP forwarding, offline behavior, and connection limits."""
import contextlib
import importlib.util
from pathlib import Path
import socket
import socketserver
import tempfile
import threading
import unittest

spec = importlib.util.spec_from_file_location("bridge", Path(__file__).with_name("proxy.py"))
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


@contextlib.contextmanager
def running(server):
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05})
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


class Echo(socketserver.BaseRequestHandler):
    def handle(self):
        self.server.connected.set()
        while chunk := self.request.recv(65536):
            self.request.sendall(chunk)


class ProxyTests(unittest.TestCase):
    def test_binary_body_is_forwarded_without_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "model.sock")
            upstream = socketserver.ThreadingUnixStreamServer(path, Echo)
            upstream.daemon_threads = True
            upstream.connected = threading.Event()
            with running(upstream), running(bridge.Bridge(("127.0.0.1", 0), path)) as proxy:
                with socket.create_connection(proxy.server_address, timeout=3) as client:
                    payload = bytes(range(256)) * 512
                    client.sendall(payload)
                    response = bytearray()
                    while len(response) < len(payload):
                        response.extend(client.recv(65536))
                    self.assertEqual(bytes(response), payload)

    def test_offline_model_returns_http_503(self):
        with tempfile.TemporaryDirectory() as directory:
            with running(bridge.Bridge(("127.0.0.1", 0), str(Path(directory) / "missing"))) as proxy:
                with socket.create_connection(proxy.server_address, timeout=3) as client:
                    self.assertIn(b"503 Service Unavailable", client.recv(4096))

    def test_connections_are_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "model.sock")
            upstream = socketserver.ThreadingUnixStreamServer(path, Echo)
            upstream.daemon_threads = True
            upstream.connected = threading.Event()
            with running(upstream), running(bridge.Bridge(("127.0.0.1", 0), path, 1)) as proxy:
                with socket.create_connection(proxy.server_address, timeout=3):
                    self.assertTrue(upstream.connected.wait(timeout=3))
                    with socket.create_connection(proxy.server_address, timeout=3) as second:
                        self.assertIn(b"503 Service Unavailable", second.recv(4096))


if __name__ == "__main__":
    unittest.main()
