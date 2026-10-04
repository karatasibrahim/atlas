import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:geolocator/geolocator.dart';
import 'package:image_picker/image_picker.dart';
import 'package:provider/provider.dart';

import '../../core/api.dart';
import '../../core/format.dart';
import '../../core/session.dart';
import '../../core/theme.dart';
import '../../widgets/common.dart';

/// Konum alınabiliyorsa döndürür; izin yoksa veya kapalıysa null (giriş/çıkış konumsuz yapılır).
Future<Position?> _tryPosition() async {
  try {
    if (!await Geolocator.isLocationServiceEnabled()) return null;
    var perm = await Geolocator.checkPermission();
    if (perm == LocationPermission.denied) perm = await Geolocator.requestPermission();
    if (perm == LocationPermission.denied || perm == LocationPermission.deniedForever) return null;
    return await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(accuracy: LocationAccuracy.high, timeLimit: Duration(seconds: 10)));
  } catch (_) {
    return null;
  }
}

/// Ana sayfada ve devam ekranında kullanılan giriş/çıkış kartı (canlı sayaçlı).
class AttendanceCard extends StatefulWidget {
  const AttendanceCard({super.key, required this.data, this.onChanged, this.compact = false});
  final Map data;
  final ValueChanged<Map>? onChanged;
  final bool compact;

  @override
  State<AttendanceCard> createState() => _AttendanceCardState();
}

class _AttendanceCardState extends State<AttendanceCard> {
  late Map _data = widget.data;
  Timer? _timer;
  bool _busy = false;
  late DateTime _loadedAt = DateTime.now();

  @override
  void initState() {
    super.initState();
    _timer = Timer.periodic(const Duration(seconds: 30), (_) {
      if (mounted && _checkedIn) setState(() {});
    });
  }

  @override
  void didUpdateWidget(covariant AttendanceCard old) {
    super.didUpdateWidget(old);
    if (old.data != widget.data) {
      _data = widget.data;
      _loadedAt = DateTime.now();
    }
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  bool get _checkedIn => _data['durum'] == 'checked_in';

  double get _hoursNow {
    final base = Fmt.d(_data['bugun_saat']);
    return _checkedIn ? base + DateTime.now().difference(_loadedAt).inSeconds / 3600 : base;
  }

  Future<void> _toggle() async {
    setState(() => _busy = true);
    HapticFeedback.mediumImpact();
    final pos = await _tryPosition();
    if (!mounted) return;
    final r = await runAction(
      context,
      () async => Map<String, dynamic>.from(await context.read<AppState>().api.mobil('devam_degistir', {
        'enlem': pos?.latitude ?? false,
        'boylam': pos?.longitude ?? false,
      })),
      success: _checkedIn ? 'Çıkış yapıldı. İyi dinlenmeler!' : 'Giriş yapıldı. İyi çalışmalar!',
    );
    if (!mounted) return;
    setState(() {
      _busy = false;
      if (r != null) {
        _data = r;
        _loadedAt = DateTime.now();
      }
    });
    if (r != null) widget.onChanged?.call(r);
  }

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    final scheme = Theme.of(context).colorScheme;
    final c = AtlasColors.of(context);
    final color = _checkedIn ? c.success : scheme.primary;
    return AppCard(
      child: Row(children: [
        Container(
          width: 48,
          height: 48,
          decoration: BoxDecoration(color: color.withValues(alpha: .12), shape: BoxShape.circle),
          child: Icon(_checkedIn ? Icons.work_history_rounded : Icons.login_rounded, color: color),
        ),
        const SizedBox(width: Gap.md),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(_checkedIn ? 'Mesaidesiniz' : 'Mesai dışı', style: text.titleSmall),
            Text(
              _checkedIn ? 'Giriş ${Fmt.time(_data['giris'])}  •  Bugün ${Fmt.hours(_hoursNow)}' : 'Bugün ${Fmt.hours(_hoursNow)} çalışıldı',
              style: text.bodySmall,
            ),
          ]),
        ),
        const SizedBox(width: Gap.sm),
        FilledButton(
          style: FilledButton.styleFrom(
            backgroundColor: _checkedIn ? c.danger : c.success,
            minimumSize: const Size(96, 44),
            padding: const EdgeInsets.symmetric(horizontal: 16),
          ),
          onPressed: _busy ? null : _toggle,
          child: _busy
              ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
              : Text(_checkedIn ? 'Çıkış' : 'Giriş'),
        ),
      ]),
    );
  }
}

