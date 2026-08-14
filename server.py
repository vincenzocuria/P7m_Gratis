"""
EnergyCompare Pro & P7M Decoder Backend Server
Serves the web application and handles electronic invoice .p7m /.xml parsing API.
"""

import os
import json
import urllib.parse
from http.server import HTTPServer, SimpleHTTPRequestHandler
from p7m_decoder import P7MDecoder

PORT = 8000
WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))

class EnergyAppHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WORKSPACE_DIR, **kwargs)

    def do_POST(self):
        if self.path == '/api/parse-p7m':
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)

            try:
                # Expecting raw p7m binary bytes or JSON payload
                decoded_result = P7MDecoder.decode_file(post_data)

                xml_payload = ""
                if decoded_result.get('payload'):
                    try:
                        xml_payload = decoded_result['payload'].decode('utf-8', errors='ignore')
                    except Exception:
                        xml_payload = ""

                response = {
                    "success": decoded_result.get('payload') is not None,
                    "mime_type": decoded_result.get('mime_type', ''),
                    "sha256": decoded_result.get('sha256', ''),
                    "signer_info": decoded_result.get('signer_info', {}),
                    "xmlText": xml_payload,
                    "error": decoded_result.get('error')
                }

                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps(response).encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                err_resp = {"success": False, "error": str(e)}
                self.wfile.write(json.dumps(err_resp).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

def run_server():
    server_address = ('', PORT)
    httpd = HTTPServer(server_address, EnergyAppHandler)
    print("==================================================")
    print(" [OK] EnergyCompare Pro App Server running on:")
    print(f" -> http://localhost:{PORT}")
    print(f" -> http://127.0.0.1:{PORT}")
    print("==================================================")
    httpd.serve_forever()

if __name__ == '__main__':
    run_server()
