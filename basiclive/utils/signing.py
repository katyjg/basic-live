import base64
import time

from cryptography.hazmat.primitives import hashes
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from django.core.signing import b62_encode, b62_decode


class Signer(object):
    def __init__(self, public=None, private=None, sep=':', salt=None, max_delta=60):
        assert public or private, "Must provide either a public key or a private key, or both."
        self.private_key = None if not private else serialization.load_der_private_key(private, None, default_backend())
        self.public_key = None if not public else serialization.load_ssh_public_key(public.encode('utf-8'), default_backend())
        self.sep = sep
        self.salt = salt or 'ca.clsi.cmcf'
        self.max_delta = max_delta

    def timestamp(self):
        return b62_encode(int(time.time()))

    def signature(self, value):
        from cryptography.hazmat.primitives.asymmetric import rsa, padding, ec, ed25519
        data = f'{self.salt}{self.sep}{value}'.encode('utf-8')
        if isinstance(self.private_key, rsa.RSAPrivateKey):
            signature = self.private_key.sign(data, padding.PKCS1v15(), hashes.SHA256())
        elif isinstance(self.private_key, ec.EllipticCurvePrivateKey):
            signature = self.private_key.sign(data, ec.ECDSA(hashes.SHA256()))
        elif isinstance(self.private_key, ed25519.Ed25519PrivateKey):
            signature = self.private_key.sign(data)
        else:
            signature = self.private_key.sign(data, hashes.SHA256())
        return base64.urlsafe_b64encode(signature).decode('utf-8')

    def sign(self, value):
        assert self.private_key is not None, "Needs private key in order to sign."
        timed_value = '{value}{sep}{timestamp}'.format(value=value, sep=self.sep, timestamp=self.timestamp())
        return '{value}{sep}{signature}'.format(value=timed_value, sep=self.sep, signature=self.signature(timed_value))

    def unsign(self, signed_value):
        if self.sep not in signed_value:
            raise InvalidSignature('No "%s" found in value' % self.sep)
        try:
            timed_value, b64_sig = str(signed_value).rsplit(self.sep, 1)
            value, b62_time = timed_value.rsplit(self.sep, 1)
            if b64_sig.startswith("b'") and b64_sig.endswith("'"):
                b64_sig = b64_sig[2:-1]
            signature = base64.urlsafe_b64decode(b64_sig)
            signature_time = b62_decode(b62_time)
        except Exception as e:
            raise InvalidSignature('Corrupted signature or timestamp.') from e

        now = time.time()
        verify_value = '{salt}{sep}{value}'.format(salt=self.salt, value=timed_value, sep=self.sep).encode('utf-8')

        from cryptography.hazmat.primitives.asymmetric import rsa, padding, ec, ed25519
        if isinstance(self.public_key, rsa.RSAPublicKey):
            self.public_key.verify(signature, verify_value, padding.PKCS1v15(), hashes.SHA256())
        elif isinstance(self.public_key, ec.EllipticCurvePublicKey):
            self.public_key.verify(signature, verify_data=verify_value, signature_algorithm=ec.ECDSA(hashes.SHA256()))
        elif isinstance(self.public_key, ed25519.Ed25519PublicKey):
            self.public_key.verify(signature, verify_value)
        else:
            self.public_key.verify(signature, verify_value, hashes.SHA256())

        if now - signature_time > self.max_delta:
            raise InvalidSignature('Signature is too old.')

        return value


__all__ = ['Signer', 'InvalidSignature']