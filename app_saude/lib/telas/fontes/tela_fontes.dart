import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

// ─── Modelo de fonte ──────────────────────────────────────────────────────────
class _Fonte {
  const _Fonte(this.nome, this.orgao, this.url);
  final String nome;
  final String orgao;
  final String url;
}

// Dados oficiais usados pela plataforma (ver backend: api/fontes_oficiais_brasil.py)
const _fontesDados = [
  _Fonte('OpenDataSUS', 'Ministério da Saúde',
      'https://dadosabertos.saude.gov.br/'),
  _Fonte('DATASUS', 'Ministério da Saúde', 'https://datasus.saude.gov.br/'),
  _Fonte('InfoDengue', 'Fiocruz', 'https://info.dengue.mat.br/'),
  _Fonte(
      'Fiocruz Dengue', 'IOC/Fiocruz', 'https://www.ioc.fiocruz.br/en/dengue/'),
  _Fonte('IBGE', 'Instituto Brasileiro de Geografia e Estatística',
      'https://www.ibge.gov.br/'),
];

// Referências clínicas para os sintomas e orientações exibidos no app
const _fontesClinicas = [
  _Fonte('Arboviroses (dengue, zika, chikungunya)', 'Ministério da Saúde',
      'https://bvsms.saude.gov.br/arboviroses/'),
  _Fonte('Dengue — sinais, sintomas e prevenção', 'Ministério da Saúde',
      'https://bvsms.saude.gov.br/dengue-16/'),
  _Fonte('Influenza — manejo e tratamento', 'Ministério da Saúde',
      'https://bvsms.saude.gov.br/bvs/publicacoes/guia_manejo_tratamento_influenza_2023.pdf'),
];

class FontesResumoCard extends StatelessWidget {
  const FontesResumoCard({super.key});

  @override
  Widget build(BuildContext context) {
    return Card(
      elevation: 0,
      color: const Color(0xFF0A1A28),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Row(
              children: [
                Icon(Icons.menu_book_outlined, color: Color(0xFF78E7D5)),
                SizedBox(width: 10),
                Expanded(
                  child: Text(
                    'Fontes oficiais e citações',
                    style: TextStyle(fontSize: 16, fontWeight: FontWeight.w800),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            const Text(
              'As orientações deste app usam fontes públicas e oficiais. '
              'Abra a lista completa de referências para revisar as páginas '
              'usadas nas recomendações e nos alertas.',
              style: TextStyle(height: 1.45, color: Color(0xFFB9D2DE)),
            ),
            const SizedBox(height: 12),
            FilledButton.tonalIcon(
              onPressed: () {
                Navigator.of(context).push(
                  MaterialPageRoute(builder: (_) => const TelaFontes()),
                );
              },
              icon: const Icon(Icons.open_in_new),
              label: const Text('Abrir fontes'),
            ),
          ],
        ),
      ),
    );
  }
}

class TelaFontes extends StatelessWidget {
  const TelaFontes({super.key});

  Future<void> _abrir(BuildContext context, String url) async {
    final uri = Uri.parse(url);
    final ok = await launchUrl(uri, mode: LaunchMode.externalApplication);
    if (!ok && context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Não foi possível abrir: $url')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Fontes e referências'),
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
        children: [
          const Text(
            'O SoloCRT Saúde combina sinais colaborativos da população com '
            'dados de fontes públicas oficiais. As informações de saúde e os '
            'alertas têm como base as fontes abaixo. Toque para abrir a fonte.',
            style: TextStyle(fontSize: 14, height: 1.4),
          ),
          const SizedBox(height: 24),
          _Secao(
            titulo: 'Dados epidemiológicos e populacionais',
            fontes: _fontesDados,
            onAbrir: (u) => _abrir(context, u),
          ),
          const SizedBox(height: 20),
          _Secao(
            titulo: 'Referências clínicas (sintomas e orientações)',
            fontes: _fontesClinicas,
            onAbrir: (u) => _abrir(context, u),
          ),
          const SizedBox(height: 24),
          Card(
            color: const Color(0xFFFFF4E5),
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: const [
                  Text(
                    'Aviso importante',
                    style: TextStyle(fontWeight: FontWeight.bold, fontSize: 15),
                  ),
                  SizedBox(height: 8),
                  Text(
                    'O SoloCRT Saúde é uma plataforma privada da SoloCRT '
                    'Sistemas Integrados LTDA. Não é um aplicativo oficial do '
                    'governo e não possui vínculo ou autorização de qualquer '
                    'entidade governamental.\n\n'
                    'As informações exibidas têm caráter informativo e '
                    'preventivo e não substituem avaliação, diagnóstico ou '
                    'tratamento médico. Em caso de sintomas ou agravamento, '
                    'procure atendimento profissional imediatamente.',
                    style: TextStyle(fontSize: 13, height: 1.5),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _Secao extends StatelessWidget {
  const _Secao({
    required this.titulo,
    required this.fontes,
    required this.onAbrir,
  });
  final String titulo;
  final List<_Fonte> fontes;
  final void Function(String url) onAbrir;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          titulo,
          style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
        ),
        const SizedBox(height: 8),
        Card(
          clipBehavior: Clip.antiAlias,
          child: Column(
            children: [
              for (var i = 0; i < fontes.length; i++) ...[
                if (i > 0) const Divider(height: 1),
                ListTile(
                  leading: const Icon(Icons.link, color: Color(0xFF1976D2)),
                  title: Text(fontes[i].nome),
                  subtitle: Text(fontes[i].orgao),
                  trailing: const Icon(Icons.open_in_new, size: 18),
                  onTap: () => onAbrir(fontes[i].url),
                ),
              ],
            ],
          ),
        ),
      ],
    );
  }
}
