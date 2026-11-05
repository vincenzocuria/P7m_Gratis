"""Synthetic PDFs for password export tests (requires pypdf with AES support)."""
from pathlib import Path
from pypdf import PdfWriter
from datetime import datetime, timedelta, timezone
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs7
from cryptography.x509.oid import NameOID

root = Path(__file__).resolve().parents[1] / "test" / "fixtures"
for algorithm in ("RC4-128", "AES-256"):
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    writer.add_blank_page(width=420, height=595)
    writer.add_metadata({"/Title": "Documento sintetico protetto"})
    writer.encrypt("test-password", owner_password="owner-password", algorithm=algorithm)
    with (root / ("encrypted_" + algorithm.lower() + ".pdf")).open("wb") as output:
        writer.write(output)

key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Synthetic encrypted PDF test")])
now = datetime.now(timezone.utc)
certificate = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
               .public_key(key.public_key()).serial_number(42)
               .not_valid_before(now - timedelta(days=1))
               .not_valid_after(now + timedelta(days=365))
               .sign(key, hashes.SHA256()))
source = (root / "encrypted_aes-256.pdf").read_bytes()
builder = pkcs7.PKCS7SignatureBuilder().set_data(source).add_signer(certificate, key, hashes.SHA256())
(root / "encrypted_aes-256.pdf.p7m").write_bytes(builder.sign(
    serialization.Encoding.DER, [pkcs7.PKCS7Options.Binary]))
(root / "encrypted_detached.p7s").write_bytes(builder.sign(
    serialization.Encoding.DER, [pkcs7.PKCS7Options.Binary, pkcs7.PKCS7Options.DetachedSignature]))
