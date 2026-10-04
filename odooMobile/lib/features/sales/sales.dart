import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/api.dart';
import '../../core/format.dart';
import '../../core/session.dart';
import '../../core/theme.dart';
import '../../widgets/common.dart';
import '../inventory/doc_screen.dart';
import '../partners/partners.dart';
import '../products/product_detail.dart';
import '../scan/scanner_page.dart';

class SaleTile extends StatelessWidget {
  const SaleTile({super.key, required this.order, this.onChanged});
  final Map order;
  final VoidCallback? onChanged;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    return AppCard(
      padding: const EdgeInsets.all(Gap.md),
      onTap: () async {
        await Navigator.push(context, MaterialPageRoute(builder: (_) => SaleDetailScreen(orderId: order['id'])));
        onChanged?.call();
      },
      child: Row(children: [
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              Text(order['ad'], style: text.titleSmall),
              const SizedBox(width: Gap.sm),
              StatusChip(order['durum_ad'] ?? '', tone: States.sale(order['durum'] ?? '')),
            ]),
            const SizedBox(height: 2),
            Text(order['cari'] ?? '', style: text.bodyMedium, maxLines: 1, overflow: TextOverflow.ellipsis),
            Text(Fmt.relative(order['tarih']), style: text.bodySmall),
          ]),
        ),
        Text(Fmt.money(order['tutar'], order['para_simge'] ?? '₺'), style: text.titleSmall),
      ]),
    );
  }
}

class SalesListScreen extends StatefulWidget {
  const SalesListScreen({super.key});

  @override
  State<SalesListScreen> createState() => _SalesListScreenState();
}

class _SalesListScreenState extends State<SalesListScreen> {
  String _search = '', _filter = 'hepsi';
  final List _items = [];
  bool _loading = true, _more = true;
  Object? _error;
  final _scroll = ScrollController();

  @override
  void initState() {
    super.initState();
    _load(reset: true);
    _scroll.addListener(() {
      if (_scroll.position.pixels > _scroll.position.maxScrollExtent - 300 && !_loading && _more) _load();
    });
  }

  @override
  void dispose() {
    _scroll.dispose();
    super.dispose();
  }

  Future<void> _load({bool reset = false}) async {
    setState(() => _loading = true);
    try {
      final r = (await context.read<AppState>().api.mobil('satis_listesi', {
        'arama': _search,
        'filtre': _filter,
        'offset': reset ? 0 : _items.length,
        'limit': 30,
      })) as List;
      if (!mounted) return;
      setState(() {
        if (reset) _items.clear();
        _items.addAll(r);
        _more = r.length == 30;
        _error = null;
      });
    } catch (e) {
      if (mounted) setState(() => _error = e);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _create() async {
    final created = await Navigator.push(context, MaterialPageRoute(builder: (_) => const SaleCreateScreen()));
    if (created != null) _load(reset: true);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Satış')),
      floatingActionButton: FloatingActionButton.extended(
          onPressed: _create, icon: const Icon(Icons.add_rounded), label: const Text('Yeni teklif')),
      body: Column(children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(Gap.lg, Gap.sm, Gap.lg, Gap.sm),
          child: SearchField(hint: 'Sipariş no, cari, referans', onChanged: (v) {
            _search = v;
            _load(reset: true);
          }),
        ),
        SizedBox(
          height: 44,
          child: ListView(scrollDirection: Axis.horizontal, padding: const EdgeInsets.symmetric(horizontal: Gap.lg), children: [
            for (final (k, l) in const [('hepsi', 'Tümü'), ('teklif', 'Teklifler'), ('siparis', 'Siparişler'), ('benim', 'Benim')])
              Padding(
                padding: const EdgeInsets.only(right: Gap.sm),
                child: ChoiceChip(
                  label: Text(l),
                  selected: _filter == k,
                  onSelected: (_) {
                    setState(() => _filter = k);
                    _load(reset: true);
                  },
                ),
              ),
          ]),
        ),
        Expanded(
          child: _items.isEmpty && _loading
              ? const SkeletonList()
              : _items.isEmpty && _error != null
                  ? ErrorState(error: _error!, onRetry: () => _load(reset: true))
                  : RefreshIndicator(
                      onRefresh: () => _load(reset: true),
                      child: _items.isEmpty
                          ? EmptyState(
                              icon: Icons.receipt_long_outlined,
                              title: 'Kayıt yok',
                              message: 'Bu filtrede teklif veya sipariş bulunamadı.',
                              action: FilledButton.tonal(onPressed: _create, child: const Text('Yeni teklif oluştur')),
                            )
                          : ListView.separated(
                              controller: _scroll,
                              physics: const AlwaysScrollableScrollPhysics(),
                              padding: const EdgeInsets.fromLTRB(Gap.lg, Gap.sm, Gap.lg, 96),
                              itemCount: _items.length + (_more ? 1 : 0),
                              separatorBuilder: (_, _) => const SizedBox(height: Gap.sm),
                              itemBuilder: (context, i) => i == _items.length
                                  ? const Padding(padding: EdgeInsets.all(Gap.lg), child: Center(child: CircularProgressIndicator()))
                                  : SaleTile(order: _items[i], onChanged: () => _load(reset: true)),
                            ),
                    ),
        ),
      ]),
    );
  }
}

