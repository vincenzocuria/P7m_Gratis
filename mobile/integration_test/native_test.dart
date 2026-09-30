import 'dart:convert';
import 'dart:io';

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
    await tester.pump(const Duration(seconds: 2));
    await binding.takeScreenshot('pdf');
  });
}
