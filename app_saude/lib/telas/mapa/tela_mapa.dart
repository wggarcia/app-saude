import 'package:flutter/material.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';
import 'dart:convert';
import 'package:http/http.dart' as http;

class TelaMapa extends StatefulWidget {
  const TelaMapa({super.key});

  @override
  State<TelaMapa> createState() => _TelaMapaState();
}

class _TelaMapaState extends State<TelaMapa> {

  Set<Marker> marcadores = {};

  @override
  void initState() {
    super.initState();
    carregarDados();
  }

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

          novos.add(
            Marker(
              markerId: MarkerId(lat.toString() + lon.toString()),
              position: LatLng(lat, lon),
              infoWindow: InfoWindow(
                title: item['cidade'] ?? "Local",
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
      body: GoogleMap(
        initialCameraPosition: const CameraPosition(
          target: LatLng(-22.8832, -43.1034),
          zoom: 12,
        ),
        markers: marcadores,
      ),
    );
  }
}