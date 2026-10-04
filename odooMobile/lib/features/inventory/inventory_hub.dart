import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/session.dart';
import '../../core/theme.dart';
import '../../widgets/common.dart';
import '../scan/scan_lookup.dart';
import 'doc_list.dart';

/// Depo işlemleri: mal kabul, sevkiyat, üretim, stok sayımı (atlas.barkod).
class InventoryHub extends StatelessWidget {
  const InventoryHub({super.key});

  static const ops = [
    ('mal_kabul', 'Mal Kabul', 'Gelen ürünleri okutarak teslim al', Icons.move_to_inbox_rounded, Color(0xFF0E7490)),
    ('sevkiyat', 'Sevkiyat', 'Siparişleri topla ve gönder', Icons.local_shipping_rounded, Color(0xFF7C3AED)),
    ('uretim', 'Üretim', 'Malzeme ve mamul serisi okut', Icons.precision_manufacturing_rounded, Color(0xFFB45309)),
    ('sayim', 'Stok Sayımı', 'Lokasyonu say, farkları işle', Icons.fact_check_rounded, Color(0xFF15803D)),
  ];

  @override
  Widget build(BuildContext context) {
    final api = context.read<AppState>().api;
    final text = Theme.of(context).textTheme;
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(title: const Text('Depo')),
      body: DataView<Map<String, dynamic>>(
        load: () async => Map<String, dynamic>.from(await api.barkod('ana_ekran')),
        builder: (context, data, reload) => ContentWidth(
          child: ListView(padding: const EdgeInsets.all(Gap.lg), children: [
            for (final (key, title, subtitle, icon, color) in ops)
              Padding(
                padding: const EdgeInsets.only(bottom: Gap.md),
                child: AppCard(
                  onTap: () async {
                    await Navigator.push(context, MaterialPageRoute(builder: (_) => DocListScreen(islem: key, title: title)));
                    reload();
                  },
                  child: Row(children: [
                    Container(
                      width: 56,
                      height: 56,
                      decoration: BoxDecoration(color: color.withValues(alpha: .12), borderRadius: BorderRadius.circular(16)),
                      child: Icon(icon, color: color, size: 28),
                    ),
                    const SizedBox(width: Gap.lg),
                    Expanded(
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Text(title, style: text.titleMedium),
                        const SizedBox(height: 2),
                        Text(subtitle, style: text.bodySmall),
                      ]),
                    ),
                    if (data[key] != null)
                      Container(
                        constraints: const BoxConstraints(minWidth: 36),
                        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                        decoration: BoxDecoration(color: scheme.primary.withValues(alpha: .1), borderRadius: BorderRadius.circular(10)),
                        child: Text('${data[key]}', textAlign: TextAlign.center, style: text.titleMedium?.copyWith(color: scheme.primary)),
                      ),
                    const SizedBox(width: Gap.sm),
                    Icon(Icons.chevron_right_rounded, color: scheme.onSurfaceVariant),
                  ]),
                ),
              ),
            const SizedBox(height: Gap.sm),
            OutlinedButton.icon(
              onPressed: () => openScanLookup(context),
              icon: const Icon(Icons.qr_code_scanner_rounded),
              label: const Text('Ürün / seri / lokasyon sorgula'),
            ),
          ]),
        ),
      ),
    );
  }
}
