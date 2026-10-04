import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/format.dart';
import '../../core/session.dart';
import '../../core/theme.dart';
import '../../widgets/common.dart';
import '../inventory/doc_screen.dart';
import '../products/product_detail.dart';
import 'scanner_page.dart';

/// Genel okutma: kodu tara, ne olduğunu çözümle ve ilgili ekrana yönlendir.
Future<void> openScanLookup(BuildContext context) async {
  final code = await scanOnce(context, title: 'Ne okutuyorsunuz?');
  if (code == null || !context.mounted) return;
  await Navigator.of(context).push(MaterialPageRoute(builder: (_) => ScanResultScreen(code: code)));
}

class ScanResultScreen extends StatelessWidget {
  const ScanResultScreen({super.key, required this.code});
  final String code;

  @override
  Widget build(BuildContext context) {
    final api = context.read<AppState>().api;
    return Scaffold(
      appBar: AppBar(title: const Text('Okutma sonucu')),
      body: DataView<Map<String, dynamic>>(
        load: () async => Map<String, dynamic>.from(await api.barkod('cozumle', {'code': code})),
        refreshable: false,
        builder: (context, data, _) => _Result(data: data),
      ),
    );
  }
}

class _Result extends StatelessWidget {
  const _Result({required this.data});
  final Map<String, dynamic> data;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    final scheme = Theme.of(context).colorScheme;
    final tip = data['tip'];
    final urun = data['urun'] as Map?;
    final seri = data['seri'] as Map?;
    final lokasyon = data['lokasyon'] as Map?;
    final belge = data['belge'] as Map?;
    final stok = (data['stok'] as List?) ?? [];
    final (icon, label) = switch (tip) {
      'urun' => (Icons.inventory_2_rounded, 'Ürün'),
      'seri' => (Icons.qr_code_2_rounded, 'Seri / Lot'),
      'lokasyon' => (Icons.shelves, 'Lokasyon'),
      'belge' => (Icons.local_shipping_rounded, 'Depo belgesi'),
      'uretim' => (Icons.precision_manufacturing_rounded, 'Üretim emri'),
      _ => (Icons.help_outline_rounded, 'Bilinmeyen'),
    };
    final total = stok.fold<double>(0, (a, s) => a + Fmt.d(s['miktar']));

    return ContentWidth(
      child: ListView(padding: const EdgeInsets.all(Gap.lg), children: [
        AppCard(
          child: Row(children: [
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(color: scheme.primary.withValues(alpha: .1), borderRadius: BorderRadius.circular(16)),
              child: Icon(icon, color: scheme.primary, size: 30),
            ),
            const SizedBox(width: Gap.lg),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                StatusChip(label, tone: Tone.primary),
                const SizedBox(height: 6),
                Text(urun?['ad'] ?? lokasyon?['ad'] ?? belge?['ad'] ?? data['kod'], style: text.titleMedium),
                if (seri != null) Text('Seri: ${seri['ad']}', style: text.bodyMedium),
                Text(data['kod'], style: text.bodySmall),
              ]),
            ),
          ]),
        ),
        if (urun != null) ...[
          const SectionHeader('Stok durumu'),
          AppCard(
            padding: const EdgeInsets.symmetric(horizontal: Gap.lg, vertical: Gap.sm),
            child: Column(children: [
              InfoRow('Toplam eldeki', '${Fmt.qty(total)} ${urun['birim']}', emphasize: true),
              if (stok.isNotEmpty) const Divider(),
              for (final s in stok)
                InfoRow(s['lokasyon'], '${Fmt.qty(s['miktar'])}${(s['seri'] ?? '') != '' ? '  •  ${s['seri']}' : ''}'),
              if (stok.isEmpty)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 8),
                  child: Text('Depolarda stok yok', style: text.bodyMedium?.copyWith(color: scheme.onSurfaceVariant)),
                ),
            ]),
          ),
          const SizedBox(height: Gap.lg),
          FilledButton.tonalIcon(
            onPressed: () => Navigator.push(context, MaterialPageRoute(builder: (_) => ProductDetailScreen(productId: urun['id']))),
            icon: const Icon(Icons.info_outline_rounded),
            label: const Text('Ürün kartını aç'),
          ),
        ],
        if (lokasyon != null) ...[
          const SizedBox(height: Gap.lg),
          FilledButton.icon(
            onPressed: () => Navigator.pushReplacement(
                context, MaterialPageRoute(builder: (_) => DocScreen(islem: 'sayim', id: lokasyon['id'], title: lokasyon['ad']))),
            icon: const Icon(Icons.fact_check_rounded),
            label: const Text('Bu lokasyonda sayım yap'),
          ),
        ],
        if (belge != null && belge['islem'] != null) ...[
          const SizedBox(height: Gap.lg),
          FilledButton.icon(
            onPressed: () => Navigator.pushReplacement(
                context, MaterialPageRoute(builder: (_) => DocScreen(islem: belge['islem'], id: belge['id'], title: belge['ad']))),
            icon: const Icon(Icons.open_in_new_rounded),
            label: const Text('Belgeyi aç ve okutmaya başla'),
          ),
        ],
        const SizedBox(height: Gap.md),
        OutlinedButton.icon(
          onPressed: () async {
            final nav = Navigator.of(context);
            final code = await scanOnce(context, title: 'Ne okutuyorsunuz?');
            if (code != null) nav.pushReplacement(MaterialPageRoute(builder: (_) => ScanResultScreen(code: code)));
          },
          icon: const Icon(Icons.qr_code_scanner_rounded),
          label: const Text('Yeni okutma'),
        ),
      ]),
    );
  }
}
