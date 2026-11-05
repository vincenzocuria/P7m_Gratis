import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pdfrx/pdfrx.dart';
import 'package:p7m_gratis/pdf_preview.dart';

/// Real PDFium tests: the encrypted fixtures must ask for a password,
/// open with the right one and never leave an empty grey area.
void main() {
  setUpAll(() async => pdfrxInitialize());

  Future<void> settle(WidgetTester tester, bool Function() done) async {
    for (var i = 0; i < 50 && !done(); i++) {
      await tester.runAsync(
        () => Future.delayed(const Duration(milliseconds: 100)),
      );
      await tester.pump(const Duration(milliseconds: 50));
    }
  }

  for (final fixture in ['encrypted_aes-256.pdf', 'encrypted_rc4-128.pdf']) {
    testWidgets('$fixture: chiede la password e si apre', (tester) async {
      final bytes = File('test/fixtures/$fixture').readAsBytesSync();
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: PasswordPdfPreview(bytes: bytes, name: fixture),
          ),
        ),
      );
      await settle(
        tester,
        () => find.byType(PdfPasswordDialog).evaluate().isNotEmpty,
      );
      expect(find.byType(PdfPasswordDialog), findsOneWidget);

      await tester.enterText(find.byType(TextField), 'sbagliata');
      await tester.tap(find.text('Apri'));
      await settle(
        tester,
        () => find.text('Password errata. Riprova.').evaluate().isNotEmpty,
      );
      expect(find.text('Password errata. Riprova.'), findsOneWidget);

      await tester.enterText(find.byType(TextField), 'test-password');
      await tester.tap(find.text('Apri'));
      await settle(
        tester,
        () => find.byType(PdfPasswordDialog).evaluate().isEmpty,
      );
      await settle(tester, () => false);
      expect(find.byType(PdfPasswordDialog), findsNothing);
      expect(find.textContaining('Impossibile aprire'), findsNothing);
      expect(find.textContaining('PDF protetto'), findsNothing);
      expect(find.textContaining('non si è aperto'), findsNothing);
    });
  }

  testWidgets(
    'Annulla mostra un messaggio chiaro e Riprova richiede di nuovo',
    (tester) async {
      final bytes = File('test/fixtures/encrypted_aes-256.pdf')
          .readAsBytesSync();
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: PasswordPdfPreview(bytes: bytes, name: 'a.pdf'),
          ),
        ),
      );
      await settle(
        tester,
        () => find.byType(PdfPasswordDialog).evaluate().isNotEmpty,
      );
      await tester.tap(find.text('Annulla'));
      await settle(tester, () => find.text('Riprova').evaluate().isNotEmpty);
      expect(
        find.text('PDF protetto: inserisci la password per aprirlo.'),
        findsOneWidget,
      );
      await tester.tap(find.text('Riprova'));
      await settle(
        tester,
        () => find.byType(PdfPasswordDialog).evaluate().isNotEmpty,
      );
      expect(find.byType(PdfPasswordDialog), findsOneWidget);
    },
  );

  testWidgets('File non PDF: messaggio di errore, mai area vuota', (
    tester,
  ) async {
    final bytes = File('test/fixtures/sample.docx').readAsBytesSync();
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: PasswordPdfPreview(bytes: bytes, name: 'rotto.pdf'),
        ),
      ),
    );
    await settle(tester, () => find.text('Riprova').evaluate().isNotEmpty);
    expect(find.textContaining('Impossibile aprire il PDF'), findsOneWidget);
  });
}
