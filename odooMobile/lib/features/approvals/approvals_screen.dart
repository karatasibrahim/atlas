import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/api.dart';
import '../../core/format.dart';
import '../../core/session.dart';
import '../../core/theme.dart';
import '../../widgets/common.dart';

IconData _sourceIcon(String kaynak) => switch (kaynak) {
      'masraf' => Icons.receipt_long_rounded,
      'izin' => Icons.beach_access_rounded,
      _ => Icons.verified_rounded,
    };

/// Onay merkezi: Atlas onay talepleri, masraflar ve izinler tek listede.
class ApprovalsScreen extends StatefulWidget {
  const ApprovalsScreen({super.key});

  @override
  State<ApprovalsScreen> createState() => _ApprovalsScreenState();
}

class _ApprovalsScreenState extends State<ApprovalsScreen> {
  final _pending = GlobalKey<DataViewState<List>>();
  final _mine = GlobalKey<DataViewState<List>>();

  OdooClient get _api => context.read<AppState>().api;

  Future<void> _refresh() async {
    await Future.wait([_pending.currentState?.reload() ?? Future.value(), _mine.currentState?.reload() ?? Future.value()]);
    if (mounted) context.read<AppState>().refreshBadges();
  }

  Future<void> _openDetail(String kaynak, int id) async {
    final changed = await Navigator.push<bool>(
        context, MaterialPageRoute(builder: (_) => ApprovalDetailScreen(kaynak: kaynak, id: id)));
    if (changed == true) _refresh();
  }

  Future<void> _quickApprove(Map item) async {
    final r = await runAction(context, () => _api.mobil('onay_ver', {'kaynak': item['kaynak'], 'res_id': item['id']}),
        success: 'Onaylandı');
    if (r != null) _refresh();
  }

  Future<void> _newRequest() async {
    final r = await Navigator.push(context, MaterialPageRoute(builder: (_) => const ApprovalRequestForm()));
    if (r != null) _refresh();
  }

  @override
  Widget build(BuildContext context) {
    final canRequest = context.watch<AppState>().can('onay');
    return DefaultTabController(
      length: 2,
      child: Scaffold(
        appBar: AppBar(
          title: const Text('Onaylar'),
          bottom: const TabBar(tabs: [Tab(text: 'Onayımı bekleyen'), Tab(text: 'Taleplerim')]),
        ),
        floatingActionButton: canRequest
            ? FloatingActionButton.extended(onPressed: _newRequest, icon: const Icon(Icons.add_rounded), label: const Text('Yeni talep'))
            : null,
        body: TabBarView(children: [
          DataView<List>(
            key: _pending,
            load: () async {
              final appState = context.read<AppState>();
              final r = (await appState.api.mobil('onay_listesi')) as List;
              appState.refreshBadges();
              return r;
            },
            builder: (context, items, _) => items.isEmpty
                ? const EmptyState(icon: Icons.task_alt_rounded, title: 'Her şey yolunda', message: 'Onayınızı bekleyen bir talep yok.')
                : ListView.separated(
                    padding: const EdgeInsets.fromLTRB(Gap.lg, Gap.lg, Gap.lg, 96),
                    itemCount: items.length,
                    separatorBuilder: (_, _) => const SizedBox(height: Gap.md),
                    itemBuilder: (context, i) => _PendingCard(
                      item: items[i],
                      onTap: () => _openDetail(items[i]['kaynak'], items[i]['id']),
                      onApprove: () => _quickApprove(items[i]),
                    ),
                  ),
          ),
          DataView<List>(
            key: _mine,
            load: () async => canRequest ? (await _api.mobil('onay_taleplerim')) as List : [],
            builder: (context, items, _) => items.isEmpty
                ? EmptyState(
                    icon: Icons.outbox_rounded,
                    title: 'Talebiniz yok',
                    message: 'Avans, satın alma, seyahat gibi onay taleplerinizi buradan oluşturabilirsiniz.',
                    action: canRequest ? FilledButton.tonal(onPressed: _newRequest, child: const Text('Yeni talep')) : null,
                  )
                : ListView.separated(
                    padding: const EdgeInsets.fromLTRB(Gap.lg, Gap.lg, Gap.lg, 96),
                    itemCount: items.length,
                    separatorBuilder: (_, _) => const SizedBox(height: Gap.sm),
                    itemBuilder: (context, i) {
                      final t = items[i] as Map;
                      final text = Theme.of(context).textTheme;
                      return AppCard(
                        padding: const EdgeInsets.all(Gap.md),
                        onTap: () => _openDetail('onay', t['id']),
                        child: Row(children: [
                          Expanded(
                            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                              Text(t['baslik'], style: text.titleSmall),
                              Text('${t['no']}  •  ${t['kategori']}', style: text.bodySmall),
                              const SizedBox(height: 6),
                              Row(children: [
                                StatusChip(t['durum_ad'], tone: States.approval(t['durum'])),
                                const SizedBox(width: Gap.sm),
                                if (t['durum'] == 'beklemede') Text('${t['ilerleme']} onay', style: text.bodySmall),
                              ]),
                            ]),
                          ),
                          if (t['tutar'] != false) Text(Fmt.money(t['tutar'], t['para_simge']), style: text.titleSmall),
                        ]),
                      );
                    },
                  ),
          ),
        ]),
      ),
    );
  }
}