class AttendanceScreen extends StatelessWidget {
  const AttendanceScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final api = context.read<AppState>().api;
    return Scaffold(
      appBar: AppBar(title: const Text('Giriş / Çıkış')),
      body: DataView<List>(
        load: () async => [await api.mobil('devam_durum'), await api.mobil('devam_gecmis')],
        builder: (context, data, reload) {
          final text = Theme.of(context).textTheme;
          final history = (data[1] as List).cast<Map>();
          return ContentWidth(
            child: ListView(padding: const EdgeInsets.all(Gap.lg), children: [
              AttendanceCard(data: data[0], onChanged: (_) => reload()),
              const SizedBox(height: Gap.sm),
              Text('Giriş ve çıkışta konumunuz (izin verdiyseniz) kaydedilir.', style: text.bodySmall),
              const SectionHeader('Geçmiş'),
              if (history.isEmpty) const EmptyState(icon: Icons.history_rounded, title: 'Kayıt yok'),
              for (final h in history)
                Padding(
                  padding: const EdgeInsets.only(bottom: Gap.sm),
                  child: AppCard(
                    padding: const EdgeInsets.all(Gap.md),
                    child: Row(children: [
                      SizedBox(
                        width: 52,
                        child: Column(children: [
                          Text(Fmt.weekday(h['giris']), style: text.bodySmall),
                          Text(Fmt.dateShort(h['giris']).split(' ').first, style: text.titleLarge),
                        ]),
                      ),
                      const SizedBox(width: Gap.md),
                      Expanded(
                        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                          Text('${Fmt.time(h['giris'])} → ${h['cikis'] == false ? 'devam ediyor' : Fmt.time(h['cikis'])}',
                              style: text.titleSmall),
                          if ((h['konum'] ?? '') != '') Text(h['konum'], style: text.bodySmall, maxLines: 1, overflow: TextOverflow.ellipsis),
                        ]),
                      ),
                      Text(Fmt.hours(h['saat']), style: text.labelLarge),
                    ]),
                  ),
                ),
            ]),
          );
        },
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Masraf
// ---------------------------------------------------------------------------

class ExpensesScreen extends StatefulWidget {
  const ExpensesScreen({super.key});

  @override
  State<ExpensesScreen> createState() => _ExpensesScreenState();
}

class _ExpensesScreenState extends State<ExpensesScreen> {
  final _key = GlobalKey<DataViewState<List>>();

  Future<void> _create() async {
    final r = await Navigator.push(context, MaterialPageRoute(builder: (_) => const ExpenseFormScreen()));
    if (r != null) _key.currentState?.reload();
  }

  Future<void> _submit(Map e) async {
    final r = await runAction(context, () => context.read<AppState>().api.mobil('masraf_gonder', {'expense_id': e['id']}),
        success: 'Masraf onaya gönderildi');
    if (r != null) _key.currentState?.reload();
  }

