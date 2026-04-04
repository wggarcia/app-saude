import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'dart:convert';
import 'package:http/http.dart' as http;

class TelaMapa extends StatefulWidget {
  const TelaMapa({super.key});

  @override
  State<TelaMapa> createState() => _TelaMapaState();
}

class _TelaMapaState extends State<TelaMapa> {

  String token = "COLE_AQUI_SEU_TOKEN";

  List<Marker> marcadores = [];

  @override
  void initState() {
    super.initState();
    carregarDados();
  }

  Future<void> carregarDados() async {
  final url = Uri.parse(
    "https://app-saude-p9n8.onrender.com/api/mapa-casos"
  );

  try {
    final response = await http.get(url);

    print("STATUS: ${response.statusCode}");
    print("BODY: ${response.body}");

    if (response.statusCode == 200) {
      final List dados = jsonDecode(response.body);

      List<Marker> novos = [];

      for (var item in dados) {
        double lat = (item['latitude'] ?? 0).toDouble();
        double lon = (item['longitude'] ?? 0).toDouble();

        if (lat == 0 || lon == 0) continue;

        novos.add(
          Marker(
            point: LatLng(lat, lon),
            width: 50,
            height: 50,
            child: Column(
              children: [
                Icon(Icons.location_on, color: Colors.red, size: 30),
                Text(
                  item['grupo'] ?? '',
                  style: TextStyle(fontSize: 10),
                ),
              ],
            ),
          ),
        );
      }

      setState(() {
        marcadores = novos;
      });
    }
  } catch (e) {
    print("Erro mapa: $e");
  }
}

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text("Mapa de Casos"),
        backgroundColor: Colors.blue,
      ),
      body: FlutterMap(
        options: MapOptions(
          initialCenter: LatLng(-22.8832, -43.1034),
          initialZoom: 12,
        ),
        children: [
          TileLayer(
               urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                 userAgentPackageName: 'app_saude',
                ),

          MarkerLayer(
            markers: marcadores,
          ),
        ],
      ),
    );
  }
}