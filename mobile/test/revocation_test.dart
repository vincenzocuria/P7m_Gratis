import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:pkcs7/pkcs7.dart' show X509;
import 'package:p7m_gratis/core/revocation.dart';
import 'package:p7m_gratis/core/p7m.dart';
import 'package:p7m_gratis/core/timestamp.dart';

void main() {
  final leaf = X509.fromDer(File('test/fixtures/leaf.der').readAsBytesSync());
  final issuer = X509.fromDer(File('test/fixtures/root.der').readAsBytesSync());
  final now = DateTime.parse(
    File('test/fixtures/validation_time.txt').readAsStringSync(),
  );
  for (final kind in [
    'good',
    'revoked',
    'expired',
    'wrong_signature',
    'partial',
  ]) {
    test('CRL autentica: $kind', () {
      final bytes = File('test/fixtures/crl_$kind.der').readAsBytesSync();
      if (kind == 'good' || kind == 'revoked') {
        expect(
          validateCrl(bytes, leaf, issuer, at: now),
          kind == 'good' ? RevocationStatus.good : RevocationStatus.revoked,
        );
      } else {
        expect(
          () => validateCrl(bytes, leaf, issuer, at: now),
          throwsA(anything),
        );
      }
    });
  }
  for (final kind in [
    'good',
    'revoked',
    'expired',
    'wrong_signature',
    'wrong_cert',
    'delegated',
    'delegated_no_check_missing',
  ]) {
    test('OCSP autentico: $kind', () {
      final bytes = File('test/fixtures/ocsp_$kind.der').readAsBytesSync();
      if (['good', 'revoked', 'delegated'].contains(kind)) {
        expect(
          validateOcsp(bytes, leaf, issuer, at: now),
          kind == 'revoked' ? RevocationStatus.revoked : RevocationStatus.good,
        );
      } else {
        expect(
          () => validateOcsp(bytes, leaf, issuer, at: now),
          throwsA(anything),
        );
      }
    });
  }
  test('SKI identifica il certificato corretto', () {
    final doc = decodeP7m((
      File('test/fixtures/ski.p7m').readAsBytesSync(),
      'test.txt.p7m',
    ));
    expect(doc.signers.single.integrity, true);
    expect(doc.signers.single.certificate, isNotNull);
  });
  test('Marca RFC 3161 verifica firma e impronta', () {
    final doc = decodeP7m((
      File('test/fixtures/timestamped.p7m').readAsBytesSync(),
      'test.txt.p7m',
    ));
    final signer = doc.signers.single;
    expect(signer.integrity, true);
    final stamp = inspectTimestamp((
      signer.timestampTokens.single,
      signer.signatureBytes!,
    ));
    expect(stamp.integrity, true, reason: stamp.detail);
    expect(stamp.time, now);
  });
  test('Marca relativa a un’altra firma rifiutata', () {
    final doc = decodeP7m((
      File('test/fixtures/timestamped.p7m').readAsBytesSync(),
      'test.txt.p7m',
    ));
    final signer = doc.signers.single;
    final bytes = signer.signatureBytes!;
    bytes[0] ^= 1;
    expect(
      inspectTimestamp((signer.timestampTokens.single, bytes)).integrity,
      false,
    );
  });
  test('La richiesta OCSP contiene il CertID', () {
    final request = sequence(ocspRequest(leaf, issuer));
    expect(request.elements, isNotEmpty);
  });
  test('Gli endpoint della busta sono letti senza richieste di rete', () {
    expect(endpoints(leaf, true), ['https://example.com/ocsp']);
    expect(endpoints(leaf, false), ['https://example.com/list.crl']);
  });
  for (final address in [
    '127.0.0.1',
    '10.0.0.1',
    '192.168.1.1',
    '169.254.169.254',
    '100.64.0.1',
    '::1',
    'fe80::1',
    'fc00::1',
    '::ffff:127.0.0.1',
    '2001:db8::1',
  ]) {
    test(
      'Endpoint locale rifiutato: $address',
      () => expect(publicAddress(InternetAddress(address)), false),
    );
  }
}