class SaleDetailScreen extends StatefulWidget {
  const SaleDetailScreen({super.key, required this.orderId});
  final int orderId;

  @override
  State<SaleDetailScreen> createState() => _SaleDetailScreenState();
}

class _SaleDetailScreenState extends State<SaleDetailScreen> {
  final _key = GlobalKey<DataViewState<Map<String, dynamic>>>();

  OdooClient get _api => context.read<AppState>().api;

  Future<void> _confirm() async {
    if (!await confirm(context, title: 'Teklifi onayla', message: 'Teklif satış siparişine dönüşecek.', ok: 'Siparişe çevir')) return;
    if (!mounted) return;
    final r = await runAction(context, () => _api.mobil('satis_onayla', {'order_id': widget.orderId}), success: 'Sipariş onaylandı');
    if (r != null) _key.currentState?.reload();
  }

  Future<void> _cancel() async {
    if (!await confirm(context, title: 'Siparişi iptal et', ok: 'İptal et', destructive: true)) return;
    if (!mounted) return;
    final r = await runAction(context, () => _api.mobil('satis_iptal', {'order_id': widget.orderId}), success: 'İptal edildi');
    if (r != null) _key.currentState?.reload();
  }

  Future<void> _note() async {
    final note = await promptText(context, title: 'Not ekle', hint: 'Siparişe iç not', required: true);
    if (note == null || !mounted) return;
    await runAction(context, () => _api.mobil('not_ekle', {'model': 'sale.order', 'res_id': widget.orderId, 'metin': note}),
        success: 'Not eklendi');
  }

