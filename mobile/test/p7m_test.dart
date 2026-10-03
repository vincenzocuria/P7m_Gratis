import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:p7m_gratis/core/p7m.dart';

void main() {
  test('Buste annidate indipendenti dal nome del file', () {
    final d = decodeP7m((
      File('test/fixtures/nested.p7m').readAsBytesSync(),
      'test.txt.p7m',
    ));
    expect(d.signers.length, 2);
    expect(String.fromCharCodes(d.bytes), 'Documento di prova mobile');
  });
  test('Suffisso ripetuto non impedisce estrazione singola', () {
    final d = decodeP7m((
      File('test/fixtures/valid.p7m').readAsBytesSync(),
      'test.txt.p7m.p7m',
    ));
    expect(d.signers.length, 1);
    expect(d.name, 'test.txt');
  });
  test('ASN.1 con profondità eccessiva rifiutato prima del parser', () {
    var bytes = <int>[4, 0];
    for (var i = 0; i < 40; i++) {
      bytes = [0x30, bytes.length, ...bytes];
    }
    expect(
      () => checkAsn1Limits(Uint8List.fromList(bytes)),
      throwsA(isA<FormatException>()),
    );
  });
  for (final kind in [
    'bad_signature',
    'wrong_certificate',
    'missing_digest',
    'duplicate_digest',
    'unknown_hash',
  ]) {
    test('Nessun falso positivo: $kind', () {
      final d = decodeP7m((
        File('test/fixtures/$kind.p7m').readAsBytesSync(),
        'test.txt.p7m',
      ));
      expect(d.signers.single.integrity, isNot(true));
    });
  }
  test('Una busta senza firme non certifica il documento', () {
    final d = decodeP7m((
      File('test/fixtures/no_signers.p7m').readAsBytesSync(),
      'test.txt.p7m',
    ));
    expect(d.signers, isEmpty);
  });
  for (final algorithm in ['valid', 'ec', 'pss', 'multi', 'unsigned']) {
    test('Firma verificata: $algorithm', () {
      final d = decodeP7m((
        File('test/fixtures/$algorithm.p7m').readAsBytesSync(),
        'test.txt.p7m',
      ));
      expect(d.name, 'test.txt');
      expect(String.fromCharCodes(d.bytes), 'Documento di prova mobile');
      expect(
        d.signers.every((s) => s.integrity == true),
        true,
        reason: d.signers.map((s) => s.detail).join('; '),
      );
      expect(d.signers.length, algorithm == 'multi' ? 2 : 1);
    });
  }
  test('Contenuto alterato non accettato', () {
    final d = decodeP7m((
      File('test/fixtures/tampered.p7m').readAsBytesSync(),
      'test.txt.p7m',
    ));
    expect(d.signers.single.integrity, false);
  });
  test('Buste annidate', () {
    final d = decodeP7m((
      File('test/fixtures/nested.p7m').readAsBytesSync(),
      'test.txt.p7m.p7m',
    ));
    expect(d.signers.length, 2);
    expect(d.signers.every((s) => s.integrity == true), true);
    expect(String.fromCharCodes(d.bytes), 'Documento di prova mobile');
  });
  test('Input arbitrario rifiutato', () {
    expect(
      () => decodeP7m((File('pubspec.yaml').readAsBytesSync(), 'bad.p7m')),
      throwsA(anything),
    );
  });
}
