import unittest

from shortcut_cli import _resolve_signing_public_key


class SigningKeyTests(unittest.TestCase):
    def test_direct_apple_id_key(self):
        key = b'\x04' + bytes(range(1, 65))
        self.assertEqual(_resolve_signing_public_key({'SigningPublicKey': key}),
                         (key, 'apple-id/contact'))

    def test_direct_key_validation(self):
        with self.assertRaisesRegex(RuntimeError, 'expected 65-byte'):
            _resolve_signing_public_key({'SigningPublicKey': b'bad'})

    def test_unknown_auth_schema(self):
        with self.assertRaisesRegex(RuntimeError, 'Bar, Foo'):
            _resolve_signing_public_key({'Foo': b'1', 'Bar': b'2'})


if __name__ == '__main__':
    unittest.main()
