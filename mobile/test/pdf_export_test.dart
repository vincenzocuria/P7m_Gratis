import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pdfrx/pdfrx.dart';
import 'package:p7m_gratis/pdf_export.dart';
import 'package:p7m_gratis/core/p7m.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('Conferma richiesta ogni volta, nessun consenso preselezionato', (
    tester,
  ) async {
    bool? result;
    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (context) {
            return TextButton(
              onPressed: () async {
                result = await showDialog<bool>(
                  context: context,
                  builder: (_) => const PdfExportConsentDialog(),
                );
              },
              child: const Text('Esporta'),
            );
          },
        ),
      ),
    );
    await tester.tap(find.text('Esporta'));
    await tester.pumpAndSettle();
    expect(
      tester.widget<FilledButton>(find.byType(FilledButton)).onPressed,
      isNull,
    );
    expect(find.textContaining('colpa grave'), findsOneWidget);
    await tester.ensureVisible(find.byType(CheckboxListTile));
    await tester.tap(find.byType(CheckboxListTile));
    await tester.pump();
    await tester.tap(find.text('Crea copia senza password'));
    await tester.pumpAndSettle();
    expect(result, true);
    await tester.tap(find.text('Esporta'));
    await tester.pumpAndSettle();
    expect(
      tester.widget<FilledButton>(find.byType(FilledButton)).onPressed,
      isNull,
    );
    await tester.tap(find.text('Annulla'));
    await tester.pumpAndSettle();
    expect(result, false);
  });

  group('Motore PDF nativo', () {
    setUpAll(() async {
      await pdfrxInitialize();
    });

    for (final algorithm in ['rc4-128', 'aes-256']) {
      test(
        'Copia $algorithm senza password, originale ancora protetto',
        () async {
          final source = File('test/fixtures/encrypted_$algorithm.pdf')
              .readAsBytesSync();
          var attempts = 0;
          final copy = await pdfWithoutPassword(
            source,
            passwordProvider: () {
              attempts++;
              return attempts == 1 ? 'errata' : 'test-password';
            },
          );
          expect(attempts, 2);
          final opened = await PdfDocument.openData(copy);
          try {
            expect(opened.isEncrypted, false);
            expect(opened.pages.length, 2);
            expect(opened.pages.first.width, 595);
            expect(opened.pages.last.width, 420);
          } finally {
            await opened.dispose();
          }
          await expectLater(
            PdfDocument.openData(source),
            throwsA(isA<PdfPasswordException>()),
          );
          final model = decodeDocument((source, 'firmato.pdf'));
          expect(model.pdfSignaturesUncertain, true);
          expect(model.originalBytes, orderedEquals(source));
        },
      );
    }

    test('Annullamento non produce una copia', () async {
      final source = File('test/fixtures/encrypted_aes-256.pdf')
          .readAsBytesSync();
      await expectLater(
        pdfWithoutPassword(source, passwordProvider: () => null),
        throwsA(isA<PdfPasswordException>()),
      );
    });
    test(
      'PDF cifrato dentro P7M: estrazione, firma e copia senza password',
      () async {
        final envelope = File('test/fixtures/encrypted_aes-256.pdf.p7m')
            .readAsBytesSync();
        final model = decodeDocument((envelope, 'documento.pdf.p7m'));
        expect(model.isPlainPdf, false);
        expect(model.pdfSignaturesUncertain, true);
        expect(model.signers.first.integrity, true);
        final copy = await pdfWithoutPassword(
          model.bytes,
          passwordProvider: () => 'test-password',
        );
        final opened = await PdfDocument.openData(copy);
        try {
          expect(opened.isEncrypted, false);
          expect(opened.pages.length, 2);
        } finally {
          await opened.dispose();
        }
        expect(model.originalBytes, orderedEquals(envelope));
        expect(
          decodeDocument((model.originalBytes!, model.originalName!))
              .signers
              .first
              .integrity,
          true,
        );
      },
    );
  });
}