  @override
  Widget build(BuildContext context) {
    return DataView<Map<String, dynamic>>(
      key: _key,
      refreshable: false,
      load: () async => Map<String, dynamic>.from(await _api.mobil('satis_detay', {'order_id': widget.orderId})),
      skeleton: Scaffold(appBar: AppBar(), body: const SkeletonList(header: true)),
      builder: (context, o, reload) {
        final text = Theme.of(context).textTheme;
        final scheme = Theme.of(context).colorScheme;
        final sym = o['para_simge'] ?? '₺';
        final lines = (o['satirlar'] as List).cast<Map>();
        final teslimatlar = (o['teslimatlar'] as List).cast<Map>();
        return Scaffold(
          appBar: AppBar(title: Text(o['ad']), actions: [
            PopupMenuButton<String>(
              tooltip: 'Diğer işlemler',
              onSelected: (v) => v == 'not' ? _note() : _cancel(),
              itemBuilder: (_) => [
                const PopupMenuItem(value: 'not', child: Text('Not ekle')),
                if (o['durum'] != 'cancel') const PopupMenuItem(value: 'iptal', child: Text('İptal et')),
              ],
            ),
          ]),
          bottomNavigationBar: o['onaylanabilir'] == true
              ? BottomActionBar(children: [
                  FilledButton.icon(onPressed: _confirm, icon: const Icon(Icons.check_rounded), label: const Text('Siparişe çevir')),
                ])
              : null,
          body: RefreshIndicator(
            onRefresh: reload,
            child: ContentWidth(
              child: ListView(padding: const EdgeInsets.all(Gap.lg), children: [
                AppCard(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Row(children: [
                      StatusChip(o['durum_ad'], tone: States.sale(o['durum'])),
                      const Spacer(),
                      Text(Fmt.dateTime(o['tarih']), style: text.bodySmall),
                    ]),
                    const SizedBox(height: Gap.md),
                    InkWell(
                      onTap: () => Navigator.push(context, MaterialPageRoute(builder: (_) => PartnerDetailScreen(partnerId: o['cari_id']))),
                      child: Row(children: [
                        Avatar(name: o['cari'], size: 40),
                        const SizedBox(width: Gap.md),
                        Expanded(child: Text(o['cari'], style: text.titleMedium)),
                        Icon(Icons.chevron_right_rounded, color: scheme.onSurfaceVariant),
                      ]),
                    ),
                    const SizedBox(height: Gap.lg),
                    Text('Toplam', style: text.bodySmall),
                    Text(Fmt.money(o['tutar'], sym), style: text.headlineMedium?.copyWith(color: scheme.primary)),
                  ]),
                ),
                const SectionHeader('Ürünler'),
                AppCard(
                  padding: EdgeInsets.zero,
                  child: Column(children: [
                    for (var i = 0; i < lines.length; i++) ...[
                      if (i > 0) const Divider(indent: Gap.lg, endIndent: Gap.lg),
                      Padding(
                        padding: const EdgeInsets.all(Gap.md),
                        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                          Avatar(name: lines[i]['ad'], image: lines[i]['gorsel'] == false ? null : lines[i]['gorsel'], size: 40, square: true),
                          const SizedBox(width: Gap.md),
                          Expanded(
                            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                              Text(lines[i]['ad'], style: text.titleSmall),
                              Text(
                                '${Fmt.qty(lines[i]['miktar'])} ${lines[i]['birim']} × ${Fmt.money(lines[i]['fiyat'], sym)}'
                                '${Fmt.d(lines[i]['indirim']) > 0 ? '  (−%${Fmt.qty(lines[i]['indirim'])})' : ''}',
                                style: text.bodySmall,
                              ),
                              if (o['durum'] == 'sale')
                                Text('Teslim: ${Fmt.qty(lines[i]['teslim'])}  •  Fatura: ${Fmt.qty(lines[i]['faturalanan'])}',
                                    style: text.bodySmall),
                            ]),
                          ),
                          Text(Fmt.money(lines[i]['tutar'], sym), style: text.titleSmall),
                        ]),
                      ),
                    ],
                  ]),
                ),
                const SizedBox(height: Gap.md),
                AppCard(
                  padding: const EdgeInsets.symmetric(horizontal: Gap.lg, vertical: Gap.sm),
                  child: Column(children: [
                    InfoRow('Ara toplam', Fmt.money(o['ara_toplam'], sym)),
                    InfoRow('Vergiler', Fmt.money(o['vergi'], sym)),
                    const Divider(),
                    InfoRow('Genel toplam', Fmt.money(o['tutar'], sym), emphasize: true),
                  ]),
                ),
                const SectionHeader('Bilgiler'),
                AppCard(
                  padding: const EdgeInsets.symmetric(horizontal: Gap.lg, vertical: Gap.sm),
                  child: Column(children: [
                    InfoRow('Satış temsilcisi', o['satici'] ?? ''),
                    InfoRow('Ödeme koşulu', o['odeme_kosulu'] ?? ''),
                    InfoRow('Geçerlilik', Fmt.date(o['gecerlilik'])),
                    InfoRow('Müşteri referansı', o['referans'] ?? ''),
                  ]),
                ),
                if (teslimatlar.isNotEmpty) ...[
                  const SectionHeader('Teslimatlar'),
                  for (final t in teslimatlar)
                    Padding(
                      padding: const EdgeInsets.only(bottom: Gap.sm),
                      child: AppCard(
                        padding: const EdgeInsets.all(Gap.md),
                        onTap: ['done', 'cancel'].contains(t['durum'])
                            ? null
                            : () => Navigator.push(context,
                                MaterialPageRoute(builder: (_) => DocScreen(islem: 'sevkiyat', id: t['id'], title: t['ad']))),
                        child: Row(children: [
                          const Icon(Icons.local_shipping_outlined),
                          const SizedBox(width: Gap.md),
                          Expanded(child: Text(t['ad'], style: text.titleSmall)),
                          Builder(builder: (_) {
                            final (l, tone) = States.picking(t['durum']);
                            return StatusChip(l, tone: tone);
                          }),
                        ]),
                      ),
                    ),
                ],
                if ((o['not'] ?? '') != '') ...[
                  const SectionHeader('Notlar'),
                  AppCard(child: Text(o['not'])),
                ],
                const SizedBox(height: Gap.xl),
              ]),
            ),
          ),
        );
      },
    );
  }
}

