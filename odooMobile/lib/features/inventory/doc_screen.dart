import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../../core/api.dart';
import '../../core/format.dart';
import '../../core/session.dart';
import '../../core/theme.dart';
import '../../widgets/common.dart';
import '../scan/scanner_page.dart';

/// Okutmalı depo belgesi: mal kabul, sevkiyat, üretim veya lokasyon sayımı.
class DocScreen extends StatefulWidget {
  const DocScreen({super.key, required this.islem, required this.id, required this.title});
  final String islem;
  final int id;
  final String title;

  @override
  State<DocScreen> createState() => _DocScreenState();
}

class _DocScreenState extends State<DocScreen> {
  Map<String, dynamic>? _doc;
  Object? _error;
  bool _busy = false;

  OdooClient get _api => context.read<AppState>().api;
  bool get _sayim => widget.islem == 'sayim';
  bool get _uretim => widget.islem == 'uretim';

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final d = Map<String, dynamic>.from(await _api.barkod('belge_ac', {'islem': widget.islem, 'res_id': widget.id}));
      if (mounted) {
        setState(() {
          _doc = d;
          _error = null;
        });
      }
    } catch (e) {
      if (mounted) setState(() => _error = e);
    }
  }

  Future<ScanFeedback> _scan(String code, [double qty = 1]) async {
    try {
      final r = Map<String, dynamic>.from(
          await _api.barkod('okut', {'islem': widget.islem, 'res_id': widget.id, 'code': code, 'qty': qty}));
      if (mounted) setState(() => _doc = Map<String, dynamic>.from(r['belge']));
      return ScanFeedback(r['mesaj'] ?? 'Okutuldu', r['sonuc'] == 'uyari' ? ScanTone.warning : ScanTone.ok);
    } catch (e) {
      return ScanFeedback(errorText(e), ScanTone.error);
    }
  }

  Future<void> _openScanner() async {
    await Navigator.of(context).push(MaterialPageRoute(
      fullscreenDialog: true,
      builder: (_) => ScannerPage(title: widget.title, subtitle: _hint, onCode: _scan),
    ));
  }

  String get _hint => switch (widget.islem) {
        'mal_kabul' => 'Gelen ürünlerin barkod / seri QR kodunu okutun',
        'sevkiyat' => 'Toplanan ürünlerin barkod / seri QR kodunu okutun',
        'uretim' => 'Malzemeleri ve mamul serisini okutun',
        _ => 'Lokasyondaki ürünleri okutun',
      };

  String _codeFor(Map urun) => (urun['barkod'] ?? '') != '' ? urun['barkod'] : ((urun['kod'] ?? '') != '' ? urun['kod'] : 'P${urun['id']}');

  Future<void> _manualQty(Map line) async {
    final urun = line['urun'] as Map;
    if (urun['takip'] == 'serial' || urun['takip'] == 'lot') {
      showError(context, OdooException('${urun['ad']} seri/lot takipli; seri QR kodunu okutun.'));
      return;
    }
    final controller = TextEditingController(text: '1');
    final qty = await showModalBottomSheet<double>(
      context: context,
      isScrollControlled: true,
      builder: (ctx) => Padding(
        padding: EdgeInsets.fromLTRB(20, 0, 20, MediaQuery.of(ctx).viewInsets.bottom + 20),
        child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Text(urun['ad'], style: Theme.of(ctx).textTheme.titleMedium),
          const SizedBox(height: 4),
          Text(_sayim ? 'Sayılan miktara eklenecek adet' : 'Okutulmuş sayılacak miktar', style: Theme.of(ctx).textTheme.bodySmall),
          const SizedBox(height: 16),
          QtyStepper(controller: controller, unit: line['birim'] ?? urun['birim'] ?? ''),
          const SizedBox(height: 16),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, double.tryParse(controller.text.replaceAll(',', '.'))),
            child: const Text('Ekle'),
          ),
        ]),
      ),
    );
    if (qty == null || qty <= 0 || !mounted) return;
    final fb = await _scan(_codeFor(urun), qty);
    if (!mounted) return;
    fb.tone == ScanTone.error ? showError(context, OdooException(fb.message)) : showSuccess(context, fb.message);
  }

  Future<void> _generateSerials({int? moveId}) async {
    final ok = await confirm(context,
        title: 'Seri numarası üret',
        message: _uretim ? 'Mamul için seri/lot numarası üretilecek.' : 'Kalan miktar kadar yeni seri numarası üretilip okutulmuş sayılacak.',
        ok: 'Üret');
    if (!ok || !mounted) return;
    final r = await runAction(context, () async => Map<String, dynamic>.from(await _api.barkod('seri_uret', {
          'islem': widget.islem,
          'res_id': widget.id,
          'move_id': moveId ?? 0,
        })));
    if (r != null && mounted) {
      setState(() => _doc = Map<String, dynamic>.from(r['belge']));
      showSuccess(context, r['mesaj']);
    }
  }

  Future<void> _validate() async {
    final lines = (_doc!['satirlar'] as List);
    bool kalanIcin = true, sifirla = false;
    if (_sayim) {
      final choice = await showModalBottomSheet<bool>(
        context: context,
        builder: (ctx) => SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(20, 0, 20, 20),
            child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
              Text('Sayımı stoğa işle', style: Theme.of(ctx).textTheme.titleLarge),
              const SizedBox(height: 8),
              Text('Okutulmayan ürünler için ne yapılsın?', style: Theme.of(ctx).textTheme.bodyMedium),
              const SizedBox(height: 16),
              FilledButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Yalnızca sayılanları işle')),
              const SizedBox(height: 8),
              OutlinedButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Okutulmayanları sıfırla')),
            ]),
          ),
        ),
      );
      if (choice == null) return;
      sifirla = choice;
    } else {
      final eksik = lines.any((l) => l['tamam'] != true);
      if (eksik && !_uretim) {
        final choice = await showModalBottomSheet<bool>(
          context: context,
          builder: (ctx) => SafeArea(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(20, 0, 20, 20),
              child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                Text('Eksik okutma var', style: Theme.of(ctx).textTheme.titleLarge),
                const SizedBox(height: 8),
                Text('Bazı ürünler istenen miktara ulaşmadı. Kalanlar için ne yapılsın?', style: Theme.of(ctx).textTheme.bodyMedium),
                const SizedBox(height: 16),
                FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Kalanlar için yeni belge oluştur')),
                const SizedBox(height: 8),
                OutlinedButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Kalanları iptal et')),
              ]),
            ),
          ),
        );
        if (choice == null) return;
        kalanIcin = choice;
      } else if (!await confirm(context, title: _uretim ? 'Üretimi tamamla' : 'Belgeyi doğrula', ok: 'Tamamla')) {
        return;
      }
    }
    if (!mounted) return;
    setState(() => _busy = true);
    final r = await runAction(context, () async => Map<String, dynamic>.from(await _api.barkod('dogrula', {
          'islem': widget.islem,
          'res_id': widget.id,
          'kalan_icin_belge': kalanIcin,
          'sifirla': sifirla,
        })));
    if (!mounted) return;
    setState(() => _busy = false);
    if (r != null) {
      HapticFeedback.heavyImpact();
      await showDialog(
        context: context,
        builder: (ctx) => AlertDialog(
          icon: Icon(Icons.check_circle_rounded, color: AtlasColors.of(ctx).success, size: 48),
          title: const Text('Tamamlandı'),
          content: Text(r['mesaj'] ?? '', textAlign: TextAlign.center),
          actions: [FilledButton(onPressed: () => Navigator.pop(ctx), child: const Text('Tamam'))],
        ),
      );
      if (mounted) Navigator.pop(context, true);
    }
  }

  @override
  Widget build(BuildContext context) {
    final doc = _doc;
    return Scaffold(
      appBar: AppBar(title: Text(widget.title), actions: [
        IconButton(tooltip: 'Yenile', onPressed: _load, icon: const Icon(Icons.refresh_rounded)),
      ]),
      body: doc == null
          ? (_error != null ? ErrorState(error: _error!, onRetry: _load) : const SkeletonList(header: true))
          : RefreshIndicator(onRefresh: _load, child: _body(doc)),
      floatingActionButton: doc == null
          ? null
          : FloatingActionButton.extended(
              onPressed: _openScanner,
              icon: const Icon(Icons.qr_code_scanner_rounded),
              label: const Text('Okut'),
            ),
      floatingActionButtonLocation: FloatingActionButtonLocation.endFloat,
      bottomNavigationBar: doc == null
          ? null
          : BottomActionBar(children: [
              FilledButton.icon(
                onPressed: _busy ? null : _validate,
                icon: _busy
                    ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                    : Icon(_sayim ? Icons.inventory_rounded : Icons.check_rounded),
                label: Text(_sayim ? 'Sayımı uygula' : (_uretim ? 'Üretimi tamamla' : 'Doğrula')),
              ),
            ]),
    );
  }

  Widget _body(Map<String, dynamic> doc) {
    final text = Theme.of(context).textTheme;
    final scheme = Theme.of(context).colorScheme;
    final lines = (doc['satirlar'] as List).cast<Map>();
    double hedef = 0, yapilan = 0;
    if (!_sayim) {
      for (final l in lines) {
        hedef += Fmt.d(l['istenen']);
        yapilan += Fmt.d(l['okutulan']).clamp(0, Fmt.d(l['istenen']));
      }
    }
    final ratio = hedef == 0 ? 0.0 : (yapilan / hedef).clamp(0.0, 1.0);
    final sayilan = _sayim ? lines.where((l) => l['sayilan'] != null).length : 0;
    final mamul = doc['mamul'] as Map?;

    return ContentWidth(
      child: ListView(padding: const EdgeInsets.fromLTRB(Gap.lg, Gap.sm, Gap.lg, 120), children: [
        AppCard(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              Expanded(child: Text(doc['ad'] ?? '', style: text.titleLarge)),
              if (!_sayim && (doc['durum'] ?? '') != '') ...[
                Builder(builder: (_) {
                  final (label, tone) = States.picking(doc['durum']);
                  return StatusChip(label, tone: tone);
                }),
              ],
            ]),
            if ((doc['cari'] ?? '') != '' && !_sayim) ...[
              const SizedBox(height: 4),
              Text(doc['cari'], style: text.bodyLarge),
            ],
            const SizedBox(height: Gap.sm),
            Wrap(spacing: Gap.lg, runSpacing: 4, children: [
              if ((doc['lokasyon'] ?? '') != '') _meta(Icons.place_rounded, doc['lokasyon']),
              if ((doc['kaynak'] ?? '') != '') _meta(Icons.link_rounded, doc['kaynak']),
              if ((doc['irsaliye_no'] ?? '') != '') _meta(Icons.receipt_long_rounded, 'İrsaliye ${doc['irsaliye_no']}'),
            ]),
            const SizedBox(height: Gap.lg),
            if (_sayim)
              Text('$sayilan / ${lines.length} kalem sayıldı', style: text.labelLarge)
            else ...[
              Row(children: [
                Expanded(child: Text('İlerleme', style: text.labelLarge)),
                Text('${Fmt.qty(yapilan)} / ${Fmt.qty(hedef)}', style: text.labelLarge?.copyWith(color: scheme.primary)),
              ]),
              const SizedBox(height: Gap.sm),
              ClipRRect(
                borderRadius: BorderRadius.circular(8),
                child: LinearProgressIndicator(
                  value: ratio,
                  minHeight: 10,
                  backgroundColor: scheme.surfaceContainer,
                  color: ratio >= 1 ? AtlasColors.of(context).success : scheme.primary,
                ),
              ),
            ],
          ]),
        ),
        if (mamul != null) ...[
          const SectionHeader('Mamul'),
          AppCard(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text((mamul['urun'] as Map)['ad'], style: text.titleSmall),
              Text('${Fmt.qty(mamul['miktar'])} ${mamul['birim']}', style: text.bodyMedium),
              if ((mamul['seriler'] as List).isNotEmpty) ...[
                const SizedBox(height: Gap.sm),
                Wrap(spacing: 6, runSpacing: 6, children: [
                  for (final s in mamul['seriler'] as List) StatusChip(s, tone: Tone.info, icon: Icons.qr_code_2_rounded),
                ]),
              ],
              if (['lot', 'serial'].contains((mamul['urun'] as Map)['takip'])) ...[
                const SizedBox(height: Gap.md),
                OutlinedButton.icon(
                  onPressed: () => _generateSerials(),
                  icon: const Icon(Icons.auto_awesome_rounded),
                  label: const Text('Mamul serisi üret'),
                ),
              ],
            ]),
          ),
        ],
        SectionHeader(_sayim ? 'Lokasyondaki ürünler' : (_uretim ? 'Malzemeler' : 'Ürünler')),
        if (lines.isEmpty)
          Padding(
            padding: const EdgeInsets.all(Gap.xl),
            child: Text(_sayim ? 'Lokasyonda kayıtlı ürün yok. Okutarak ekleyin.' : 'Satır yok.',
                textAlign: TextAlign.center, style: text.bodyMedium?.copyWith(color: scheme.onSurfaceVariant)),
          ),
        for (final l in lines) ...[
          _sayim ? _countLine(l) : _moveLine(l),
          const SizedBox(height: Gap.sm),
        ],
      ]),
    );
  }

  Widget _meta(IconData icon, String value) {
    final scheme = Theme.of(context).colorScheme;
    return Row(mainAxisSize: MainAxisSize.min, children: [
      Icon(icon, size: 16, color: scheme.onSurfaceVariant),
      const SizedBox(width: 4),
      Flexible(child: Text(value, style: Theme.of(context).textTheme.bodySmall, overflow: TextOverflow.ellipsis)),
    ]);
  }

  Widget _moveLine(Map l) {
    final text = Theme.of(context).textTheme;
    final scheme = Theme.of(context).colorScheme;
    final c = AtlasColors.of(context);
    final urun = l['urun'] as Map;
    final istenen = Fmt.d(l['istenen']), okutulan = Fmt.d(l['okutulan']);
    final tamam = l['tamam'] == true;
    final fazla = okutulan > istenen;
    final seriler = (l['seriler'] as List?) ?? [];
    final tracked = urun['takip'] == 'serial' || urun['takip'] == 'lot';
    return AppCard(
      onTap: () => _manualQty(l),
      color: tamam ? c.successContainer.withValues(alpha: .5) : null,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Icon(tamam ? Icons.check_circle_rounded : Icons.radio_button_unchecked_rounded,
              color: tamam ? c.success : scheme.outline, size: 22, semanticLabel: tamam ? 'Tamamlandı' : 'Eksik'),
          const SizedBox(width: Gap.md),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(urun['ad'], style: text.titleSmall),
              Text([urun['kod'], if (tracked) (urun['takip'] == 'serial' ? 'Seri takipli' : 'Lot takipli')].where((s) => s != '').join('  •  '),
                  style: text.bodySmall),
            ]),
          ),
          Text('${Fmt.qty(okutulan)} / ${Fmt.qty(istenen)}',
              style: text.titleSmall?.copyWith(color: fazla ? c.warning : (tamam ? c.success : scheme.onSurface))),
        ]),
        if (seriler.isNotEmpty) ...[
          const SizedBox(height: Gap.sm),
          Wrap(spacing: 6, runSpacing: 6, children: [
            for (final s in seriler.take(12)) StatusChip(s, icon: Icons.qr_code_2_rounded),
            if (seriler.length > 12) StatusChip('+${seriler.length - 12}'),
          ]),
        ],
        if (widget.islem == 'mal_kabul' && tracked && !tamam) ...[
          const SizedBox(height: Gap.sm),
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton.icon(
              onPressed: () => _generateSerials(moveId: l['move_id']),
              icon: const Icon(Icons.auto_awesome_rounded, size: 18),
              label: const Text('Seri üret'),
            ),
          ),
        ],
      ]),
    );
  }

  Widget _countLine(Map l) {
    final text = Theme.of(context).textTheme;
    final c = AtlasColors.of(context);
    final urun = l['urun'] as Map;
    final sayildi = l['sayilan'] != null;
    final fark = Fmt.d(l['fark']);
    return AppCard(
      onTap: () => _manualQty(l),
      child: Row(children: [
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(urun['ad'], style: text.titleSmall),
            Text([urun['kod'], if ((l['seri'] ?? '') != '') 'Seri ${l['seri']}'].where((s) => s != '').join('  •  '), style: text.bodySmall),
            const SizedBox(height: 4),
            Text('Sistem: ${Fmt.qty(l['sistem'])} ${l['birim']}', style: text.bodySmall),
          ]),
        ),
        Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
          Text(sayildi ? Fmt.qty(l['sayilan']) : '—', style: text.titleLarge),
          if (sayildi)
            StatusChip(fark == 0 ? 'Eşit' : '${fark > 0 ? '+' : ''}${Fmt.qty(fark)}',
                tone: fark == 0 ? Tone.success : (fark > 0 ? Tone.info : Tone.danger))
          else
            Text('Sayılmadı', style: text.bodySmall?.copyWith(color: c.warning)),
        ]),
      ]),
    );
  }
}

