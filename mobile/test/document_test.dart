import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:p7m_gratis/core/p7m.dart';

void main() {
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
