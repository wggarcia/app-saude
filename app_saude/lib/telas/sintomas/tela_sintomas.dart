import 'package:flutter/material.dart';
import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:geolocator/geolocator.dart';
import 'package:record/record.dart';
import 'package:flutter/foundation.dart';
import 'package:path_provider/path_provider.dart';
import 'dart:io';

class TelaSintomas extends StatefulWidget {
  @override
  _TelaSintomasState createState() => _TelaSintomasState();
}

class _TelaSintomasState extends State<TelaSintomas> {

  bool febre = false;
  bool tosse = false;
  bool dorCorpo = false;
  bool cansaco = false;
  bool faltaAr = false;

  bool carregando = false;

  final recorder = AudioRecorder();

  Future<Position?> obterLocalizacao() async {
  bool serviceEnabled = await Geolocator.isLocationServiceEnabled();
  if (!serviceEnabled) return null;

  LocationPermission permission = await Geolocator.checkPermission();

  if (permission == LocationPermission.denied) {
    permission = await Geolocator.requestPermission();
  }

  if (permission == LocationPermission.deniedForever) {
    return null;
  }

  return await Geolocator.getCurrentPosition(
    desiredAccuracy: LocationAccuracy.high,
  );
}

  Future<void> gravarAudio() async {
  try {
    if (kIsWeb) return;

    bool hasPermission = await recorder.hasPermission();

    if (!hasPermission) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text("Permissão de microfone negada")),
      );
      return;
    }

    final dir = await getApplicationDocumentsDirectory();
    final path = '${dir.path}/voz.wav';

  await recorder.start(
  const RecordConfig(),
  path: path,
);

    await Future.delayed(Duration(seconds: 3));

    final result = await recorder.stop();

    if (result != null) {
      enviarAudio(result);
    }

  } catch (e) {
    print("Erro no áudio: $e");

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text("Erro ao gravar áudio")),
    );
  }
}

  Future<void> enviarAudio(String path) async {
    print("CAMINHO: $path");
    print("EXISTE: ${File(path).existsSync()}");

    final request = http.MultipartRequest(
      'POST',
      Uri.parse("https://app-saude-p9n8.onrender.com/api/registrar")
    );

    request.files.add(await http.MultipartFile.fromPath('audio', path));

    final response = await request.send();
    final respStr = await response.stream.bytesToString();

    final data = jsonDecode(respStr);

    showDialog(
      context: context,
      builder: (_) => AlertDialog(
        title: Text("Resultado da IA"),
        content: Text(data['classificacao'] ?? ""),
      ),
    );
  }

  Future<void> enviarDados() async {
    setState(() => carregando = true);

    final pos = await obterLocalizacao();

    if (pos == null) {
  ScaffoldMessenger.of(context).showSnackBar(
    SnackBar(content: Text("Ative o GPS")),
  );
  setState(() => carregando = false);
  return;
}

    await http.post(
      Uri.parse("https://app-saude-p9n8.onrender.com/api/registrar"),
      headers: {"Content-Type": "application/json"},
      body: jsonEncode({
        "febre": febre,
        "tosse": tosse,
        "dor_corpo": dorCorpo,
        "cansaco": cansaco,
        "falta_ar": faltaAr,
        "latitude": pos?.latitude,
        "longitude": pos?.longitude,
      }),
    );

    setState(() => carregando = false);

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text("Dados enviados")),
    );
  }

  Widget item(String texto, bool valor, Function(bool?) onChanged) {
    return CheckboxListTile(
      value: valor,
      onChanged: onChanged,
      title: Text(texto),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Container(
        decoration: BoxDecoration(
          gradient: LinearGradient(
            colors: [Color(0xFFff416c), Color(0xFFff4b2b)],
          ),
        ),
        child: SafeArea(
          child: Column(
            children: [

              Padding(
                padding: EdgeInsets.all(20),
                child: Text(
                  "Saúde Inteligente",
                  style: TextStyle(color: Colors.white, fontSize: 22),
                ),
              ),

              Expanded(
                child: Container(
                  padding: EdgeInsets.all(20),
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.vertical(top: Radius.circular(30)),
                  ),
                  child: Column(
                    children: [

                      item("Febre", febre, (v) => setState(() => febre = v!)),
                      item("Tosse", tosse, (v) => setState(() => tosse = v!)),
                      item("Dor no corpo", dorCorpo, (v) => setState(() => dorCorpo = v!)),
                      item("Cansaço", cansaco, (v) => setState(() => cansaco = v!)),
                      item("Falta de ar", faltaAr, (v) => setState(() => faltaAr = v!)),

                      SizedBox(height: 20),

                      ElevatedButton(
                        onPressed: gravarAudio,
                        child: Text("Falar"),
                      ),

                      SizedBox(height: 20),

                      carregando
                          ? CircularProgressIndicator()
                          : ElevatedButton(
                              onPressed: enviarDados,
                              child: Text("Enviar"),
                            ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}