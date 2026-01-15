"""
mitmproxy addon that corrupts S3 uploads to test upload verification.

Usage:
    1. Install mitmproxy: pip install mitmproxy

    2. Install mitmproxy CA certificate (required for HTTPS interception):
       # Start mitmproxy once to generate certificates
       mitmproxy -p 8080
       # Press 'q' to quit after it starts

       # macOS: Install CA certificate
       sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain ~/.mitmproxy/mitmproxy-ca-cert.pem

       # Or use REQUESTS_CA_BUNDLE (per-session):
       export REQUESTS_CA_BUNDLE=~/.mitmproxy/mitmproxy-ca-cert.pem

    3. Start proxy with corruption script:
       mitmproxy -s tests/integration/mitmproxy_corrupt_upload.py -p 8080

    4. Run SDK with proxy:
       HTTPS_PROXY=http://localhost:8080 REQUESTS_CA_BUNDLE=~/.mitmproxy/mitmproxy-ca-cert.pem \
         python tests/integration/test_upload_verification.py --api_key=<KEY> --test=success

Configuration:
    - CORRUPT_PROBABILITY: Chance of corrupting each upload (0.0 to 1.0)
    - CORRUPT_BYTES: Number of bytes to corrupt in each corrupted upload
"""

import random
from mitmproxy import http


CORRUPT_PROBABILITY = 1.0
CORRUPT_BYTES = 10


class UploadCorruptor:
    def __init__(self):
        self.corrupted_count = 0
        self.total_count = 0

    def request(self, flow: http.HTTPFlow) -> None:
        if not self._is_s3_upload(flow):
            return

        self.total_count += 1

        if random.random() > CORRUPT_PROBABILITY:
            print(f"[PASS] Upload #{self.total_count}: {flow.request.url[:80]}...")
            return

        if flow.request.content:
            original_size = len(flow.request.content)
            corrupted_content = self._corrupt_bytes(flow.request.content)
            flow.request.content = corrupted_content
            self.corrupted_count += 1
            print(
                f"[CORRUPT] Upload #{self.total_count}: corrupted {CORRUPT_BYTES} bytes in {original_size} byte payload"
            )

    def _is_s3_upload(self, flow: http.HTTPFlow) -> bool:
        return (
            flow.request.method == "PUT"
            and "s3" in flow.request.host
            and flow.request.content
            and len(flow.request.content) > 100
        )

    def _corrupt_bytes(self, content: bytes) -> bytes:
        content_list = bytearray(content)
        content_length = len(content_list)

        for _ in range(min(CORRUPT_BYTES, content_length)):
            position = random.randint(0, content_length - 1)
            content_list[position] = (
                content_list[position] + random.randint(1, 255)
            ) % 256

        return bytes(content_list)


addons = [UploadCorruptor()]