/// Yeni satış teklifi: cari seç, ürün ekle (arama veya barkod), miktar/fiyat düzenle, kaydet veya onayla.
class SaleCreateScreen extends StatefulWidget {
  const SaleCreateScreen({super.key, this.partner});
  final Map? partner;

  @override
  State<SaleCreateScreen> createState() => _SaleCreateScreenState();
}

class _Line {
  _Line(this.product) : price = Fmt.d(product['fiyat']);
  final Map product;
  double qty = 1;
  double price;
  double discount = 0;
  double get total => qty * price * (1 - discount / 100);
}

class _SaleCreateScreenState extends State<SaleCreateScreen> {
  Map? _partner;
  final List<_Line> _lines = [];
  final _note = TextEditingController();
  bool _busy = false;

  OdooClient get _api => context.read<AppState>().api;

  @override
  void initState() {
    super.initState();
    _partner = widget.partner;
  }

  double get _total => _lines.fold(0, (a, l) => a + l.total);

  void _addProduct(Map p) {
    setState(() {
      final existing = _lines.where((l) => l.product['id'] == p['id']).firstOrNull;
      if (existing != null) {
        existing.qty += 1;
      } else {
        _lines.add(_Line(p));
      }
    });
  }

  Future<void> _pickPartner() async {
    final p = await Navigator.push<Map>(context, MaterialPageRoute(builder: (_) => const PartnerListScreen(picker: true)));
    if (p != null) setState(() => _partner = p);
  }

