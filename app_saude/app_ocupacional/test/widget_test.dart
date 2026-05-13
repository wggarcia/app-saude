import 'package:app_ocupacional/main.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('exibe entrada ocupacional', (WidgetTester tester) async {
    await tester.pumpWidget(const SolusCrtOcupacionalApp());

    expect(find.text('SolusCRT Ocupacional'), findsOneWidget);
    expect(find.text('Empresa'), findsOneWidget);
    expect(find.text('Trabalhador'), findsOneWidget);
  });
}
