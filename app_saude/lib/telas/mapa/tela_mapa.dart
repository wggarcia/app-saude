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

  List<Marker> marcadores = [];

  bool carregou = false;

@override
void didChangeDependencies() {
  super.didChangeDependencies();

  if (!carregou) {
    carregarDados();
    carregou = true;
  }
}

  Future<void> carregarDados() async {
    final url = Uri.parse(
      "https://app-saude-p9n8.onrender.com/api/mapa-casos"
    );

    final response = await http.get(url);

    if (response.statusCode == 200) {
      final List dados = jsonDecode(response.body);

      List<Marker> novos = [];

      for (var item in dados) {
        double lat = double.parse(item['latitude'].toString());
        double lon = double.parse(item['longitude'].toString());

        novos.add(
          Marker(
            point: LatLng(lat, lon),
            width: 60,
            height: 60,
            child: Column(
              children: [
                Container(
                  padding: EdgeInsets.all(6),
                  decoration: BoxDecoration(
                    color: Colors.red,
                    shape: BoxShape.circle,
                  ),
                  child: Icon(Icons.coronavirus, color: Colors.white),
                ),
                Text("${item['total'] ?? 1}",
                    style: TextStyle(fontSize: 10)),
              ],
            ),
          ),
        );
      }

      setState(() {
        marcadores = novos;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text("Mapa")),
      body: FlutterMap(
        options: MapOptions(
          initialCenter: LatLng(-22.9, -43.1),
          initialZoom: 10,
        ),
        children: [
          TileLayer(
            urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
            userAgentPackageName: 'app_saude',
          ),
          MarkerLayer(markers: marcadores),
        ],
      ),
    );
  }
}