class _PendingCard extends StatelessWidget {
  const _PendingCard({required this.item, required this.onTap, required this.onApprove});
  final Map item;
  final VoidCallback onTap, onApprove;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    final scheme = Theme.of(context).colorScheme;
    return AppCard(
      onTap: onTap,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Avatar(name: item['kisi'], image: item['kisi_gorsel'], size: 40),
          const SizedBox(width: Gap.md),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(item['kisi'], style: text.titleSmall),
              Text(Fmt.relative(item['tarih']), style: text.bodySmall),
            ]),
          ),
          StatusChip(item['kategori'], tone: Tone.primary, icon: _sourceIcon(item['kaynak'])),
        ]),
        const SizedBox(height: Gap.md),
        Text(item['baslik'], style: text.titleMedium),
        if ((item['donem'] ?? '') != '') Text(item['donem'], style: text.bodySmall),
        if (item['tutar'] != false) ...[
          const SizedBox(height: 4),
          Text(Fmt.money(item['tutar'], item['para_simge']), style: text.headlineSmall?.copyWith(color: scheme.primary)),
        ],
        const SizedBox(height: Gap.md),
        Row(children: [
          Expanded(child: OutlinedButton(onPressed: onTap, child: const Text('İncele'))),
          const SizedBox(width: Gap.md),
          Expanded(
            child: FilledButton.icon(onPressed: onApprove, icon: const Icon(Icons.check_rounded), label: const Text('Onayla')),
          ),
        ]),
      ]),
    );
  }
}

class ApprovalDetailScreen extends StatefulWidget {
  const ApprovalDetailScreen({super.key, required this.kaynak, required this.id});
  final String kaynak;
  final int id;

  @override
  State<ApprovalDetailScreen> createState() => _ApprovalDetailScreenState();
}

class _ApprovalDetailScreenState extends State<ApprovalDetailScreen> {
  bool _busy = false;
  OdooClient get _api => context.read<AppState>().api;

  Future<void> _approve() async {
    String? note;
    if (widget.kaynak == 'onay') {
      note = await promptText(context, title: 'Onay notu', hint: 'İsteğe bağlı', ok: 'Onayla');
    } else if (await confirm(context, title: 'Onaylansın mı?', ok: 'Onayla')) {
      note = '';
    }
    if (note == null || !mounted) return;
    setState(() => _busy = true);
    final r = await runAction(context, () => _api.mobil('onay_ver', {'kaynak': widget.kaynak, 'res_id': widget.id, 'aciklama': note}),
        success: 'Onaylandı');
    if (!mounted) return;
    setState(() => _busy = false);
    if (r != null) Navigator.pop(context, true);
  }

  Future<void> _reject() async {
    final reason = await promptText(context, title: 'Red nedeni', hint: 'Talep edene iletilecek', ok: 'Reddet', required: true, destructive: true);
    if (reason == null || !mounted) return;
    setState(() => _busy = true);
    final r = await runAction(context, () => _api.mobil('onay_reddet', {'kaynak': widget.kaynak, 'res_id': widget.id, 'neden': reason}),
        success: 'Reddedildi');
    if (!mounted) return;
    setState(() => _busy = false);
    if (r != null) Navigator.pop(context, true);
  }

