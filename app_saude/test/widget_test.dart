import 'package:app_saude/main.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  testWidgets('renderiza o shell principal do app', (tester) async {
    SharedPreferences.setMockInitialValues({});

    await tester.pumpWidget(const SolusCrtAppSaude());
    await tester.pumpAndSettle();

    expect(find.byType(MaterialApp), findsOneWidget);
    expect(find.byType(Scaffold), findsAtLeastNWidgets(1));
    expect(find.text('Antes de continuar'), findsOneWidget);
  });
}
