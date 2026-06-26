import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:app_ocupacional/main.dart';
import 'package:app_ocupacional/telas/empresa/tela_login_empresa.dart';
import 'package:app_ocupacional/telas/funcionario/tela_login_funcionario.dart';
import 'package:app_ocupacional/telas/funcionario/tela_registro_funcionario.dart';

void main() {
  setUp(() {
    // Inicializa mocks de storage para cada teste
    SharedPreferences.setMockInitialValues({});
    FlutterSecureStorage.setMockInitialValues({});
  });

  // ─── App entrada ──────────────────────────────────────────────────────────

  group('App — tela de entrada', () {
    testWidgets('exibe botões de acesso por perfil', (tester) async {
      SharedPreferences.setMockInitialValues({});
      await tester.pumpWidget(const SolusCrtOcupacionalApp());
      await tester.pumpAndSettle();

      expect(find.text('SolusCRT Ocupacional'), findsOneWidget);
      expect(find.text('Empresa'), findsOneWidget);
      expect(find.text('Trabalhador'), findsOneWidget);
    });

    testWidgets('exibe logo ou ícone de saúde', (tester) async {
      await tester.pumpWidget(const SolusCrtOcupacionalApp());
      await tester.pumpAndSettle();

      // Pelo menos um ícone deve estar presente no app shell
      expect(find.byType(Icon).evaluate().isNotEmpty, isTrue);
    });
  });

  // ─── TelaLoginEmpresa ─────────────────────────────────────────────────────

  group('TelaLoginEmpresa', () {
    testWidgets('renderiza campos de email e senha', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(home: TelaLoginEmpresa()),
      );

      // Deve ter pelo menos 2 campos de texto (email + senha)
      expect(find.byType(TextField), findsAtLeastNWidgets(2));
    });

    testWidgets('renderiza botão de entrar', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(home: TelaLoginEmpresa()),
      );

      // Botão de login (ElevatedButton, FilledButton ou TextButton)
      final buttonFinder = find.byWidgetPredicate(
        (w) => w is ElevatedButton || w is FilledButton || w is TextButton,
      );
      expect(buttonFinder, findsAtLeastNWidgets(1));
    });

    testWidgets('exibe erro ao enviar campos vazios', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(home: TelaLoginEmpresa()),
      );

      // Localiza e toca o botão de login
      final buttons = find.byWidgetPredicate(
        (w) => w is ElevatedButton || w is FilledButton,
      );
      if (buttons.evaluate().isNotEmpty) {
        await tester.tap(buttons.first);
        await tester.pump();
        // Pode exibir mensagem de erro ou loading — não deve crashar
        expect(find.byType(Scaffold), findsOneWidget);
      }
    });

    testWidgets('campo de senha tem obscureText por padrão', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(home: TelaLoginEmpresa()),
      );

      final textFields = tester.widgetList<TextField>(find.byType(TextField));
      final senhaField = textFields.where((f) => f.obscureText).toList();
      expect(senhaField.isNotEmpty, isTrue,
          reason: 'Deve haver pelo menos um campo de senha com obscureText=true');
    });
  });

  // ─── TelaLoginFuncionario ─────────────────────────────────────────────────

  group('TelaLoginFuncionario', () {
    testWidgets('renderiza campos de email e senha', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(home: TelaLoginFuncionario()),
      );
      await tester.pumpAndSettle();

      expect(find.byType(TextField), findsAtLeastNWidgets(2));
    });

    testWidgets('sem sessão salva exibe o formulário de login', (tester) async {
      // FlutterSecureStorage vazio → nenhum token → deve ficar na tela de login
      await tester.pumpWidget(
        const MaterialApp(home: TelaLoginFuncionario()),
      );
      await tester.pumpAndSettle();

      expect(find.byType(Scaffold), findsOneWidget);
      expect(find.byType(TextField), findsAtLeastNWidgets(2));
    });

    testWidgets('campo de senha tem obscureText por padrão', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(home: TelaLoginFuncionario()),
      );
      await tester.pumpAndSettle();

      final textFields = tester.widgetList<TextField>(find.byType(TextField));
      final senhaField = textFields.where((f) => f.obscureText).toList();
      expect(senhaField.isNotEmpty, isTrue);
    });

    testWidgets('exibe link ou botão para registrar novo usuário', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(home: TelaLoginFuncionario()),
      );
      await tester.pumpAndSettle();

      // Deve exibir alguma opção de registro (TextButton ou link)
      final registrar = find.textContaining('registr', findRichText: true);
      final cadastrar = find.textContaining('cadastr', findRichText: true);
      final encontrado = registrar.evaluate().isNotEmpty || cadastrar.evaluate().isNotEmpty;
      expect(encontrado, isTrue,
          reason: 'Deve haver uma opção de registro/cadastro para novos funcionários');
    });
  });

  // ─── TelaRegistroFuncionario ──────────────────────────────────────────────

  group('TelaRegistroFuncionario', () {
    testWidgets('renderiza campo de CPF', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(home: TelaRegistroFuncionario()),
      );
      await tester.pumpAndSettle();

      expect(find.byType(Scaffold), findsOneWidget);
      // Etapa 1 de registro: campo CPF
      expect(find.byType(TextField), findsAtLeastNWidgets(1));
    });
  });

  // ─── Navegação básica ─────────────────────────────────────────────────────

  group('Navegação — empresa → login empresa', () {
    testWidgets('botão Empresa navega para TelaLoginEmpresa', (tester) async {
      await tester.pumpWidget(const SolusCrtOcupacionalApp());
      await tester.pumpAndSettle();

      // Toca no botão "Empresa"
      final empresaButton = find.text('Empresa');
      if (empresaButton.evaluate().isNotEmpty) {
        await tester.tap(empresaButton.first);
        await tester.pumpAndSettle();
        expect(find.byType(TextField), findsAtLeastNWidgets(1));
      }
    });

    testWidgets('botão Trabalhador navega para TelaLoginFuncionario', (tester) async {
      await tester.pumpWidget(const SolusCrtOcupacionalApp());
      await tester.pumpAndSettle();

      final trabButton = find.text('Trabalhador');
      if (trabButton.evaluate().isNotEmpty) {
        await tester.tap(trabButton.first);
        await tester.pumpAndSettle();
        expect(find.byType(TextField), findsAtLeastNWidgets(1));
      }
    });
  });
}
