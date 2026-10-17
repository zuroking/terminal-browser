from datetime import datetime, timezone
import ipaddress
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


CERT_DIR = Path(__file__).parent / "certs"
VALID_FROM = datetime(2020, 1, 1, tzinfo=timezone.utc)
VALID_UNTIL = datetime(2036, 9, 24, tzinfo=timezone.utc)
EXPIRED_UNTIL = datetime(2021, 9, 24, tzinfo=timezone.utc)


def new_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def write_key(path: Path, key: rsa.RSAPrivateKey) -> None:
    path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )


def write_certificate(path: Path, certificate: x509.Certificate) -> None:
    path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))


def subject(common_name: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])


def leaf(
    common_name: str,
    san: tuple[x509.GeneralName, ...],
    issuer_name: x509.Name,
    issuer_key: rsa.RSAPrivateKey,
    public_key: rsa.RSAPublicKey,
    not_before: datetime,
    not_after: datetime,
) -> x509.Certificate:
    return (
        x509.CertificateBuilder()
        .subject_name(subject(common_name))
        .issuer_name(issuer_name)
        .public_key(public_key)
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
        .add_extension(x509.SubjectAlternativeName(list(san)), critical=False)
        .sign(issuer_key, hashes.SHA256())
    )


def generate() -> None:
    CERT_DIR.mkdir(parents=True, exist_ok=True)
    ca_key = new_key()
    ca_name = subject("terminal-browser fixture CA")
    ca_certificate = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(VALID_FROM)
        .not_valid_after(VALID_UNTIL)
        .add_extension(x509.BasicConstraints(ca=True, path_length=1), critical=True)
        .sign(ca_key, hashes.SHA256())
    )
    write_key(CERT_DIR / "ca.key", ca_key)
    write_certificate(CERT_DIR / "ca.crt", ca_certificate)

    valid_key = new_key()
    valid_certificate = leaf(
        "localhost",
        (
            x509.DNSName("localhost"),
            x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
        ),
        ca_name,
        ca_key,
        valid_key.public_key(),
        VALID_FROM,
        VALID_UNTIL,
    )
    write_key(CERT_DIR / "valid.key", valid_key)
    write_certificate(CERT_DIR / "valid.crt", valid_certificate)

    untrusted_key = new_key()
    untrusted_name = subject("untrusted localhost")
    untrusted_certificate = (
        x509.CertificateBuilder()
        .subject_name(untrusted_name)
        .issuer_name(untrusted_name)
        .public_key(untrusted_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(VALID_FROM)
        .not_valid_after(VALID_UNTIL)
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName("localhost"),
                    x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
                ]
            ),
            critical=False,
        )
        .sign(untrusted_key, hashes.SHA256())
    )
    write_key(CERT_DIR / "untrusted.key", untrusted_key)
    write_certificate(CERT_DIR / "untrusted.crt", untrusted_certificate)

    mismatch_key = new_key()
    mismatch_certificate = leaf(
        "wrong host",
        (x509.DNSName("wrong.invalid"),),
        ca_name,
        ca_key,
        mismatch_key.public_key(),
        VALID_FROM,
        VALID_UNTIL,
    )
    write_key(CERT_DIR / "mismatch.key", mismatch_key)
    write_certificate(CERT_DIR / "mismatch.crt", mismatch_certificate)

    expired_key = new_key()
    expired_certificate = leaf(
        "expired localhost",
        (
            x509.DNSName("localhost"),
            x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
        ),
        ca_name,
        ca_key,
        expired_key.public_key(),
        VALID_FROM,
        EXPIRED_UNTIL,
    )
    write_key(CERT_DIR / "expired.key", expired_key)
    write_certificate(CERT_DIR / "expired.crt", expired_certificate)


if __name__ == "__main__":
    generate()