  @override
  Widget build(BuildContext context) {
    final api = context.read<AppState>().api;
    return Scaffold(
      appBar: AppBar(title: const Text('Masraflarım')),
      floatingActionButton: FloatingActionButton.extended(
          onPressed: _create, icon: const Icon(Icons.add_a_photo_rounded), label: const Text('Masraf gir')),
      body: DataView<List>(
        key: _key,
        load: () async => (await api.mobil('masraf_listesi')) as List,
        builder: (context, items, _) {
          final text = Theme.of(context).textTheme;
          if (items.isEmpty) {
            return EmptyState(
              icon: Icons.receipt_long_outlined,
              title: 'Masraf yok',
              message: 'Fişin fotoğrafını çekerek saniyeler içinde masraf girin.',
              action: FilledButton.tonal(onPressed: _create, child: const Text('Masraf gir')),
            );
          }
          final draft = items.where((e) => e['durum'] == 'draft').fold<double>(0, (a, e) => a + Fmt.d(e['tutar']));
          return ListView(padding: const EdgeInsets.fromLTRB(Gap.lg, Gap.lg, Gap.lg, 96), children: [
            if (draft > 0)
              Padding(
                padding: const EdgeInsets.only(bottom: Gap.md),
                child: AppCard(
                  color: AtlasColors.of(context).warningContainer,
                  child: Row(children: [
                    Icon(Icons.pending_actions_rounded, color: AtlasColors.of(context).warning),
                    const SizedBox(width: Gap.md),
                    Expanded(child: Text('Gönderilmemiş masraflar: ${Fmt.money(draft, items.first['para_simge'])}', style: text.titleSmall)),
                  ]),
                ),
              ),
            for (final e in items)
              Padding(
                padding: const EdgeInsets.only(bottom: Gap.sm),
                child: AppCard(
                  padding: const EdgeInsets.all(Gap.md),
                  child: Row(children: [
                    Container(
                      width: 44,
                      height: 44,
                      decoration: BoxDecoration(
                          color: Theme.of(context).colorScheme.primary.withValues(alpha: .1), borderRadius: BorderRadius.circular(12)),
                      child: Icon(Fmt.d(e['ek']) > 0 ? Icons.receipt_rounded : Icons.payments_outlined,
                          color: Theme.of(context).colorScheme.primary),
                    ),
                    const SizedBox(width: Gap.md),
                    Expanded(
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Text(e['ad'], style: text.titleSmall, maxLines: 1, overflow: TextOverflow.ellipsis),
                        Text('${e['kategori']}  •  ${Fmt.date(e['tarih'])}', style: text.bodySmall),
                        const SizedBox(height: 4),
                        StatusChip(e['durum_ad'], tone: States.approval(e['durum'])),
                      ]),
                    ),
                    Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
                      Text(Fmt.money(e['tutar'], e['para_simge']), style: text.titleSmall),
                      if (e['durum'] == 'draft')
                        TextButton(onPressed: () => _submit(e), child: const Text('Gönder')),
                    ]),
                  ]),
                ),
              ),
          ]);
        },
      ),
    );
  }
}

class ExpenseFormScreen extends StatefulWidget {
  const ExpenseFormScreen({super.key});

  @override
  State<ExpenseFormScreen> createState() => _ExpenseFormScreenState();
}

class _ExpenseFormScreenState extends State<ExpenseFormScreen> {
  final _form = GlobalKey<FormState>();
  final _ad = TextEditingController(), _tutar = TextEditingController(), _not = TextEditingController();
  int? _urunId;
  DateTime _tarih = DateTime.now();
  XFile? _photo;
  bool _sirket = false, _busy = false;

  Future<void> _pick(ImageSource source) async {
    final f = await ImagePicker().pickImage(source: source, maxWidth: 1800, imageQuality: 75);
    if (f != null) setState(() => _photo = f);
  }

  Future<void> _save(bool gonder) async {
    if (!_form.currentState!.validate()) return;
    if (_urunId == null) {
      showError(context, OdooException('Masraf kategorisini seçin.'));
      return;
    }
    setState(() => _busy = true);
    String? b64;
    if (_photo != null) b64 = base64Encode(await _photo!.readAsBytes());
    if (!mounted) return;
    final r = await runAction(
      context,
      () => context.read<AppState>().api.mobil('masraf_olustur', {
        'ad': _ad.text.trim(),
        'tutar': double.tryParse(_tutar.text.replaceAll('.', '').replaceAll(',', '.')) ?? 0,
        'urun_id': _urunId,
        'tarih': _tarih.toIso8601String().substring(0, 10),
        'aciklama': _not.text.trim(),
        'fis_b64': b64 ?? false,
        'fis_adi': _photo?.name ?? 'fis.jpg',
        'sirket_odedi': _sirket,
        'gonder': gonder,
      }),
      success: gonder ? 'Masraf onaya gönderildi' : 'Masraf kaydedildi',
    );
    if (!mounted) return;
    setState(() => _busy = false);
    if (r != null) Navigator.pop(context, r);
  }

