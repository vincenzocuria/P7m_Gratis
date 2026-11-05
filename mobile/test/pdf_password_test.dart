import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:p7m_gratis/pdf_preview.dart';

void main() {
  Future<void> openDialog(WidgetTester tester, {bool incorrect = false}) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (context) {
            return Scaffold(
              body: TextButton(
                onPressed: () async {
                  final result = await showDialog<String>(
                    context: context,
                    builder: (_) => PdfPasswordDialog(incorrect: incorrect),
                  );
                  if (context.mounted) {
                    ScaffoldMessenger.of(context).showSnackBar(
                      SnackBar(
                        content: Text(
                          result == null ? 'Annullato' : 'Valore:[$result]',
                        ),
                      ),
                    );
                  }
                },
                child: const Text('Test'),
              ),
            );
          },
        ),
      ),
    );
    await tester.tap(find.text('Test'));
    await tester.pumpAndSettle();
  }

  testWidgets('Password nascosta, visibilità e invio senza rimuovere spazi', (
    tester,
  ) async {
    await openDialog(tester);
    expect(
      tester.widget<TextField>(find.byType(TextField)).obscureText,
      isTrue,
    );
    await tester.enterText(find.byType(TextField), ' segreto ');
    await tester.tap(find.byTooltip('Mostra password'));
    await tester.pump();
    expect(
      tester.widget<TextField>(find.byType(TextField)).obscureText,
      isFalse,
    );
    await tester.testTextInput.receiveAction(TextInputAction.done);
    await tester.pumpAndSettle();
    expect(find.text('Valore:[ segreto ]'), findsOneWidget);
  });

  testWidgets('Password errata: riprova oppure annulla', (tester) async {
    await openDialog(tester, incorrect: true);
    expect(find.text('Password errata. Riprova.'), findsOneWidget);
    await tester.tap(find.text('Annulla'));
    await tester.pumpAndSettle();
    expect(find.text('Annullato'), findsOneWidget);
    expect(find.byType(PdfPasswordDialog), findsNothing);
  });
}
