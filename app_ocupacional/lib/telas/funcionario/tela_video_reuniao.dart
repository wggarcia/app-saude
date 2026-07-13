import 'package:flutter/material.dart';
import 'package:webview_flutter/webview_flutter.dart';

class TelaVideoReuniao extends StatefulWidget {
  final String url;
  final String titulo;

  const TelaVideoReuniao({
    super.key,
    required this.url,
    required this.titulo,
  });

  @override
  State<TelaVideoReuniao> createState() => _TelaVideoReuniaoState();
}

class _TelaVideoReuniaoState extends State<TelaVideoReuniao> {
  late final WebViewController _controller;
  bool _carregando = true;

  static const _dominioJaas = '8x8.vc';

  bool _ehRedirecionamentoFinal(String url) {
    final uri = Uri.tryParse(url);
    if (uri == null) return false;
    if (!uri.host.contains(_dominioJaas)) return false;
    // Caminho da sala tem 2+ segmentos: /appId/sala — qualquer coisa mais rasa
    // é a página de promoção/home da 8x8
    final partes = uri.pathSegments.where((s) => s.isNotEmpty).toList();
    return partes.length < 2;
  }

  @override
  void initState() {
    super.initState();
    _controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setNavigationDelegate(
        NavigationDelegate(
          onPageStarted: (_) => setState(() => _carregando = true),
          onPageFinished: (_) => setState(() => _carregando = false),
          onNavigationRequest: (req) {
            if (_ehRedirecionamentoFinal(req.url)) {
              // Reunião encerrada — volta para o app sem abrir a página da 8x8
              if (mounted) Navigator.of(context).pop();
              return NavigationDecision.prevent;
            }
            return NavigationDecision.navigate;
          },
        ),
      )
      ..loadRequest(Uri.parse(widget.url));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.black,
        foregroundColor: Colors.white,
        title: Text(widget.titulo, style: const TextStyle(fontSize: 14)),
        leading: IconButton(
          icon: const Icon(Icons.close),
          tooltip: 'Sair da reunião',
          onPressed: () => Navigator.of(context).pop(),
        ),
      ),
      body: Stack(
        children: [
          WebViewWidget(controller: _controller),
          if (_carregando)
            const Center(
              child: CircularProgressIndicator(color: Colors.tealAccent),
            ),
        ],
      ),
    );
  }
}
