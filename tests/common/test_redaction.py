import unittest

from podonos.common.redaction import redact_secrets


class TestRedaction(unittest.TestCase):
    def test_redacts_quoted_dict_secret_fields(self):
        message = "headers={'X-API-KEY': 'SECRET', 'Authorization': 'Bearer TOKEN'}"

        redacted = redact_secrets(message)

        self.assertNotIn("SECRET", redacted)
        self.assertNotIn("TOKEN", redacted)
        self.assertIn("[REDACTED]", redacted)

    def test_redacts_cloudfront_cookie_fields(self):
        message = (
            "cookies={'CloudFront-Signature': 'SIGNATURE', "
            "'CloudFront-Policy': 'POLICY', "
            "'CloudFront-Key-Pair-Id': 'KEYPAIR'} "
            "Cookie: session=SECRET Set-Cookie: auth=TOKEN"
        )

        redacted = redact_secrets(message)

        self.assertNotIn("SIGNATURE", redacted)
        self.assertNotIn("POLICY", redacted)
        self.assertNotIn("KEYPAIR", redacted)
        self.assertNotIn("session=SECRET", redacted)
        self.assertNotIn("auth=TOKEN", redacted)
        self.assertIn("[REDACTED]", redacted)

    def test_redacts_common_secret_fields(self):
        message = (
            "password=hunter2 client_secret=CLIENTSECRET "
            "refresh_token=REFRESH secret_key=SECRETKEY "
            "payload={'private_key': 'PRIVATE', 'id_token': 'IDTOKEN'} "
            "https://example.com/callback?client_secret=QUERYSECRET"
        )

        redacted = redact_secrets(message)

        for secret in [
            "hunter2",
            "CLIENTSECRET",
            "REFRESH",
            "SECRETKEY",
            "PRIVATE",
            "IDTOKEN",
            "QUERYSECRET",
        ]:
            self.assertNotIn(secret, redacted)
        self.assertIn("[REDACTED]", redacted)


if __name__ == "__main__":
    unittest.main()