  Future<void> _pickProduct() async {
    final p = await showModalBottomSheet<Map>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      builder: (_) => const _ProductPicker(),
    );
    if (p != null) _addProduct(p);
  }

  Future<void> _scanProducts() async {
    await Navigator.push(context, MaterialPageRoute(
      fullscreenDialog: true,
      builder: (_) => ScannerPage(
        title: 'Ürün okut',
        subtitle: 'Okutulan her ürün teklife eklenir',
        onCode: (code) async {
          try {
            final r = (await _api.mobil('urun_ara', {'arama': code, 'limit': 1})) as List;
            if (r.isEmpty) return ScanFeedback('"$code" ile satılabilir ürün bulunamadı', ScanTone.error);
            _addProduct(r.first);
            final qty = _lines.firstWhere((l) => l.product['id'] == r.first['id']).qty;
            return ScanFeedback('${r.first['ad']} • ${Fmt.qty(qty)} adet', ScanTone.ok);
          } catch (e) {
            return ScanFeedback(errorText(e), ScanTone.error);
          }
        },
      ),
    ));
  }

  Future<void> _editLine(_Line line) async {
    final qty = TextEditingController(text: Fmt.qty(line.qty).replaceAll('.', ''));
    final price = TextEditingController(text: line.price.toStringAsFixed(2).replaceAll('.', ','));
    final disc = TextEditingController(text: line.discount == 0 ? '' : Fmt.qty(line.discount));
    final result = await showModalBottomSheet<String>(
      context: context,
      isScrollControlled: true,
      builder: (ctx) => Padding(
        padding: EdgeInsets.fromLTRB(20, 0, 20, MediaQuery.of(ctx).viewInsets.bottom + 20),
        child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Text(line.product['ad'], style: Theme.of(ctx).textTheme.titleMedium),
          const SizedBox(height: 16),
          QtyStepper(controller: qty, unit: line.product['birim'] ?? ''),
          const SizedBox(height: 12),
          Row(children: [
            Expanded(
              child: TextField(
                controller: price,
                keyboardType: const TextInputType.numberWithOptions(decimal: true),
                decoration: InputDecoration(labelText: 'Birim fiyat', suffixText: context.read<AppState>().currencySymbol),
              ),
            ),
            const SizedBox(width: 12),
            SizedBox(
              width: 120,
              child: TextField(
                controller: disc,
                keyboardType: const TextInputType.numberWithOptions(decimal: true),
                decoration: const InputDecoration(labelText: 'İndirim', suffixText: '%'),
              ),
            ),
          ]),
          const SizedBox(height: 16),
          Row(children: [
            Expanded(
              child: OutlinedButton.icon(
                onPressed: () => Navigator.pop(ctx, 'sil'),
                icon: const Icon(Icons.delete_outline_rounded),
                label: const Text('Kaldır'),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(child: FilledButton(onPressed: () => Navigator.pop(ctx, 'ok'), child: const Text('Uygula'))),
          ]),
        ]),
      ),
    );
    double p(String s) => double.tryParse(s.replaceAll('.', '').replaceAll(',', '.')) ?? 0;
    setState(() {
      if (result == 'sil') {
        _lines.remove(line);
      } else if (result == 'ok') {
        line.qty = p(qty.text) <= 0 ? 1 : p(qty.text);
        line.price = double.tryParse(price.text.replaceAll(',', '.')) ?? line.price;
        line.discount = p(disc.text).clamp(0, 100);
      }
    });
  }

  Future<void> _save(bool onayla) async {
    if (_partner == null) {
      showError(context, OdooException('Önce cari seçin.'));
      return;
    }
    if (_lines.isEmpty) {
      showError(context, OdooException('En az bir ürün ekleyin.'));
      return;
    }
    setState(() => _busy = true);
    final r = await runAction(
      context,
      () async => Map<String, dynamic>.from(await _api.mobil('satis_olustur', {
        'partner_id': _partner!['id'],
        'satirlar': [
          for (final l in _lines)
            {
              'urun_id': l.product['id'],
              'miktar': l.qty,
              if (l.price != Fmt.d(l.product['fiyat'])) 'fiyat': l.price,
              if (l.discount > 0) 'indirim': l.discount,
            }
        ],
        'not_metni': _note.text.trim(),
        'onayla': onayla,
      })),
      success: onayla ? 'Sipariş oluşturuldu' : 'Teklif kaydedildi',
    );
    if (!mounted) return;
    setState(() => _busy = false);
    if (r != null) {
      Navigator.pushReplacement(context, MaterialPageRoute(builder: (_) => SaleDetailScreen(orderId: r['id'])));
    }
  }

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    final scheme = Theme.of(context).colorScheme;
    final sym = context.read<AppState>().currencySymbol;
    return Scaffold(
      appBar: AppBar(title: const Text('Yeni teklif')),
      bottomNavigationBar: Column(mainAxisSize: MainAxisSize.min, children: [
        Container(
          color: scheme.surface,
          padding: const EdgeInsets.fromLTRB(Gap.lg, Gap.md, Gap.lg, 0),
          child: Row(children: [
            Text('Tahmini toplam (vergi hariç)', style: text.bodyMedium),
            const Spacer(),
            Text(Fmt.money(_total, sym), style: text.titleLarge?.copyWith(color: scheme.primary)),
          ]),
        ),
        BottomActionBar(children: [
          OutlinedButton(onPressed: _busy ? null : () => _save(false), child: const Text('Teklif kaydet')),
          FilledButton(onPressed: _busy ? null : () => _save(true), child: const Text('Sipariş oluştur')),
        ]),
      ]),
      body: ContentWidth(
        child: ListView(padding: const EdgeInsets.all(Gap.lg), children: [
          Text('Müşteri', style: text.labelLarge),
          const SizedBox(height: Gap.sm),
          AppCard(
            onTap: _pickPartner,
            padding: const EdgeInsets.all(Gap.md),
            child: _partner == null
                ? Row(children: [
                    Icon(Icons.person_search_rounded, color: scheme.primary),
                    const SizedBox(width: Gap.md),
                    Expanded(child: Text('Cari seçin', style: text.titleSmall?.copyWith(color: scheme.primary))),
                    const Icon(Icons.chevron_right_rounded),
                  ])
                : Row(children: [
                    Avatar(name: _partner!['ad'], image: _partner!['gorsel'], size: 40),
                    const SizedBox(width: Gap.md),
                    Expanded(child: Text(_partner!['ad'], style: text.titleSmall)),
                    TextButton(onPressed: _pickPartner, child: const Text('Değiştir')),
                  ]),
          ),
          const SizedBox(height: Gap.xl),
          Row(children: [
            Expanded(child: Text('Ürünler (${_lines.length})', style: text.labelLarge)),
            IconButton.filledTonal(tooltip: 'Barkodla ekle', onPressed: _scanProducts, icon: const Icon(Icons.qr_code_scanner_rounded)),
            const SizedBox(width: Gap.sm),
            FilledButton.tonalIcon(onPressed: _pickProduct, icon: const Icon(Icons.add_rounded), label: const Text('Ürün ekle')),
          ]),
          const SizedBox(height: Gap.sm),
          if (_lines.isEmpty)
            Container(
              padding: const EdgeInsets.all(Gap.xl),
              decoration: BoxDecoration(
                border: Border.all(color: scheme.outlineVariant),
                borderRadius: BorderRadius.circular(Gap.radius),
              ),
              child: Column(children: [
                Icon(Icons.shopping_basket_outlined, size: 36, color: scheme.onSurfaceVariant),
                const SizedBox(height: Gap.sm),
                Text('Ürün ekleyin veya barkod okutun', style: text.bodyMedium?.copyWith(color: scheme.onSurfaceVariant)),
              ]),
            ),
          for (final l in _lines)
            Padding(
              padding: const EdgeInsets.only(bottom: Gap.sm),
              child: Dismissible(
                key: ObjectKey(l),
                direction: DismissDirection.endToStart,
                background: Container(
                  alignment: Alignment.centerRight,
                  padding: const EdgeInsets.only(right: Gap.xl),
                  decoration: BoxDecoration(color: AtlasColors.of(context).danger, borderRadius: BorderRadius.circular(Gap.radius)),
                  child: const Icon(Icons.delete_rounded, color: Colors.white),
                ),
                onDismissed: (_) => setState(() => _lines.remove(l)),
                child: AppCard(
                  padding: const EdgeInsets.all(Gap.md),
                  onTap: () => _editLine(l),
                  child: Row(children: [
                    Expanded(
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Text(l.product['ad'], style: text.titleSmall, maxLines: 2, overflow: TextOverflow.ellipsis),
                        Text(
                          '${Fmt.qty(l.qty)} ${l.product['birim']} × ${Fmt.money(l.price, sym)}${l.discount > 0 ? '  (−%${Fmt.qty(l.discount)})' : ''}',
                          style: text.bodySmall,
                        ),
                      ]),
                    ),
                    Text(Fmt.money(l.total, sym), style: text.titleSmall),
                  ]),
                ),
              ),
            ),
          const SizedBox(height: Gap.lg),
          TextField(
            controller: _note,
            minLines: 2,
            maxLines: 5,
            decoration: const InputDecoration(labelText: 'Şartlar ve notlar'),
          ),
        ]),
      ),
    );
  }
}