/// Artı/eksi düğmeli miktar girişi.
class QtyStepper extends StatelessWidget {
  const QtyStepper({super.key, required this.controller, this.unit = '', this.onChanged});
  final TextEditingController controller;
  final String unit;
  final ValueChanged<double>? onChanged;

  void _step(double delta) {
    final v = (double.tryParse(controller.text.replaceAll(',', '.')) ?? 0) + delta;
    final nv = v < 0 ? 0.0 : v;
    controller.text = Fmt.qty(nv).replaceAll('.', '');
    onChanged?.call(nv);
  }

  @override
  Widget build(BuildContext context) {
    return Row(children: [
      IconButton.filledTonal(tooltip: 'Azalt', onPressed: () => _step(-1), icon: const Icon(Icons.remove_rounded)),
      const SizedBox(width: Gap.md),
      Expanded(
        child: TextField(
          controller: controller,
          textAlign: TextAlign.center,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          style: Theme.of(context).textTheme.titleLarge,
          onChanged: (v) => onChanged?.call(double.tryParse(v.replaceAll(',', '.')) ?? 0),
          decoration: InputDecoration(suffixText: unit),
        ),
      ),
      const SizedBox(width: Gap.md),
      IconButton.filledTonal(tooltip: 'Artır', onPressed: () => _step(1), icon: const Icon(Icons.add_rounded)),
    ]);
  }
}