  @override
  Widget build(BuildContext context) {
    return DataView<Map<String, dynamic>>(
      refreshable: false,
      skeleton: Scaffold(appBar: AppBar(), body: const SkeletonList(header: true)),
      load: () async => Map<String, dynamic>.from(await _api.mobil('onay_detay', {'kaynak': widget.kaynak, 'res_id': widget.id})),
      builder: (context, d, _) {
        final text = Theme.of(context).textTheme;
        final scheme = Theme.of(context).colorScheme;
        final c = AtlasColors.of(context);
        final approvers = (d['onaylayicilar'] as List?) ?? [];
        final ekler = (d['ekler'] as List?) ?? [];
        return Scaffold(
          appBar: AppBar(title: Text(d['kategori'] ?? 'Onay')),
          bottomNavigationBar: d['karar_verebilir'] == true
              ? BottomActionBar(children: [
                  OutlinedButton.icon(
                    style: OutlinedButton.styleFrom(foregroundColor: c.danger),
                    onPressed: _busy ? null : _reject,
                    icon: const Icon(Icons.close_rounded),
                    label: const Text('Reddet'),
                  ),
                  FilledButton.icon(
                    onPressed: _busy ? null : _approve,
                    icon: const Icon(Icons.check_rounded),
                    label: const Text('Onayla'),
                  ),
                ])
              : null,
          body: ContentWidth(
            child: ListView(padding: const EdgeInsets.all(Gap.lg), children: [
              AppCard(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Row(children: [
                    StatusChip(d['durum_ad'] ?? '', tone: States.approval(d['durum'] ?? '')),
                    const Spacer(),
                    if ((d['no'] ?? '') != '') Text(d['no'], style: text.bodySmall),
                  ]),
                  const SizedBox(height: Gap.md),
                  Text(d['baslik'] ?? '', style: text.titleLarge),
                  const SizedBox(height: 4),
                  Text('${d['kisi']}  •  ${Fmt.relative(d['tarih'])}', style: text.bodyMedium?.copyWith(color: scheme.onSurfaceVariant)),
                  if (d['tutar'] != false && d['tutar'] != null) ...[
                    const SizedBox(height: Gap.lg),
                    Text('Tutar', style: text.bodySmall),
                    Text(Fmt.money(d['tutar'], d['para_simge']), style: text.headlineMedium?.copyWith(color: scheme.primary)),
                  ],
                ]),
              ),
              if ((d['alanlar'] as List?)?.isNotEmpty ?? false) ...[
                const SectionHeader('Ayrıntılar'),
                AppCard(
                  padding: const EdgeInsets.symmetric(horizontal: Gap.lg, vertical: Gap.sm),
                  child: Column(children: [
                    for (final a in d['alanlar'] as List) InfoRow(a[0], _value(a[1])),
                  ]),
                ),
              ],
              if ((d['aciklama'] ?? '') != '') ...[
                const SectionHeader('Açıklama'),
                AppCard(child: Text(d['aciklama'])),
              ],
              if (ekler.isNotEmpty) ...[
                const SectionHeader('Ekler'),
                for (final e in ekler)
                  Padding(
                    padding: const EdgeInsets.only(bottom: Gap.sm),
                    child: AppCard(
                      padding: EdgeInsets.zero,
                      onTap: () => _showAttachment(context, e),
                      child: Row(children: [
                        if ((e['tip'] ?? '').toString().startsWith('image/'))
                          SizedBox(width: 72, height: 72, child: NetImage(e['url']))
                        else
                          const SizedBox(width: 72, height: 72, child: Icon(Icons.insert_drive_file_rounded)),
                        const SizedBox(width: Gap.md),
                        Expanded(child: Text(e['ad'], style: text.bodyMedium, maxLines: 2, overflow: TextOverflow.ellipsis)),
                        const SizedBox(width: Gap.md),
                      ]),
                    ),
                  ),
              ],
              if (approvers.isNotEmpty) ...[
                const SectionHeader('Onay akışı'),
                AppCard(
                  child: Column(children: [
                    for (var i = 0; i < approvers.length; i++) _ApproverStep(step: approvers[i], last: i == approvers.length - 1),
                  ]),
                ),
              ],
              const SizedBox(height: Gap.xl),
            ]),
          ),
        );
      },
    );
  }

  /// Sunucudan gelen tarih/tarih-saat değerlerini (ve "a → b" aralıklarını) okunur biçime çevirir.
  String _value(dynamic v) {
    final s = '${v == false ? '' : v}';
    if (s.contains(' → ')) return s.split(' → ').map(_value).join(' – ');
    if (RegExp(r'^\d{4}-\d{2}-\d{2}$').hasMatch(s)) return Fmt.date(s);
    if (RegExp(r'^\d{4}-\d{2}-\d{2}T').hasMatch(s)) return Fmt.dateTime(s);
    return s;
  }

  void _showAttachment(BuildContext context, Map e) {
    if (!(e['tip'] ?? '').toString().startsWith('image/')) return;
    Navigator.push(
      context,
      MaterialPageRoute(
        fullscreenDialog: true,
        builder: (_) => Scaffold(
          backgroundColor: Colors.black,
          appBar: AppBar(backgroundColor: Colors.black, foregroundColor: Colors.white, title: Text(e['ad'])),
          body: InteractiveViewer(child: Center(child: NetImage(e['url'], fit: BoxFit.contain))),
        ),
      ),
    );
  }
}

