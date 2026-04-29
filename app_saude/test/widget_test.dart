import 'package:app_saude/main.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('renderiza o shell principal do app', (tester) async {
    await tester.pumpWidget(const SolusCrtAppSaude());
<<<<<<< Updated upstream
    await tester.pump(const Duration(milliseconds: 300));

    expect(find.byType(MaterialApp), findsOneWidget);
    expect(find.byType(Scaffold), findsAtLeastNWidgets(1));
=======
    await tester.pump(const Duration(milliseconds: 250));

    final hasLoading = find.byType(CircularProgressIndicator).evaluate().isNotEmpty;
    final hasLegalGate = find.text('Antes de continuar').evaluate().isNotEmpty;

    expect(find.byType(MaterialApp), findsOneWidget);
    expect(hasLoading || hasLegalGate, isTrue);
>>>>>>> Stashed changes
  });
}
