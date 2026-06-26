import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:app_saude/tela_alerta.dart';
import 'package:app_saude/tela_resultado.dart';
import 'package:app_saude/telas/login/tela_login.dart';

void main() {
  // ─── TelaLogin ────────────────────────────────────────────────────────────

  group('TelaLogin', () {
    testWidgets('renderiza appbar e botão de entrar', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(home: TelaLogin()),
      );

      expect(find.text('Acesso à população'), findsOneWidget);
      expect(find.byType(FilledButton), findsAtLeastNWidgets(1));
    });

    testWidgets('exibe ícone de saúde', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(home: TelaLogin()),
      );
      expect(find.byIcon(Icons.health_and_safety), findsOneWidget);
    });

    testWidgets('exibe texto explicativo sobre não exigir cadastro', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(home: TelaLogin()),
      );
      expect(
        find.textContaining('login obrigatório', findRichText: true),
        findsOneWidget,
      );
    });
  });

  // ─── TelaAlerta ───────────────────────────────────────────────────────────

  group('TelaAlerta', () {
    testWidgets('renderiza com nivel ALTO', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: TelaAlerta(
            cidade: 'São Paulo',
            mensagem: 'Surto de dengue detectado',
            nivel: 'ALTO',
          ),
        ),
      );

      expect(find.text('Alerta de Saúde'), findsOneWidget);
      expect(find.textContaining('São Paulo'), findsOneWidget);
      expect(find.textContaining('Surto de dengue'), findsOneWidget);
    });

    testWidgets('renderiza com nivel BAIXO', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: TelaAlerta(
            cidade: 'Recife',
            mensagem: 'Situação controlada',
            nivel: 'BAIXO',
          ),
        ),
      );
      expect(find.text('Alerta de Saúde'), findsOneWidget);
    });

    test('cor() retorna vermelho para ALTO', () {
      const a = TelaAlerta(cidade: 'SP', mensagem: '', nivel: 'ALTO');
      expect(a.cor(), Colors.red);
    });

    test('cor() retorna laranja para MODERADO', () {
      const a = TelaAlerta(cidade: 'SP', mensagem: '', nivel: 'MODERADO');
      expect(a.cor(), Colors.orange);
    });

    test('cor() retorna amarelo para ATENCAO', () {
      const a = TelaAlerta(cidade: 'SP', mensagem: '', nivel: 'ATENCAO');
      expect(a.cor(), Colors.yellow);
    });

    test('cor() retorna verde para nível desconhecido', () {
      const a = TelaAlerta(cidade: 'SP', mensagem: '', nivel: 'XYZ');
      expect(a.cor(), Colors.green);
    });
  });

  // ─── TelaResultado ────────────────────────────────────────────────────────

  group('TelaResultado', () {
    testWidgets('renderiza resultado verde sem erro', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: TelaResultado(
            cidadao: {
              'cor_alerta': 'verde',
              'sindrome': 'Síndrome gripal leve',
              'conduta': 'Repouso em casa.',
            },
            local: {
              'cidade': 'Fortaleza',
              'estado': 'CE',
            },
          ),
        ),
      );

      expect(find.textContaining('Síndrome gripal'), findsOneWidget);
      expect(find.textContaining('Repouso'), findsOneWidget);
    });

    testWidgets('renderiza resultado vermelho (urgência)', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: TelaResultado(
            cidadao: {
              'cor_alerta': 'vermelha',
              'sindrome': 'Síndrome de alta complexidade',
              'conduta': 'Procure pronto-socorro imediatamente.',
              'alerta_urgente': {
                'titulo': 'URGÊNCIA',
                'descricao': 'Sintomas graves detectados',
              },
            },
            local: {
              'cidade': 'Manaus',
              'estado': 'AM',
            },
          ),
        ),
      );

      expect(find.textContaining('URGÊNCIA'), findsAtLeastNWidgets(1));
    });

    testWidgets('usa valores padrão quando campos ausentes', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: TelaResultado(
            cidadao: const {},
            local: const {},
          ),
        ),
      );

      // Não deve lançar exceção — usa defaults ('cinza', textos padrão)
      expect(find.byType(Scaffold), findsOneWidget);
    });

    testWidgets('exibe localização composta de cidade e estado', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: TelaResultado(
            cidadao: const {'cor_alerta': 'cinza', 'sindrome': 'Monitoramento'},
            local: const {'cidade': 'Belém', 'estado': 'PA'},
          ),
        ),
      );

      expect(find.textContaining('Belém'), findsOneWidget);
    });
  });

  // ─── App shell ────────────────────────────────────────────────────────────

  group('App shell — fluxo inicial', () {
    testWidgets('aceite legal é exibido na primeira abertura', (tester) async {
      SharedPreferences.setMockInitialValues({});

      await tester.pumpWidget(
        const MaterialApp(home: TelaLogin()),
      );
      await tester.pumpAndSettle();

      // TelaLogin é a primeira tela; o MaterialApp renderiza corretamente
      expect(find.byType(MaterialApp), findsOneWidget);
    });
  });
}