class _ProductPicker extends StatefulWidget {
  const _ProductPicker();

  @override
  State<_ProductPicker> createState() => _ProductPickerState();
}

class _ProductPickerState extends State<_ProductPicker> {
  String _search = '';
  final _key = GlobalKey<DataViewState<List>>();

  @override
  Widget build(BuildContext context) {
    final api = context.read<AppState>().api;
    return SizedBox(
      height: MediaQuery.of(context).size.height * .85,
      child: Column(children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(Gap.lg, 0, Gap.lg, Gap.sm),
          child: SearchField(hint: 'Ürün ara', onChanged: (v) {
            setState(() => _search = v);
            _key.currentState?.reload();
          }),
        ),
        Expanded(
          child: DataView<List>(
            key: _key,
            refreshable: false,
            load: () async => (await api.mobil('urun_ara', {'arama': _search, 'limit': 50})) as List,
            builder: (context, items, _) => items.isEmpty
                ? const EmptyState(icon: Icons.search_off_rounded, title: 'Ürün bulunamadı')
                : ListView.separated(
                    padding: const EdgeInsets.fromLTRB(Gap.lg, 0, Gap.lg, Gap.xl),
                    itemCount: items.length,
                    separatorBuilder: (_, _) => const SizedBox(height: Gap.sm),
                    itemBuilder: (context, i) => ProductTile(
                      product: items[i],
                      onTap: () => Navigator.pop(context, items[i]),
                      trailing: Icon(Icons.add_circle_rounded, color: Theme.of(context).colorScheme.primary),
                    ),
                  ),
          ),
        ),
      ]),
    );
  }
}
