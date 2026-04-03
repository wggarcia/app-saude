import 'package:flutter/material.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';
import 'dart:convert';
import 'package:http/http.dart' as http;
import 'dart:async';
import 'package:record/record.dart';
import 'package:flutter/foundation.dart'; // 👈 importante

class TelaMapa extends StatefulWidget {
  @override
  _TelaMapaState createState() => _TelaMapaState();
}

class _TelaMapaState extends State<TelaMapa> {

  Set<Marker> marcadores = {};
  Timer? timer;

  final recorder = AudioRecorder();

  @override
  void initState() {
    super.initState();
    carregarDados();

    timer = Timer.periodic(Duration(seconds: 5), (Timer t) {
      carregarDados();
    });
  }

  @override
  void dispose() {
    timer?.cancel();
    super.dispose();
  }

  // 🔥 MAPA
  Future<void> carregarDados() async {
    final url = Uri.parse("https://app-saude-p9n8.onrender.com/api/mapa-casos");

    try {
      final response = await http.get(url);

      if (response.statusCode == 200) {
        final List dados = jsonDecode(response.body);

        Set<Marker> novos = {};

        for (var item in dados) {

          double lat = double.parse(item['latitude'].toString());
          double lon = double.parse(item['longitude'].toString());

          String grupo = item['grupo'] ?? "";

          BitmapDescriptor cor;

          if (grupo == "Respiratório") {
            cor = BitmapDescriptor.defaultMarkerWithHue(BitmapDescriptor.hueOrange);
          } else if (grupo == "Arbovirose") {
            cor = BitmapDescriptor.defaultMarkerWithHue(BitmapDescriptor.hueYellow);
          } else {
            cor = BitmapDescriptor.defaultMarkerWithHue(BitmapDescriptor.hueGreen);
          }

          novos.add(
            Marker(
              markerId: MarkerId(lat.toString() + lon.toString()),
              position: LatLng(lat, lon),
              icon: cor,
              infoWindow: InfoWindow(
                title: item['cidade'] ?? "Local",
                snippet: grupo,
              ),
            ),
          );
        }

        setState(() {
          marcadores = novos;
        });
      }
    } catch (e) {
      print("Erro: $e");
    }
  }

  // 🎤 GRAVAR ÁUDIO (WEB SAFE)
  Future<void> gravarAudio() async {

    // 👉 WEB (Chrome)
    if (kIsWeb) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text("🎤 Áudio só funciona no celular")),
      );
      return;
    }

    // 👉 MOBILE
    if (await recorder.hasPermission()) {

      await recorder.start(
        const RecordConfig(),
        path: 'tosse.wav',
      );

      await Future.delayed(Duration(seconds: 3));

      final path = await recorder.stop();

      if (path != null) {
        enviarAudio(path);
      }
    }
  }

  // 🚀 ENVIAR ÁUDIO
  Future<void> enviarAudio(String path) async {
    final request = http.MultipartRequest(
      'POST',
      Uri.parse("https://app-saude-p9n8.onrender.com/api/analisar-audio"),
    );

    request.files.add(
      await http.MultipartFile.fromPath('audio', path),
    );

    final response = await request.send();
    final respStr = await response.stream.bytesToString();

    final data = jsonDecode(respStr);

    showDialog(
      context: context,
      builder: (_) => AlertDialog(
        title: Text("Resultado da IA"),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(data['classificacao'] ?? ""),
            SizedBox(height: 10),
            Text("Nível: ${data['nivel'] ?? ""}"),
          ],
        ),
      ),
    );
  }

  // 🗺️ UI (CORRIGIDA PARA WEB)
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text("Mapa de Sintomas"),
        backgroundColor: Colors.red,
      ),

      // 👇 SEM STACK (isso quebrava no Chrome)
      body: Column(
        children: [

          Expanded(
            child: GoogleMap(
              initialCameraPosition: CameraPosition(
                target: LatLng(-22.8832, -43.1034),
                zoom: 12,
              ),
              markers: marcadores,
            ),
          ),

          // 🎤 BOTÃO GARANTIDO VISÍVEL
          Container(
            width: double.infinity,
            padding: EdgeInsets.all(12),
            color: Colors.red,
            child: ElevatedButton.icon(
              onPressed: gravarAudio,
              icon: Icon(Icons.mic),
              label: Text("Gravar Tosse"),
              style: ElevatedButton.styleFrom(
                backgroundColor: Colors.white,
                foregroundColor: Colors.red,
              ),
            ),
          )

        ],
      ),
    );
  }
}