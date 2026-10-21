import 'dart:io';
import 'dart:typed_data';

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
    expect(
      d.signers.every((s) => s.integrity == true),
      true,
      reason: details(d),
    );
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
    expect(
      d.signers.every((s) => s.integrity == true),
      true,
      reason: details(d),
    );
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
    expect(
      d.signers.every((s) => s.integrity == true),
      true,
      reason: details(d),
    );
    expect(d.signers[1].role, contains('PDF estratto'));
  });
  test('Anteprima testo Word', () {
    final text = officeText(
      File('test/fixtures/sample.docx').readAsBytesSync(),
    );
    expect(text, 'Integrazione documentale\nSeconda riga con accenti: è già');
    final d = open('sample.docx.p7m');
    expect(d.name, 'sample.docx');
    expect(officeText(d.bytes), text);
  });
  test('Anteprima Word rifiuta file non validi', () {
    expect(officeText(File('pubspec.yaml').readAsBytesSync()), isNull);
  });
  test('Anteprima testo Word 97-2003 (.doc)', () {
    final bytes = File('test/fixtures/sample.doc').readAsBytesSync();
    // cp1252 piece (en dash, è), UTF-16 piece with a PAGE field, footnote
    // text past ccpText left out.
    const expected = 'Comune di prova – è\nCampo: 1 fine €';
    expect(officeText(bytes), expected);
    expect(officeExtensions, contains('doc'));
    final d = open('sample.doc.p7m');
    expect(d.name, 'sample.doc');
    expect(d.signers.single.integrity, true, reason: details(d));
    expect(officeText(d.bytes), expected);
  });
  test('Documento OLE2 senza estensione diventa .doc', () {
    final d = open('word97.p7m');
    expect(d.name, 'word97.doc');
    expect(officeText(d.bytes), isNotNull);
    final bytes = File('test/fixtures/sample.doc').readAsBytesSync();
    expect(documentName('documento', bytes), 'documento.doc');
    expect(documentName('atto.doc', bytes), 'atto.doc');
  });
  test('Anteprima .doc rifiuta file cifrati e malformati', () {
    expect(
      officeText(File('test/fixtures/encrypted.doc').readAsBytesSync()),
      isNull,
    );
    final bytes = File('test/fixtures/sample.doc').readAsBytesSync();
    expect(officeText(bytes.sublist(0, 1024)), isNull);
    final looped = Uint8List.fromList(bytes);
    // FAT entry of the directory sector pointing to itself: a chain loop.
    final fatStart = 512, dirSector = 1;
    ByteData.sublistView(looped)
        .setUint32(fatStart + 4 * dirSector, dirSector, Endian.little);
    expect(officeText(looped), isNull);
  });
}
