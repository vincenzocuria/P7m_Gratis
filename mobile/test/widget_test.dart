import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:p7m_gratis/main.dart';

void main() {
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
