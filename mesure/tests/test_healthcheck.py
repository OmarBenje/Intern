"""The measurement probe accepts readiness only on a successful HTTP status."""

import io
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch


class MeasurementProbeTests(unittest.TestCase):
    def test_http_status_controls_health_without_importing_tls_stack(self):
        overlay = Path(__file__).resolve().parents[1] / 'compose.test.yaml'
        source = next(line.strip()[2:] for line in overlay.read_text().splitlines()
                      if line.strip().startswith('- "import socket;'))
        code = json.loads(source)
        for response, expected in ((b'HTTP/1.1 200 OK\r\n', 0),
                                   (b'HTTP/1.1 503 Unavailable\r\n', 1), (b'', 1)):
            connection = Mock()
            connection.makefile.return_value = io.BytesIO(response)
            with self.subTest(response=response), patch('socket.create_connection', return_value=connection) as connect:
                with self.assertRaises(SystemExit) as exit:
                    exec(code, {})
                self.assertEqual(exit.exception.code, expected)
                connect.assert_called_once_with(('127.0.0.1', 8000), timeout=4)
                connection.sendall.assert_called_once_with(b'GET /health/ready/ HTTP/1.0\r\nHost: localhost\r\n\r\n')
                connection.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
