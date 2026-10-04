import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/format.dart';
import '../../core/session.dart';
import '../../core/theme.dart';
import '../../widgets/common.dart';
import '../scan/scanner_page.dart';

class ProductListScreen extends StatefulWidget {
  const ProductListScreen({super.key});

  @override
  State<ProductListScreen> createState() => _ProductListScreenState();
}

class _ProductListScreenState extends State<ProductListScreen> {
  String _search = '';
  final _key = GlobalKey<DataViewState<List>>();

  void _setSearch(String v) {
    setState(() => _search = v);
    _key.currentState?.reload();
  }

  @override
  Widget build(BuildContext context) {
    final api = context.read<AppState>().api;
    return Scaffold(
      appBar: AppBar(title: const Text('Ürünler')),
      body: Column(children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(Gap.lg, Gap.sm, Gap.lg, Gap.sm),
          child: SearchField(
            hint: 'Ürün adı, kod veya barkod',
            onChanged: _setSearch,
            trailing: IconButton(
              tooltip: 'Barkod okut',
              icon: const Icon(Icons.qr_code_scanner_rounded),
              onPressed: () async {
                final code = await scanOnce(context, title: 'Ürün barkodu okut');
                if (code != null) _setSearch(code);
              },
            ),
          ),
        ),
        Expanded(
          child: DataView<List>(
            key: _key,
            load: () async => (await api.mobil('urun_ara', {'arama': _search, 'satilabilir': false, 'limit': 60})) as List,
            builder: (context, items, _) => items.isEmpty
                ? const EmptyState(icon: Icons.inventory_2_outlined, title: 'Ürün bulunamadı')
                : ListView.separated(
                    padding: const EdgeInsets.fromLTRB(Gap.lg, Gap.sm, Gap.lg, Gap.xxl),
                    itemCount: items.length,
                    separatorBuilder: (_, _) => const SizedBox(height: Gap.sm),
                    itemBuilder: (context, i) => ProductTile(
                      product: items[i],
                      onTap: () => Navigator.push(context, MaterialPageRoute(builder: (_) => ProductDetailScreen(productId: items[i]['id']))),
                    ),
                  ),
          ),
        ),
      ]),
    );
  }
}

class ProductTile extends StatelessWidget {
  const ProductTile({super.key, required this.product, this.onTap, this.trailing});
  final Map product;
  final VoidCallback? onTap;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    final c = AtlasColors.of(context);
    final symbol = context.read<AppState>().currencySymbol;
    final stok = product['stok'];
    return AppCard(
      onTap: onTap,
      padding: const EdgeInsets.all(Gap.md),
      child: Row(children: [
        Avatar(name: product['ad'] ?? '?', image: product['gorsel_var'] == true ? product['gorsel'] : null, size: 52, square: true),
        const SizedBox(width: Gap.md),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(product['ad'] ?? '', style: text.titleSmall, maxLines: 2, overflow: TextOverflow.ellipsis),
            const SizedBox(height: 2),
            Text(Fmt.money(product['fiyat'], symbol), style: text.bodyMedium?.copyWith(fontWeight: FontWeight.w600)),
            if (stok != null)
              Text('Stok: ${Fmt.qty(stok)} ${product['birim']}',
                  style: text.bodySmall?.copyWith(color: Fmt.d(stok) > 0 ? c.success : c.danger)),
          ]),
        ),
        ?trailing,
      ]),
    );
  }
}

class ProductDetailScreen extends StatelessWidget {
  const ProductDetailScreen({super.key, required this.productId});
  final int productId;

  @override
  Widget build(BuildContext context) {
    final api = context.read<AppState>().api;
    final symbol = context.read<AppState>().currencySymbol;
    return Scaffold(
      appBar: AppBar(title: const Text('Ürün')),
      body: DataView<Map<String, dynamic>>(
        load: () async => Map<String, dynamic>.from(await api.mobil('urun_detay', {'product_id': productId})),
        builder: (context, p, _) {
          final text = Theme.of(context).textTheme;
          final scheme = Theme.of(context).colorScheme;
          final stoklar = (p['stoklar'] as List?) ?? [];
          return ContentWidth(
            child: ListView(padding: const EdgeInsets.all(Gap.lg), children: [
              if (p['gorsel_var'] == true)
                ClipRRect(
                  borderRadius: BorderRadius.circular(Gap.radius),
                  child: AspectRatio(
                    aspectRatio: 1.6,
                    child: Container(color: Colors.white, child: NetImage(p['gorsel_buyuk'], fit: BoxFit.contain)),
                  ),
                ),
              const SizedBox(height: Gap.lg),
              Text(p['ad'], style: text.headlineSmall),
              const SizedBox(height: 4),
              Text(p['kategori'] ?? '', style: text.bodyMedium?.copyWith(color: scheme.onSurfaceVariant)),
              const SizedBox(height: Gap.lg),
              Row(children: [
                Expanded(child: _Stat(label: 'Satış fiyatı', value: Fmt.money(p['fiyat'], symbol))),
                const SizedBox(width: Gap.md),
                if (p['stok'] != null) Expanded(child: _Stat(label: 'Eldeki stok', value: '${Fmt.qty(p['stok'])} ${p['birim']}')),
              ]),
              if (p['tahmini'] != null) ...[
                const SizedBox(height: Gap.md),
                Row(children: [
                  Expanded(child: _Stat(label: 'Tahmini stok', value: '${Fmt.qty(p['tahmini'])} ${p['birim']}')),
                  const SizedBox(width: Gap.md),
                  if (p['maliyet'] != null && p['maliyet'] != false) Expanded(child: _Stat(label: 'Maliyet', value: Fmt.money(p['maliyet'], symbol))),
                ]),
              ],
              const SectionHeader('Bilgiler'),
              AppCard(
                padding: const EdgeInsets.symmetric(horizontal: Gap.lg, vertical: Gap.sm),
                child: Column(children: [
                  InfoRow('Stok kodu', p['kod'] ?? ''),
                  InfoRow('Barkod', p['barkod'] ?? ''),
                  InfoRow('Birim', p['birim'] ?? ''),
                ]),
              ),
              if (stoklar.isNotEmpty) ...[
                const SectionHeader('Lokasyonlara göre stok'),
                AppCard(
                  padding: const EdgeInsets.symmetric(horizontal: Gap.lg, vertical: Gap.sm),
                  child: Column(children: [
                    for (final s in stoklar)
                      InfoRow(
                        '${s['lokasyon']}${(s['seri'] ?? '') != '' ? '\n${s['seri']}' : ''}',
                        '${Fmt.qty(s['miktar'])}${Fmt.d(s['rezerve']) > 0 ? '  (${Fmt.qty(s['rezerve'])} rezerve)' : ''}',
                      ),
                  ]),
                ),
              ],
              if ((p['aciklama'] ?? '') != '') ...[
                const SectionHeader('Satış açıklaması'),
                AppCard(child: Text(p['aciklama'])),
              ],
            ]),
          );
        },
      ),
    );
  }
}

class _Stat extends StatelessWidget {
  const _Stat({required this.label, required this.value});
  final String label, value;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    return AppCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(label, style: text.bodySmall),
        const SizedBox(height: 4),
        Text(value, style: text.titleMedium),
      ]),
    );
  }
}
