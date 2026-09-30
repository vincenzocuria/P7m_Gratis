import 'package:flutter_test/flutter_test.dart';
import 'package:p7m_gratis/main.dart';

void main() {
  testWidgets('Apertura documenti', (tester) async {
    await tester.pumpWidget(const P7mApp());
    expect(find.text('Apri un documento P7M'), findsOneWidget);
  });
}