  @override
  Widget build(BuildContext context) {
    final api = context.read<AppState>().api;
    final text = Theme.of(context).textTheme;
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(title: const Text('Yeni masraf')),
      bottomNavigationBar: BottomActionBar(children: [
        OutlinedButton(onPressed: _busy ? null : () => _save(false), child: const Text('Kaydet')),
        FilledButton(onPressed: _busy ? null : () => _save(true), child: const Text('Onaya gönder')),
      ]),
      body: DataView<List>(
        refreshable: false,
        load: () async => (await api.mobil('masraf_urunleri')) as List,
        builder: (context, cats, _) => Form(
          key: _form,
          child: ContentWidth(
            child: ListView(padding: const EdgeInsets.all(Gap.lg), children: [
              // Fiş fotoğrafı
              AspectRatio(
                aspectRatio: 16 / 9,
                child: Material(
                  color: scheme.surfaceContainerLow,
                  borderRadius: BorderRadius.circular(Gap.radius),
                  clipBehavior: Clip.antiAlias,
                  child: InkWell(
                    onTap: () => _pick(ImageSource.camera),
                    child: _photo == null
                        ? Column(mainAxisAlignment: MainAxisAlignment.center, children: [
                            Icon(Icons.photo_camera_rounded, size: 40, color: scheme.primary),
                            const SizedBox(height: Gap.sm),
                            Text('Fişin fotoğrafını çekin', style: text.titleSmall?.copyWith(color: scheme.primary)),
                            TextButton(onPressed: () => _pick(ImageSource.gallery), child: const Text('veya galeriden seçin')),
                          ])
                        : Stack(fit: StackFit.expand, children: [
                            FutureBuilder(
                              future: _photo!.readAsBytes(),
                              builder: (_, s) => s.hasData ? Image.memory(s.data!, fit: BoxFit.cover) : const SizedBox(),
                            ),
                            Positioned(
                              right: 8,
                              top: 8,
                              child: IconButton.filled(
                                tooltip: 'Fotoğrafı kaldır',
                                onPressed: () => setState(() => _photo = null),
                                icon: const Icon(Icons.close_rounded),
                              ),
                            ),
                          ]),
                  ),
                ),
              ),
              const SizedBox(height: Gap.xl),
              Text('Kategori *', style: text.labelLarge),
              const SizedBox(height: Gap.sm),
              Wrap(spacing: Gap.sm, runSpacing: Gap.sm, children: [
                for (final k in cats)
                  ChoiceChip(
                    label: Text(k['ad']),
                    selected: _urunId == k['id'],
                    onSelected: (_) => setState(() {
                      _urunId = k['id'];
                      if (_ad.text.isEmpty) _ad.text = k['ad'];
                    }),
                  ),
              ]),
              const SizedBox(height: Gap.lg),
              TextFormField(
                controller: _ad,
                decoration: const InputDecoration(labelText: 'Açıklama *', hintText: 'Örn. Müşteri ziyareti taksi'),
                validator: (v) => (v ?? '').trim().isEmpty ? 'Açıklama gerekli' : null,
              ),
              const SizedBox(height: Gap.md),
              Row(children: [
                Expanded(
                  child: TextFormField(
                    controller: _tutar,
                    keyboardType: const TextInputType.numberWithOptions(decimal: true),
                    style: text.titleMedium,
                    decoration: InputDecoration(labelText: 'Tutar (KDV dahil) *', suffixText: context.read<AppState>().currencySymbol),
                    validator: (v) => (double.tryParse((v ?? '').replaceAll('.', '').replaceAll(',', '.')) ?? 0) <= 0 ? 'Tutar girin' : null,
                  ),
                ),
                const SizedBox(width: Gap.md),
                Expanded(
                  child: InkWell(
                    borderRadius: BorderRadius.circular(Gap.radiusSm),
                    onTap: () async {
                      final d = await showDatePicker(
                          context: context, initialDate: _tarih, firstDate: DateTime(2020), lastDate: DateTime.now());
                      if (d != null) setState(() => _tarih = d);
                    },
                    child: InputDecorator(
                      decoration: const InputDecoration(labelText: 'Tarih', suffixIcon: Icon(Icons.calendar_month_rounded)),
                      child: Text(Fmt.date(_tarih.toIso8601String())),
                    ),
                  ),
                ),
              ]),
              const SizedBox(height: Gap.md),
              SwitchListTile.adaptive(
                contentPadding: EdgeInsets.zero,
                value: _sirket,
                onChanged: (v) => setState(() => _sirket = v),
                title: const Text('Şirket kartıyla ödendi'),
                subtitle: Text(_sirket ? 'Size geri ödeme yapılmaz' : 'Kendi cebinizden ödediniz; size geri ödenir', style: text.bodySmall),
              ),
              TextFormField(controller: _not, minLines: 2, maxLines: 5, decoration: const InputDecoration(labelText: 'Not')),
            ]),
          ),
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// İzin
// ---------------------------------------------------------------------------

class LeavesScreen extends StatefulWidget {
  const LeavesScreen({super.key});

  @override
  State<LeavesScreen> createState() => _LeavesScreenState();
}

class _LeavesScreenState extends State<LeavesScreen> {
  final _key = GlobalKey<DataViewState<List>>();

  Future<void> _create() async {
    final r = await Navigator.push(context, MaterialPageRoute(builder: (_) => const LeaveFormScreen()));
    if (r != null) _key.currentState?.reload();
  }

  Future<void> _withdraw(Map l) async {
    if (!await confirm(context, title: 'İzin talebini geri çek', ok: 'Geri çek', destructive: true)) return;
    if (!mounted) return;
    final r = await runAction(context, () => context.read<AppState>().api.mobil('izin_iptal', {'leave_id': l['id']}),
        success: 'Talep geri çekildi');
    if (r != null) _key.currentState?.reload();
  }

  @override
  Widget build(BuildContext context) {
    final api = context.read<AppState>().api;
    return Scaffold(
      appBar: AppBar(title: const Text('İzinlerim')),
      floatingActionButton:
          FloatingActionButton.extended(onPressed: _create, icon: const Icon(Icons.add_rounded), label: const Text('İzin iste')),
      body: DataView<List>(
        key: _key,
        load: () async => [await api.mobil('izin_turleri'), await api.mobil('izin_listesi')],
        builder: (context, data, _) {
          final text = Theme.of(context).textTheme;
          final types = (data[0] as List).where((t) => t['tahsis'] == true && t['kalan'] != null && t['kalan'] != false).toList();
          final leaves = (data[1] as List).cast<Map>();
          return ListView(padding: const EdgeInsets.fromLTRB(Gap.lg, Gap.lg, Gap.lg, 96), children: [
            if (types.isNotEmpty) ...[
              SizedBox(
                height: 104,
                child: ListView.separated(
                  scrollDirection: Axis.horizontal,
                  itemCount: types.length,
                  separatorBuilder: (_, _) => const SizedBox(width: Gap.md),
                  itemBuilder: (context, i) => SizedBox(
                    width: 160,
                    child: AppCard(
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Text(types[i]['ad'], style: text.bodySmall, maxLines: 1, overflow: TextOverflow.ellipsis),
                        const Spacer(),
                        Text('${Fmt.qty(types[i]['kalan'])} ${types[i]['birim'] == 'hour' ? 'saat' : 'gün'}', style: text.titleLarge),
                        Text('kalan', style: text.bodySmall),
                      ]),
                    ),
                  ),
                ),
              ),
              const SizedBox(height: Gap.md),
            ],
            if (leaves.isEmpty) const EmptyState(icon: Icons.beach_access_outlined, title: 'İzin talebiniz yok'),
            for (final l in leaves)
              Padding(
                padding: const EdgeInsets.only(bottom: Gap.sm),
                child: AppCard(
                  padding: const EdgeInsets.all(Gap.md),
                  child: Row(children: [
                    Expanded(
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Text(l['tur'], style: text.titleSmall),
                        Text('${Fmt.date(l['bas'])} – ${Fmt.date(l['bit'])}  •  ${l['sure']}', style: text.bodySmall),
                        const SizedBox(height: 4),
                        StatusChip(l['durum_ad'], tone: States.approval(l['durum'])),
                      ]),
                    ),
                    if (l['durum'] == 'confirm')
                      IconButton(tooltip: 'Geri çek', onPressed: () => _withdraw(l), icon: const Icon(Icons.undo_rounded)),
                  ]),
                ),
              ),
          ]);
        },
      ),
    );
  }
}

