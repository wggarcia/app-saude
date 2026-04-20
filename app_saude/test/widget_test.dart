import 'package:app_saude/main.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('renderiza o shell principal do app', (tester) async {
    await tester.pumpWidget(const SolusCrtAppSaude());
    await tester.pump();

    expect(find.text('SolusCRT Saude'), findsWidgets);
    expect(find.text('Registrar sintomas'), findsOneWidget);
  });
}
