import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:p7m_gratis/core/office_preview.dart';
import 'package:p7m_gratis/core/p7m.dart';

P7mDocument open(String name) =>
    decodeDocument((File('test/fixtures/$name').readAsBytesSync(), name));

String details(P7mDocument d) =>
    d.signers.map((s) => '${s.role}: ${s.detail}').join('; ');

void main() {
  test('Firma e controfirma verificate', () {
    final d = open('countersigned.p7m');
    expect(String.fromCharCodes(d.bytes), 'Documento firmato e controfirmato');
    expect(d.signers.length, 2, reason: details(d));
    expect(d.signers.every((s) => s.integrity == true), true,
        reason: details(d));
    expect(d.signers[0].role, isEmpty);
    expect(d.signers[1].role, startsWith('Controfirma di '));
    expect(d.signers[1].name, contains('Controfirmatario'));
  });
  test('Controfirma alterata non accettata', () {
    final d = open('countersigned_bad.p7m');
    expect(d.signers[0].integrity, true);
    expect(d.signers[1].integrity, false);
  });
  for (final name in ['base64.p7m', 'pem.p7m']) {
    test('P7M in Base64: $name', () {
      final d = open(name);
      expect(String.fromCharCodes(d.bytes), 'Documento in Base64');
      expect(d.signers.single.integrity, true, reason: details(d));
    });
  }
  test('PDF con firma PAdES verificata', () {
    final d = open('pades.pdf');
    expect(d.isPlainPdf, true);
    expect(d.signers.single.integrity, true, reason: details(d));
    expect(d.signers.single.role, 'Firma nel PDF');
    expect(d.signers.single.name, contains('Primo firmatario'));
  });
  test('PDF alterato dopo la firma PAdES', () {
    final d = open('pades_tampered.pdf');
    expect(d.signers.single.integrity, false);
  });
  test('PDF con due firme PAdES successive', () {
    final d = open('pades_two.pdf');
    expect(d.signers.length, 2, reason: details(d));
    expect(d.signers.every((s) => s.integrity == true), true,
        reason: details(d));
    expect(d.signers[0].detail, contains('modificato dopo questa firma'));
    expect(d.signers[1].detail, isNot(contains('modificato dopo')));
  });
  test('Tipo di firma PDF non supportato non certificato', () {
    final d = open('pades_unsupported.pdf');
    expect(d.signers.single.integrity, isNull);
    expect(d.signers.single.detail, contains('non supportato'));
  });
  test('PDF semplice senza firme', () {
    final d = decodeDocument((
      File('test/fixtures/pades.pdf').readAsBytesSync().sublist(0, 40),
      'semplice.pdf',
    ));
    expect(d.signers, isEmpty);
  });
  test('CAdES intorno a un PDF PAdES', () {
    final d = open('pades.pdf.p7m');
    expect(d.name, 'pades.pdf');
    expect(d.signers.length, 2, reason: details(d));
    expect(d.signers.every((s) => s.integrity == true), true,
        reason: details(d));
    expect(d.signers[1].role, contains('PDF estratto'));
  });
  test('Anteprima testo Word', () {
    final text = officeText(File('test/fixtures/sample.docx').readAsBytesSync());
    expect(text, 'Integrazione documentale\nSeconda riga con accenti: è già');
    final d = open('sample.docx.p7m');
    expect(d.name, 'sample.docx');
    expect(officeText(d.bytes), text);
  });
  test('Anteprima Word rifiuta file non validi', () {
    expect(officeText(File('pubspec.yaml').readAsBytesSync()), isNull);
  });
}