class _ApproverStep extends StatelessWidget {
  const _ApproverStep({required this.step, required this.last});
  final Map step;
  final bool last;

  @override
  Widget build(BuildContext context) {
    final c = AtlasColors.of(context);
    final scheme = Theme.of(context).colorScheme;
    final text = Theme.of(context).textTheme;
    final (icon, color, label) = switch (step['durum']) {
      'onayladi' => (Icons.check_circle_rounded, c.success, 'Onayladı'),
      'reddetti' => (Icons.cancel_rounded, c.danger, 'Reddetti'),
      'bekliyor' => (Icons.schedule_rounded, c.warning, 'Bekliyor'),
      'iptal' => (Icons.remove_circle_outline_rounded, scheme.outline, 'Gerek kalmadı'),
      _ => (Icons.radio_button_unchecked_rounded, scheme.outline, 'Sırada'),
    };
    return IntrinsicHeight(
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Column(children: [
          Icon(icon, color: color, size: 24),
          if (!last) Expanded(child: Container(width: 2, color: scheme.outlineVariant, margin: const EdgeInsets.symmetric(vertical: 4))),
        ]),
        const SizedBox(width: Gap.md),
        Expanded(
          child: Padding(
            padding: EdgeInsets.only(bottom: last ? 0 : Gap.lg),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(children: [
                Expanded(child: Text(step['ad'], style: text.titleSmall)),
                if (step['zorunlu'] == true) const StatusChip('Zorunlu'),
              ]),
              Text([label, if (step['tarih'] != false) Fmt.dateTime(step['tarih'])].join('  •  '),
                  style: text.bodySmall?.copyWith(color: color)),
              if ((step['not'] ?? '') != '') ...[const SizedBox(height: 4), Text('"${step['not']}"', style: text.bodyMedium)],
            ]),
          ),
        ),
      ]),
    );
  }
}

/// Atlas onay talebi oluşturma: kategoriye göre alanlar dinamik gösterilir.
class ApprovalRequestForm extends StatefulWidget {
  const ApprovalRequestForm({super.key});

  @override
  State<ApprovalRequestForm> createState() => _ApprovalRequestFormState();
}

class _ApprovalRequestFormState extends State<ApprovalRequestForm> {
  final _form = GlobalKey<FormState>();
  Map? _kategori;
  final _konu = TextEditingController(), _aciklama = TextEditingController(), _tutar = TextEditingController();
  final _referans = TextEditingController(), _miktar = TextEditingController();
  DateTime? _tarih;
  DateTimeRange? _donem;
  bool _busy = false;

  String _alan(String k) => (_kategori?['alanlar'] as Map?)?[k] ?? 'yok';
  bool _show(String k) => _alan(k) != 'yok';
  bool _req(String k) => _alan(k) == 'zorunlu';

  Future<void> _save() async {
    if (!_form.currentState!.validate()) return;
    if (_req('tarih') && _tarih == null || _req('donem') && _donem == null) {
      showError(context, OdooException('Zorunlu tarih alanlarını doldurun.'));
      return;
    }
    setState(() => _busy = true);
    String? iso(DateTime? d) => d?.toUtc().toIso8601String().substring(0, 19).replaceFirst('T', ' ');
    final r = await runAction(
      context,
      () => context.read<AppState>().api.mobil('onay_talep_olustur', {
        'kategori_id': _kategori!['id'],
        'konu': _konu.text.trim(),
        'aciklama': _aciklama.text.trim(),
        'tutar': double.tryParse(_tutar.text.replaceAll('.', '').replaceAll(',', '.')) ?? 0,
        'tarih': iso(_tarih) ?? false,
        'tarih_bas': iso(_donem?.start) ?? false,
        'tarih_bit': iso(_donem?.end) ?? false,
        'referans': _referans.text.trim(),
        'miktar': double.tryParse(_miktar.text.replaceAll(',', '.')) ?? 0,
      }),
      success: 'Talep onaya gönderildi',
    );
    if (!mounted) return;
    setState(() => _busy = false);
    if (r != null) Navigator.pop(context, r);
  }