class LeaveFormScreen extends StatefulWidget {
  const LeaveFormScreen({super.key});

  @override
  State<LeaveFormScreen> createState() => _LeaveFormScreenState();
}

class _LeaveFormScreenState extends State<LeaveFormScreen> {
  int? _type;
  DateTimeRange? _range;
  final _note = TextEditingController();
  bool _busy = false;

  String _d(DateTime d) => d.toIso8601String().substring(0, 10);

  Future<void> _save() async {
    if (_type == null || _range == null) {
      showError(context, OdooException('İzin türünü ve tarihleri seçin.'));
      return;
    }
    setState(() => _busy = true);
    final r = await runAction(
      context,
      () => context.read<AppState>().api.mobil('izin_olustur', {
        'tur_id': _type,
        'bas': _d(_range!.start),
        'bit': _d(_range!.end),
        'aciklama': _note.text.trim(),
      }),
      success: 'İzin talebi gönderildi',
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
      appBar: AppBar(title: const Text('İzin talebi')),
      bottomNavigationBar: BottomActionBar(children: [FilledButton(onPressed: _busy ? null : _save, child: const Text('Gönder'))]),
      body: DataView<List>(
        refreshable: false,
        load: () async => (await api.mobil('izin_turleri')) as List,
        builder: (context, types, _) => ContentWidth(
          child: ListView(padding: const EdgeInsets.all(Gap.lg), children: [
            Text('İzin türü', style: text.labelLarge),
            const SizedBox(height: Gap.sm),
            RadioGroup<int>(
              groupValue: _type,
              onChanged: (v) => setState(() => _type = v),
              child: Column(children: [
                for (final t in types)
                  RadioListTile<int>(
                    value: t['id'],
                    title: Text(t['ad']),
                    subtitle: t['tahsis'] == true && t['kalan'] != null && t['kalan'] != false
                        ? Text('Kalan: ${Fmt.qty(t['kalan'])} ${t['birim'] == 'hour' ? 'saat' : 'gün'}')
                        : null,
                    contentPadding: EdgeInsets.zero,
                  ),
              ]),
            ),
            const SizedBox(height: Gap.lg),
            InkWell(
              borderRadius: BorderRadius.circular(Gap.radiusSm),
              onTap: () async {
                final now = DateTime.now();
                final r = await showDateRangePicker(
                  context: context,
                  firstDate: now.subtract(const Duration(days: 60)),
                  lastDate: now.add(const Duration(days: 365)),
                  initialDateRange: _range,
                );
                if (r != null) setState(() => _range = r);
              },
              child: InputDecorator(
                decoration: const InputDecoration(labelText: 'Tarihler', suffixIcon: Icon(Icons.date_range_rounded)),
                isEmpty: _range == null,
                child: Text(_range == null
                    ? ''
                    : '${Fmt.date(_range!.start.toIso8601String())} – ${Fmt.date(_range!.end.toIso8601String())}  (${_range!.duration.inDays + 1} gün)'),
              ),
            ),
            const SizedBox(height: Gap.md),
            TextField(controller: _note, minLines: 2, maxLines: 5, decoration: const InputDecoration(labelText: 'Açıklama')),
          ]),
        ),
      ),
    );
  }
}
