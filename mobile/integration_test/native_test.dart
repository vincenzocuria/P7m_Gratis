import 'dart:convert';
import 'dart:io';
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:p7m_gratis/main.dart';
import 'package:pdfrx/pdfrx.dart';

import 'fixtures.dart';

void main() {
  final binding = IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  testWidgets('Apertura, motore nativo, testo e PDF sul dispositivo', (
    tester,
  ) async {
    await tester.pumpWidget(const P7mApp());
    await tester.pumpAndSettle();
    if (Platform.isAndroid) await binding.convertFlutterSurfaceToImage();
    await tester.pumpAndSettle();
    await binding.takeScreenshot('welcome');
    final dynamic state = tester.state(find.byType(Home));
    await state.receive({
      'bytes': base64Decode(textP7m),
      'name': 'documento.txt.p7m',
    });
    for (
      var i = 0;
      i < 100 && state.assessments.any((dynamic a) => a == null);
      i++
    ) {
      await tester.pump(const Duration(milliseconds: 100));
    }
    await tester.pumpAndSettle();
    expect(find.text('documento.txt'), findsOneWidget);
    expect(find.text('Documento di prova mobile'), findsOneWidget);
    expect(
      state.assessments.single.trusted,
      false,
      reason: 'Una radice sintetica incorporata non deve essere fidata; il bridge nativo deve rispondere',
    );
    await tester.tap(find.text('Firme'));
    await tester.pumpAndSettle();
    expect(find.byIcon(Icons.check_circle_outline), findsNothing);
    await binding.takeScreenshot('firme');
    await state.receive({
      'bytes': base64Decode(pdfP7m),
      'name': 'determina.pdf.p7m',
    });
    await tester.pumpAndSettle();
    await tester.tap(find.text('Documento'));
    await tester.pumpAndSettle();
    expect(find.byType(PdfViewer), findsOneWidget);
    await tester.runAsync(() async {
      final pdf = await PdfDocument.openData(state.doc.bytes);
      expect(pdf.pages.length, 1);
      final rendered = await pdf.pages.first.render();
      expect(
        rendered,
        isNotNull,
        reason: 'Il motore nativo deve renderizzare la pagina',
      );
      rendered?.dispose();
      await pdf.dispose();
      await Future<void>.delayed(const Duration(seconds: 3));
    });
    await tester.pumpAndSettle();
    await binding.takeScreenshot('pdf');
    final pdfBytes = state.doc.bytes;
    await state.receive({'bytes': pdfBytes, 'name': 'documento.pdf'});
    await tester.pumpAndSettle();
    expect(state.doc.isPlainPdf, true);
    expect(find.text('PDF semplice • non è una busta P7M'), findsOneWidget);
    expect(find.text('Firme'), findsNothing);
    expect(find.text('Controlla revoca online'), findsNothing);
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(seconds: 3)),
    );
    await tester.pumpAndSettle();
    await binding.takeScreenshot('pdf-semplice');
    await tester.tap(find.byTooltip('Informazioni e sviluppatore'));
    await tester.pumpAndSettle();
    expect(find.text('Sviluppata da Vincenzo Curia'), findsOneWidget);
    // Let the platform compositor present the dialog before capturing its pixels.
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(seconds: 1)),
    );
    await tester.pumpAndSettle();
    await binding.takeScreenshot('informazioni');
    await tester.ensureVisible(find.text('Come funziona'));
    await tester.tap(find.text('Come funziona'));
    await tester.pumpAndSettle();
    expect(find.text('1. Apri un documento'), findsOneWidget);
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(seconds: 1)),
    );
    await tester.pumpAndSettle();
    await binding.takeScreenshot('guida');
    await tester.pageBack();
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Privacy'));
    await tester.tap(find.text('Privacy'));
    await tester.pumpAndSettle();
    final privacy = tester
        .widget<SelectableText>(find.byType(SelectableText))
        .data!;
    expect(privacy, contains('support@vcuria.app'));
    expect(privacy, contains('24 ore'));
    await tester.pageBack();
    await tester.pumpAndSettle();
    await tester.tap(find.text('Chiudi'));
    await tester.pumpAndSettle();
    expect(
      state.doc.isPlainPdf,
      true,
      reason: 'Consultare la guida non perde il documento',
    );
    unawaited(state.clearDocuments() as Future<void>);
    await tester.pumpAndSettle();
    for (var i = 0; i < 50 && state.busy; i++) {
      await tester.pump(const Duration(milliseconds: 100));
    }
    expect(state.busy, false);
    expect(find.byType(PdfViewer), findsNothing);
    expect(find.text('Apri un P7M o PDF'), findsOneWidget);
  });
}
