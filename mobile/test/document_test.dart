import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:p7m_gratis/core/p7m.dart';

void main() {
  test('P7S separato segnala che manca il documento originale', () {
    final bytes = File('test/fixtures/encrypted_detached.p7s')
        .readAsBytesSync();
    expect(
      () => decodeDocument((bytes, 'firma.p7s')),
      throwsA(
        isA<FormatException>().having(
          (e) => e.message,
          'message',
          contains('Firma separata'),
        ),
      ),
    );
  });
  for (final extension in ['p7s', 'm7m']) {
    test('SignedData con contenuto e suffisso $extension', () {
      final bytes = File('test/fixtures/valid.p7m').readAsBytesSync();
      final doc = decodeDocument((bytes, 'documento.txt.$extension'));
      expect(doc.name, 'documento.txt');
      expect(doc.originalName, 'documento.txt.$extension');
      expect(doc.signers.first.integrity, true);
    });
  }
  for (final extension in ['tsd', 'm7m']) {
    test('Contenitore $extension non supportato ha un errore specifico', () {
      expect(
        () => decodeDocument((
          Uint8List.fromList([1, 2, 3]),
          'documento.$extension',
        )),
        throwsA(
          isA<FormatException>().having(
            (e) => e.message,
            'message',
            contains('Contenitore ${extension.toUpperCase()} non supportato'),
          ),
        ),
      );
    });
  }
  for (final fixture in ['valid.p7m', 'nested.p7m', 'pades.pdf.p7m']) {
    test('Esportazione conserva tutti i byte originali: $fixture', () {
      final bytes = File('test/fixtures/$fixture').readAsBytesSync();
      final doc = decodeDocument((bytes, 'ricevuto.xml.p7m'));
      expect(doc.originalName, 'ricevuto.xml.p7m');
      expect(doc.originalBytes, orderedEquals(bytes));
      expect(doc.originalBytes, isNot(orderedEquals(doc.bytes)));
      expect(
        decodeDocument((doc.originalBytes!, doc.originalName!)).signers.length,
        doc.signers.length,
      );
    });
  }
  test('PDF riconosciuto dal contenuto senza dichiarare firme P7M', () {
    final bytes = Uint8List.fromList(ascii.encode('%PDF-1.7\nexample'));
    final doc = decodeDocument((bytes, 'documento.pdf'));
    expect(doc.isPlainPdf, true);
    expect(doc.signers, isEmpty);
    expect(doc.bytes, bytes);
  });
  test('Estensione PDF non nasconde una busta P7M', () {
    final doc = decodeDocument((
      File('test/fixtures/valid.p7m').readAsBytesSync(),
      'documento.pdf',
    ));
    expect(doc.isPlainPdf, false);
    expect(doc.signers, isNotEmpty);
  });
  test('Estensione PDF non rende validi dati arbitrari', () {
    expect(
      () => decodeDocument((Uint8List.fromList([1, 2, 3]), 'documento.pdf')),
      throwsFormatException,
    );
  });
}
