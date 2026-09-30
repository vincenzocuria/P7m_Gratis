"""Synthetic adversarial fixtures. Requires repository Python dependencies."""
from pathlib import Path
from datetime import datetime, timedelta, timezone
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
from cryptography.x509 import ocsp
from asn1crypto import cms, tsp, algos

out=Path(__file__).resolve().parents[1]/'test'/'fixtures'
now=datetime.now(timezone.utc).replace(microsecond=0)
out.joinpath('validation_time.txt').write_text(now.isoformat())
name=lambda text:x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,text)])
key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
other=rsa.generate_private_key(public_exponent=65537,key_size=2048)
leaf_key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
base=lambda subject,issuer,pub,serial:x509.CertificateBuilder().subject_name(subject).issuer_name(issuer).public_key(pub).serial_number(serial).not_valid_before(now-timedelta(days=100)).not_valid_after(now+timedelta(days=100))
root=base(name('Test Root'),name('Test Root'),key.public_key(),501).add_extension(x509.BasicConstraints(ca=True,path_length=2),True).add_extension(x509.KeyUsage(True,False,False,False,False,True,True,False,False),True).sign(key,hashes.SHA256())
leaf=base(name('Test signer'),root.subject,leaf_key.public_key(),502).add_extension(x509.BasicConstraints(ca=False,path_length=None),True).add_extension(x509.KeyUsage(True,True,False,False,False,False,False,False,False),True).add_extension(x509.SubjectKeyIdentifier.from_public_key(leaf_key.public_key()),False).add_extension(x509.AuthorityInformationAccess([x509.AccessDescription(x509.oid.AuthorityInformationAccessOID.OCSP,x509.UniformResourceIdentifier('https://example.com/ocsp'))]),False).add_extension(x509.CRLDistributionPoints([x509.DistributionPoint(full_name=[x509.UniformResourceIdentifier('https://example.com/list.crl')],relative_name=None,reasons=None,crl_issuer=None)]),False).sign(key,hashes.SHA256())
wrong_root=base(root.subject,root.subject,other.public_key(),503).add_extension(x509.BasicConstraints(ca=True,path_length=2),True).sign(other,hashes.SHA256())
for text,cert in [('root',root),('leaf',leaf),('wrong_root',wrong_root)]:out.joinpath(text+'.der').write_bytes(cert.public_bytes(serialization.Encoding.DER))
for kind in ['good','revoked','expired','wrong_signature','partial']:
 b=x509.CertificateRevocationListBuilder().issuer_name(root.subject).last_update(now-timedelta(hours=1)).next_update(now+timedelta(days=1) if kind!='expired' else now-timedelta(minutes=1))
 if kind=='revoked': b=b.add_revoked_certificate(x509.RevokedCertificateBuilder().serial_number(leaf.serial_number).revocation_date(now-timedelta(minutes=30)).build())
 if kind=='partial': b=b.add_extension(x509.IssuingDistributionPoint(full_name=None,relative_name=None,only_contains_user_certs=True,only_contains_ca_certs=False,only_some_reasons=None,indirect_crl=False,only_contains_attribute_certs=False),True)
 crl=b.sign(other if kind=='wrong_signature' else key,hashes.SHA256())
 out.joinpath('crl_'+kind+'.der').write_bytes(crl.public_bytes(serialization.Encoding.DER))
