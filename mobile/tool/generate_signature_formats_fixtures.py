"""Synthetic fixtures for countersignatures, Base64 P7M, PAdES and Word previews."""
import base64
import hashlib
import zipfile
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path

from asn1crypto import cms, x509 as asn_x509
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.serialization import pkcs7
from cryptography.x509.oid import NameOID

out = Path(__file__).resolve().parents[1] / 'test' / 'fixtures'
now = datetime.now(timezone.utc).replace(microsecond=0)
name = lambda text: x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, text)])
root_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def certificate(subject, key, serial, issuer=None, issuer_key=None):
    builder = (
        x509.CertificateBuilder()
        .subject_name(name(subject))
        .issuer_name(issuer.subject if issuer else name(subject))
        .public_key(key.public_key())
        .serial_number(serial)
        .not_valid_before(now - timedelta(days=100))
        .not_valid_after(now + timedelta(days=100))
        .add_extension(x509.BasicConstraints(ca=issuer is None, path_length=None), True)
    )
    return builder.sign(issuer_key or key, hashes.SHA256())


root = certificate('Formats Root', root_key, 701)
first_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
second_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
first = certificate('Primo firmatario', first_key, 702, root, root_key)
second = certificate('Controfirmatario', second_key, 703, root, root_key)


def attached(data, cert, key):
    return pkcs7.PKCS7SignatureBuilder().set_data(data).add_signer(cert, key, hashes.SHA256()).add_certificate(root).sign(serialization.Encoding.DER, [pkcs7.PKCS7Options.Binary])


def detached(data, cert, key):
    return pkcs7.PKCS7SignatureBuilder().set_data(data).add_signer(cert, key, hashes.SHA256()).add_certificate(root).sign(serialization.Encoding.DER, [pkcs7.PKCS7Options.Binary, pkcs7.PKCS7Options.DetachedSignature])


def countersign(envelope, cert, key, tamper=False):
    signed = cms.ContentInfo.load(envelope)
    signer = signed['content']['signer_infos'][0]
    value = signer['signature'].native
    attributes = [
        cms.CMSAttribute({'type': 'message_digest', 'values': [hashlib.sha256(value).digest()]}),
        cms.CMSAttribute({'type': 'signing_time', 'values': [cms.Time({'utc_time': now})]}),
    ]
    attributes.sort(key=lambda a: a.dump())  # DER SET ordering
    attrs = cms.CMSAttributes(attributes)
    signature = key.sign(attrs.dump(), padding.PKCS1v15(), hashes.SHA256())
    if tamper:
        signature = bytes([signature[0] ^ 1]) + signature[1:]
    issuer = asn_x509.Certificate.load(cert.public_bytes(serialization.Encoding.DER))
    counter = cms.SignerInfo({
        'version': 'v1',
        'sid': cms.SignerIdentifier({'issuer_and_serial_number': {
            'issuer': issuer.issuer, 'serial_number': issuer.serial_number}}),
        'digest_algorithm': {'algorithm': 'sha256'},
        'signed_attrs': attrs,
        'signature_algorithm': {'algorithm': 'sha256_rsa'},
        'signature': signature,
    })
    signer['unsigned_attrs'] = cms.CMSAttributes([
        cms.CMSAttribute({'type': 'counter_signature', 'values': [counter]})])
    signed['content']['certificates'].append(cms.CertificateChoices({'certificate': issuer}))
    return signed.dump(force=True)


document = b'Documento firmato e controfirmato'
envelope = attached(document, first, first_key)
out.joinpath('countersigned.p7m').write_bytes(countersign(envelope, second, second_key))
out.joinpath('countersigned_bad.p7m').write_bytes(countersign(envelope, second, second_key, tamper=True))

der = attached(b'Documento in Base64', first, first_key)
encoded = base64.encodebytes(der)
out.joinpath('base64.p7m').write_bytes(encoded)
out.joinpath('pem.p7m').write_bytes(b'-----BEGIN PKCS7-----\r\n' + encoded.replace(b'\n', b'\r\n') + b'-----END PKCS7-----\r\n')

PLACEHOLDER = 16384


def signed_revision(prefix, number, cert, key, subfilter=b'ETSI.CAdES.detached'):
    """Append a signature dictionary and sign every byte except /Contents."""
    body = prefix + (b'%d 0 obj\n<</Type/Sig/Filter/Adobe.PPKLite/SubFilter/' % number) + subfilter + \
        b'/ByteRange [0 0000000000 0000000000 0000000000]/Contents <' + b'0' * PLACEHOLDER + \
        b'>>>\nendobj\ntrailer\n<</Root 1 0 R>>\n%%EOF\n'
    start = body.index(b'/Contents <', len(prefix)) + len(b'/Contents ')
    end = start + PLACEHOLDER + 2
    ranges = b'[0 %010d %010d %010d]' % (start, end, len(body) - end)
    marker = b'[0 0000000000 0000000000 0000000000]'
    body = body[:body.index(marker, len(prefix))] + ranges + body[body.index(marker, len(prefix)) + len(marker):]
    cms_der = detached(body[:start] + body[end:], cert, key)
    hex_value = cms_der.hex().encode().ljust(PLACEHOLDER, b'0')
    return body[:start + 1] + hex_value + body[end - 1:]


first_revision = b'%PDF-1.7\n1 0 obj\n<</Type/Catalog>>\nendobj\n'
pades = signed_revision(first_revision, 2, first, first_key)
out.joinpath('pades.pdf').write_bytes(pades)
tampered = pades.replace(b'/Type/Catalog', b'/Type/Catalgg', 1)
out.joinpath('pades_tampered.pdf').write_bytes(tampered)
out.joinpath('pades_two.pdf').write_bytes(signed_revision(pades, 3, second, second_key))
out.joinpath('pades_unsupported.pdf').write_bytes(signed_revision(first_revision, 2, first, first_key, b'adbe.pkcs7.sha1'))
out.joinpath('pades.pdf.p7m').write_bytes(attached(pades, second, second_key))

docx = BytesIO()
with zipfile.ZipFile(docx, 'w', zipfile.ZIP_DEFLATED) as z:
    z.writestr('[Content_Types].xml', '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
    z.writestr('word/document.xml', '<?xml version="1.0" encoding="UTF-8"?>'
               '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
               '<w:p><w:r><w:t>Integrazione</w:t></w:r><w:r><w:t xml:space="preserve"> documentale</w:t></w:r></w:p>'
               '<w:p><w:r><w:t>Seconda riga con accenti: è già</w:t></w:r></w:p>'
               '</w:body></w:document>')
out.joinpath('sample.docx').write_bytes(docx.getvalue())
out.joinpath('sample.docx.p7m').write_bytes(attached(docx.getvalue(), first, first_key))
print('fixtures ok')
