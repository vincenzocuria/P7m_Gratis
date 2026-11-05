import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:p7m_gratis/main.dart';
import 'package:p7m_gratis/help.dart';

void main() {
  for (final extension in ['xml', 'pdf', 'doc', 'docx', 'png', 'txt']) {
    testWidgets(
      'Salva mostra nomi reali per $extension, anche su schermo piccolo',
      (tester) async {
        tester.view.physicalSize = const Size(320, 480);
        tester.view.devicePixelRatio = 1;
        addTearDown(tester.view.resetPhysicalSize);
        addTearDown(tester.view.resetDevicePixelRatio);
        await tester.pumpWidget(
          MaterialApp(
            home: ExportDocumentDialog(
              originalName: 'documento.$extension.p7m',
              extractedName: 'documento.$extension',
            ),
          ),
        );
        expect(
          find.textContaining('documento.$extension.p7m\n'),
          findsOneWidget,
        );
        expect(find.textContaining('documento.$extension\n'), findsOneWidget);
        expect(tester.takeException(), isNull);
      },
    );
  }
  testWidgets(
    'Esportazione permette originale firmato, estratto e annullamento',
    (tester) async {
      bool? selection;
      await tester.pumpWidget(
        MaterialApp(
          home: Builder(
            builder: (context) {
              return TextButton(
                onPressed: () async {
                  selection = await showDialog<bool>(
                    context: context,
                    builder: (_) => const ExportDocumentDialog(
                      originalName: 'fattura.xml.p7m',
                      extractedName: 'fattura.xml',
                    ),
                  );
                },
                child: const Text('Esporta'),
              );
            },
          ),
        ),
      );
      for (final option in {
        'Originale completo con le firme': true,
        'Solo documento estratto': false,
        'Annulla': null,
      }.entries) {
        await tester.tap(find.text('Esporta'));
        await tester.pumpAndSettle();
        expect(find.textContaining('fattura.xml.p7m'), findsOneWidget);
        expect(find.textContaining('fattura.xml\n'), findsOneWidget);
        await tester.tap(find.text(option.key));
        await tester.pumpAndSettle();
        expect(selection, option.value);
      }
    },
  );
  testWidgets('Guida facoltativa e informativa completa disponibili offline', (
    tester,
  ) async {
    await tester.pumpWidget(const MaterialApp(home: HelpPage()));
    expect(find.text('1. Apri un documento'), findsOneWidget);
    await tester.scrollUntilVisible(find.text('3. Comprendi le firme'), 150);
    expect(find.textContaining('Non accertata significa'), findsOneWidget);
    await tester.pumpWidget(const MaterialApp(home: PrivacyPage()));
    await tester.runAsync(() async {
      await Future<void>.delayed(const Duration(milliseconds: 100));
    });
    await tester.pumpAndSettle();
    final text = tester
        .widget<SelectableText>(find.byType(SelectableText))
        .data!;
    expect(text, contains('support@vcuria.app'));
    expect(text, contains('24 ore'));
    expect(text, contains('PAdES'));
  });
  testWidgets('Nome lungo compatto, dettagli leggibili e comandi accessibili', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(320, 480);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final name = '${List.filled(40, 'Documento lungo').join(' ')}.pdf';
    var saves = 0;
    var shares = 0;
    for (final scale in [1.0, 2.0]) {
      await tester.pumpWidget(
        MaterialApp(
          home: MediaQuery(
            data: MediaQueryData(textScaler: TextScaler.linear(scale)),
            child: Scaffold(
              body: Column(
                children: [
                  DocumentHeader(
                    name: name,
                    isPlainPdf: true,
                    onSave: () => saves++,
                    onShare: () => shares++,
                  ),
                  const Expanded(child: Placeholder()),
                ],
              ),
            ),
          ),
        ),
      );
      expect(tester.takeException(), isNull);
      expect(tester.getSize(find.byType(DocumentHeader)).height, lessThan(110));
      expect(tester.getSize(find.byType(Placeholder)).height, greaterThan(370));
      await tester.tap(find.byTooltip('Salva'));
      await tester.tap(find.byTooltip('Condividi'));
      await tester.tap(find.text(name));
      await tester.pumpAndSettle();
      expect(find.byType(SelectableText), findsOneWidget);
      expect(
        find.textContaining('non sono state rilevate firme'),
        findsOneWidget,
      );
      await tester.tap(find.text('Chiudi'));
      await tester.pumpAndSettle();
    }
    expect(saves, 2);
    expect(shares, 2);
  });
  testWidgets('Apertura documenti', (tester) async {
    await tester.pumpWidget(const P7mApp());
    expect(find.text('Apri un P7M o PDF'), findsOneWidget);
  });
  testWidgets('Informazioni sviluppatore, sito e versione desktop', (
    tester,
  ) async {
    await tester.pumpWidget(const P7mApp());
    await tester.tap(find.byTooltip('Informazioni e sviluppatore'));
    await tester.pumpAndSettle();
    expect(find.text('Sviluppata da Vincenzo Curia'), findsOneWidget);
    expect(find.text('Scopri vcuria.app'), findsOneWidget);
    expect(find.text('Versione desktop Windows'), findsOneWidget);
    await tester.tap(find.text('Chiudi'));
    await tester.pumpAndSettle();
    expect(find.text('Sviluppata da Vincenzo Curia'), findsNothing);
  });
  testWidgets('Schermo piccolo senza overflow', (tester) async {
    tester.view.physicalSize = const Size(320, 480);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(const P7mApp());
    expect(tester.takeException(), isNull);
  });
  testWidgets('Allegati ricevuti durante la verifica non persi', (
    tester,
  ) async {
    await tester.pumpWidget(const P7mApp());
    final dynamic state = tester.state(find.byType(Home));
    await tester.runAsync(() async {
      final bytes = File('test/fixtures/valid.p7m').readAsBytesSync();
      final first = state.receive({
        'bytes': bytes,
        'name': 'primo.txt.p7m',
      }) as Future<void>;
      await state.receive({'bytes': bytes, 'name': 'secondo.txt.p7m'});
      await first;
      for (var i = 0; i < 200 && state.doc?.name != 'secondo.txt'; i++) {
        await Future<void>.delayed(const Duration(milliseconds: 10));
      }
      expect(state.doc?.name, 'secondo.txt');
    });
    await tester.pumpAndSettle();
    expect(find.text('secondo.txt'), findsOneWidget);
    await tester.tap(find.text('Firme'));
    await tester.pumpAndSettle();
    expect(find.byIcon(Icons.check_circle_outline), findsNothing);
  });
}