for kind in ['good','revoked','expired','wrong_signature','wrong_cert','delegated','delegated_no_check_missing']:
 responder=root; responder_key=key
 if kind.startswith('delegated'):
  responder_key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
  b=base(name('OCSP responder'),root.subject,responder_key.public_key(),504).add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.OCSP_SIGNING]),False)
  if kind=='delegated':b=b.add_extension(x509.OCSPNoCheck(),False)
  responder=b.sign(key,hashes.SHA256())
 b=ocsp.OCSPResponseBuilder().add_response(cert=leaf if kind!='wrong_cert' else root,issuer=root,algorithm=hashes.SHA1(),cert_status=ocsp.OCSPCertStatus.REVOKED if kind=='revoked' else ocsp.OCSPCertStatus.GOOD,this_update=now-timedelta(hours=1),next_update=now+timedelta(days=1) if kind!='expired' else now-timedelta(minutes=1),revocation_time=now-timedelta(minutes=30) if kind=='revoked' else None,revocation_reason=None).responder_id(ocsp.OCSPResponderEncoding.HASH,responder)
 if kind.startswith('delegated'): b=b.certificates([responder])
 # OpenSSL rejects a mismatched responder key, so alter the encoded signature afterwards.
 response=b.sign(responder_key,hashes.SHA256()).public_bytes(serialization.Encoding.DER)
 if kind=='wrong_signature':
  from asn1crypto import ocsp as asn_ocsp
  r=asn_ocsp.OCSPResponse.load(response); basic=r['response_bytes']['response'].parsed; sig=bytearray(basic['signature'].native);sig[0]^=1;basic['signature']=bytes(sig);r['response_bytes']['response']=basic;response=r.dump(force=True)
 out.joinpath('ocsp_'+kind+'.der').write_bytes(response)
# SubjectKeyIdentifier CMS variant: the signed bytes remain unchanged.
signed=cms.ContentInfo.load(out.joinpath('valid.p7m').read_bytes())
# Use a separate envelope whose certificate contains an SKI.
from cryptography.hazmat.primitives.serialization import pkcs7
content=pkcs7.PKCS7SignatureBuilder().set_data(b'Documento SKI').add_signer(leaf,leaf_key,hashes.SHA256()).add_certificate(root).sign(serialization.Encoding.DER,[pkcs7.PKCS7Options.Binary])
signed=cms.ContentInfo.load(content); signer=signed['content']['signer_infos'][0]
signer['sid']=cms.SignerIdentifier(name='subject_key_identifier',value=leaf.extensions.get_extension_for_class(x509.SubjectKeyIdentifier).value.digest);signer['version']='v3';signed['content']['version']='v3'
out.joinpath('ski.p7m').write_bytes(signed.dump(force=True))
# RFC 3161 token with critical, exclusive TSA EKU.
tsa=base(name('Test TSA'),root.subject,key.public_key(),506).add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.TIME_STAMPING]),True).sign(key,hashes.SHA256())
original=cms.ContentInfo.load(out.joinpath('valid.p7m').read_bytes()); signature=original['content']['signer_infos'][0]['signature'].native
h=hashes.Hash(hashes.SHA256());h.update(signature)
info=tsp.TSTInfo({'version':'v1','policy':'1.2.3.4','message_imprint':{'hash_algorithm':{'algorithm':'sha256'},'hashed_message':h.finalize()},'serial_number':1001,'gen_time':now})
token=cms.ContentInfo.load(pkcs7.PKCS7SignatureBuilder().set_data(info.dump()).add_signer(tsa,key,hashes.SHA256()).add_certificate(root).sign(serialization.Encoding.DER,[pkcs7.PKCS7Options.Binary]))
token['content']['encap_content_info']['content_type']='tst_info'
token_signer=token['content']['signer_infos'][0]
for attr in token_signer['signed_attrs']:
 if attr['type'].native=='content_type':attr['values']=['tst_info']
# SignedAttrs signature uses the SET tag, not context [0].
attrs=bytearray(token_signer['signed_attrs'].dump(force=True));attrs[0]=0x31
from cryptography.hazmat.primitives.asymmetric import padding
token_signer['signature']=key.sign(bytes(attrs),padding.PKCS1v15(),hashes.SHA256())
out.joinpath('timestamp.der').write_bytes(token.dump(force=True))
original['content']['signer_infos'][0]['unsigned_attrs']=cms.CMSAttributes([cms.CMSAttribute({'type':'signature_time_stamp_token','values':[token]})])
out.joinpath('timestamped.p7m').write_bytes(original.dump(force=True))