  @override
  Widget build(BuildContext context) {
    final api = context.read<AppState>().api;
    final text = Theme.of(context).textTheme;
    return Scaffold(
      appBar: AppBar(title: const Text('Yeni onay talebi')),
      bottomNavigationBar: _kategori == null
          ? null
          : BottomActionBar(children: [FilledButton(onPressed: _busy ? null : _save, child: const Text('Onaya gönder'))]),
      body: DataView<List>(
        refreshable: false,
        load: () async => (await api.mobil('onay_kategorileri')) as List,
        builder: (context, cats, _) => Form(
          key: _form,
          child: ContentWidth(
            child: ListView(padding: const EdgeInsets.all(Gap.lg), children: [
              Text('Kategori', style: text.labelLarge),
              const SizedBox(height: Gap.sm),
              Wrap(spacing: Gap.sm, runSpacing: Gap.sm, children: [
                for (final k in cats)
                  ChoiceChip(label: Text(k['ad']), selected: _kategori?['id'] == k['id'], onSelected: (_) => setState(() => _kategori = k)),
              ]),
              if (_kategori != null && (_kategori!['aciklama'] ?? '') != '') ...[
                const SizedBox(height: Gap.sm),
                Text(_kategori!['aciklama'], style: text.bodySmall),
              ],
              if (_kategori != null) ...[
                const SizedBox(height: Gap.xl),
                TextFormField(
                  controller: _konu,
                  decoration: const InputDecoration(labelText: 'Konu *'),
                  validator: (v) => (v ?? '').trim().isEmpty ? 'Konu gerekli' : null,
                ),
                if (_show('tutar')) ...[
                  const SizedBox(height: Gap.md),
                  TextFormField(
                    controller: _tutar,
                    keyboardType: const TextInputType.numberWithOptions(decimal: true),
                    decoration: InputDecoration(
                        labelText: 'Tutar${_req('tutar') ? ' *' : ''}', suffixText: context.read<AppState>().currencySymbol),
                    validator: (v) => _req('tutar') && (v ?? '').trim().isEmpty ? 'Tutar gerekli' : null,
                  ),
                ],
                if (_show('tarih')) ...[
                  const SizedBox(height: Gap.md),
                  _DateField(
                    label: 'Tarih${_req('tarih') ? ' *' : ''}',
                    value: _tarih == null ? '' : Fmt.date(_tarih!.toIso8601String()),
                    onTap: () async {
                      final d = await showDatePicker(context: context, firstDate: DateTime(2020), lastDate: DateTime(2100), initialDate: _tarih ?? DateTime.now());
                      if (d != null) setState(() => _tarih = d);
                    },
                  ),
                ],
                if (_show('donem')) ...[
                  const SizedBox(height: Gap.md),
                  _DateField(
                    label: 'Dönem${_req('donem') ? ' *' : ''}',
                    value: _donem == null ? '' : '${Fmt.date(_donem!.start.toIso8601String())} – ${Fmt.date(_donem!.end.toIso8601String())}',
                    onTap: () async {
                      final d = await showDateRangePicker(context: context, firstDate: DateTime(2020), lastDate: DateTime(2100));
                      if (d != null) setState(() => _donem = d);
                    },
                  ),
                ],
                if (_show('miktar')) ...[
                  const SizedBox(height: Gap.md),
                  TextFormField(
                    controller: _miktar,
                    keyboardType: const TextInputType.numberWithOptions(decimal: true),
                    decoration: InputDecoration(labelText: 'Miktar${_req('miktar') ? ' *' : ''}'),
                    validator: (v) => _req('miktar') && (v ?? '').trim().isEmpty ? 'Miktar gerekli' : null,
                  ),
                ],
                if (_show('referans')) ...[
                  const SizedBox(height: Gap.md),
                  TextFormField(
                    controller: _referans,
                    decoration: InputDecoration(labelText: 'Referans${_req('referans') ? ' *' : ''}'),
                    validator: (v) => _req('referans') && (v ?? '').trim().isEmpty ? 'Referans gerekli' : null,
                  ),
                ],
                const SizedBox(height: Gap.md),
                TextFormField(controller: _aciklama, minLines: 3, maxLines: 8, decoration: const InputDecoration(labelText: 'Açıklama')),
                if (_req('partner') || _req('urun') || _req('ek')) ...[
                  const SizedBox(height: Gap.md),
                  Text('Bu kategoride cari, ürün veya belge eki zorunlu; talebi masaüstünden tamamlamanız gerekebilir.',
                      style: text.bodySmall?.copyWith(color: AtlasColors.of(context).warning)),
                ],
              ],
            ]),
          ),
        ),
      ),
    );
  }
}

class _DateField extends StatelessWidget {
  const _DateField({required this.label, required this.value, required this.onTap});
  final String label, value;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(Gap.radiusSm),
      child: InputDecorator(
        decoration: InputDecoration(labelText: label, suffixIcon: const Icon(Icons.calendar_month_rounded)),
        isEmpty: value.isEmpty,
        child: Text(value),
      ),
    );
  }
}
