import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/api.dart';
import '../../core/format.dart';
import '../../core/session.dart';
import '../../core/theme.dart';
import '../../widgets/common.dart';
import '../sales/sales.dart';

class PartnerListScreen extends StatefulWidget {
  const PartnerListScreen({super.key, this.picker = false});

  /// true ise seçilen cariyi döndürür (teklif/fırsat oluştururken).
  final bool picker;

  @override
  State<PartnerListScreen> createState() => _PartnerListScreenState();
}

class _PartnerListScreenState extends State<PartnerListScreen> {
  String _search = '';
  final _key = GlobalKey<DataViewState<List>>();

  Future<void> _create() async {
    final created = await Navigator.push<Map>(context, MaterialPageRoute(builder: (_) => const PartnerFormScreen()));
    if (created == null || !mounted) return;
    if (widget.picker) {
      Navigator.pop(context, created);
    } else {
      _key.currentState?.reload();
    }
  }

  @override
  Widget build(BuildContext context) {
    final api = context.read<AppState>().api;
    final text = Theme.of(context).textTheme;
    return Scaffold(
      appBar: AppBar(title: Text(widget.picker ? 'Cari seç' : 'Cariler')),
      floatingActionButton: FloatingActionButton(tooltip: 'Yeni cari', onPressed: _create, child: const Icon(Icons.person_add_alt_1_rounded)),
      body: Column(children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(Gap.lg, Gap.sm, Gap.lg, Gap.sm),
          child: SearchField(hint: 'Ad, cari kodu, telefon, VKN', onChanged: (v) {
            setState(() => _search = v);
            _key.currentState?.reload();
          }),
        ),
        Expanded(
          child: DataView<List>(
            key: _key,
            load: () async => (await api.mobil('cari_ara', {'arama': _search, 'limit': 60})) as List,
            builder: (context, items, _) => items.isEmpty
                ? EmptyState(
                    icon: Icons.people_outline_rounded,
                    title: 'Cari bulunamadı',
                    action: FilledButton.tonal(onPressed: _create, child: const Text('Yeni cari oluştur')))
                : ListView.separated(
                    padding: const EdgeInsets.fromLTRB(Gap.lg, Gap.sm, Gap.lg, 96),
                    itemCount: items.length,
                    separatorBuilder: (_, _) => const SizedBox(height: Gap.sm),
                    itemBuilder: (context, i) {
                      final p = items[i] as Map;
                      return AppCard(
                        padding: const EdgeInsets.all(Gap.md),
                        onTap: () => widget.picker
                            ? Navigator.pop(context, p)
                            : Navigator.push(context, MaterialPageRoute(builder: (_) => PartnerDetailScreen(partnerId: p['id']))),
                        child: Row(children: [
                          Avatar(name: p['ad'], image: p['gorsel']),
                          const SizedBox(width: Gap.md),
                          Expanded(
                            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                              Text(p['ad'], style: text.titleSmall, maxLines: 1, overflow: TextOverflow.ellipsis),
                              Text([p['kod'], p['sehir'], p['telefon']].where((s) => (s ?? '') != '').join('  •  '),
                                  style: text.bodySmall, maxLines: 1, overflow: TextOverflow.ellipsis),
                            ]),
                          ),
                          Icon(p['sirket'] == true ? Icons.business_rounded : Icons.person_rounded,
                              size: 18, color: Theme.of(context).colorScheme.onSurfaceVariant),
                        ]),
                      );
                    },
                  ),
          ),
        ),
      ]),
    );
  }
}

class PartnerDetailScreen extends StatelessWidget {
  const PartnerDetailScreen({super.key, required this.partnerId});
  final int partnerId;

  Future<void> _launch(BuildContext context, Uri uri) async {
    if (!await launchUrl(uri, mode: LaunchMode.externalApplication) && context.mounted) {
      showError(context, OdooException('Bu işlem için uygun bir uygulama bulunamadı.'));
    }
  }

  @override
  Widget build(BuildContext context) {
    final api = context.read<AppState>().api;
    return Scaffold(
      appBar: AppBar(title: const Text('Cari kartı')),
      body: DataView<Map<String, dynamic>>(
        load: () async => Map<String, dynamic>.from(await api.mobil('cari_detay', {'partner_id': partnerId})),
        builder: (context, p, _) {
          final text = Theme.of(context).textTheme;
          final scheme = Theme.of(context).colorScheme;
          final c = AtlasColors.of(context);
          final symbol = context.read<AppState>().currencySymbol;
          final bakiye = p['bakiye'] as Map?;
          final faturalar = (p['acik_faturalar'] as List?) ?? [];
          final siparisler = (p['siparisler'] as List?) ?? [];
          final kisiler = (p['kisiler'] as List?) ?? [];
          final adres = (p['adres'] ?? '') as String;
          return ContentWidth(
            child: ListView(padding: const EdgeInsets.all(Gap.lg), children: [
              Column(children: [
                Avatar(name: p['ad'], image: p['gorsel'], size: 80),
                const SizedBox(height: Gap.md),
                Text(p['ad'], style: text.titleLarge, textAlign: TextAlign.center),
                if ((p['kod'] ?? '') != '') Text(p['kod'], style: text.bodyMedium?.copyWith(color: scheme.onSurfaceVariant)),
                if ((p['etiketler'] as List?)?.isNotEmpty ?? false) ...[
                  const SizedBox(height: Gap.sm),
                  Wrap(spacing: 6, children: [for (final e in p['etiketler']) StatusChip(e, tone: Tone.primary)]),
                ],
              ]),
              const SizedBox(height: Gap.lg),
              Row(mainAxisAlignment: MainAxisAlignment.center, children: [
                _ActionButton(
                    icon: Icons.call_rounded,
                    label: 'Ara',
                    onTap: (p['telefon'] ?? '') == '' ? null : () => _launch(context, Uri(scheme: 'tel', path: p['telefon']))),
                _ActionButton(
                    icon: Icons.mail_rounded,
                    label: 'E-posta',
                    onTap: (p['email'] ?? '') == '' ? null : () => _launch(context, Uri(scheme: 'mailto', path: p['email']))),
                _ActionButton(
                    icon: Icons.map_rounded,
                    label: 'Yol tarifi',
                    onTap: adres.isEmpty
                        ? null
                        : () => _launch(context, Uri.parse('https://www.google.com/maps/search/?api=1&query=${Uri.encodeComponent(adres)}'))),
                _ActionButton(
                    icon: Icons.request_quote_rounded,
                    label: 'Teklif',
                    onTap: () => Navigator.push(context, MaterialPageRoute(builder: (_) => SaleCreateScreen(partner: p)))),
              ]),
              if (bakiye != null) ...[
                const SizedBox(height: Gap.lg),
                AppCard(
                  child: Row(children: [
                    Expanded(child: _Money(label: 'Borç', value: Fmt.money(bakiye['borc'], symbol))),
                    Expanded(child: _Money(label: 'Alacak', value: Fmt.money(bakiye['alacak'], symbol))),
                    Expanded(
                      child: _Money(
                        label: 'Bakiye',
                        value: Fmt.money(bakiye['bakiye'], symbol),
                        color: Fmt.d(bakiye['bakiye']) > 0 ? c.warning : c.success,
                      ),
                    ),
                  ]),
                ),
              ],
              const SectionHeader('İletişim'),
              AppCard(
                padding: const EdgeInsets.symmetric(horizontal: Gap.lg, vertical: Gap.sm),
                child: Column(children: [
                  InfoRow('Telefon', p['telefon'] ?? '', icon: Icons.phone_outlined),
                  InfoRow('E-posta', p['email'] ?? '', icon: Icons.alternate_email_rounded),
                  InfoRow('Adres', adres, icon: Icons.place_outlined),
                  InfoRow('Vergi no', p['vergi_no'] ?? '', icon: Icons.badge_outlined),
                ]),
              ),
              if (faturalar.isNotEmpty) ...[
                const SectionHeader('Açık faturalar'),
                for (final f in faturalar)
                  Padding(
                    padding: const EdgeInsets.only(bottom: Gap.sm),
                    child: AppCard(
                      padding: const EdgeInsets.all(Gap.md),
                      child: Row(children: [
                        Expanded(
                          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                            Text(f['ad'], style: text.titleSmall),
                            Text('Vade: ${Fmt.date(f['vade'])}', style: text.bodySmall),
                          ]),
                        ),
                        Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
                          Text(Fmt.money(f['kalan'], f['para_simge']), style: text.titleSmall),
                          if (f['gecikti'] == true) const StatusChip('Gecikmiş', tone: Tone.danger),
                        ]),
                      ]),
                    ),
                  ),
              ],
              if (siparisler.isNotEmpty) ...[
                const SectionHeader('Son siparişler'),
                for (final s in siparisler) Padding(padding: const EdgeInsets.only(bottom: Gap.sm), child: SaleTile(order: s)),
              ],
              if (kisiler.isNotEmpty) ...[
                const SectionHeader('İlgili kişiler'),
                for (final k in kisiler)
                  Padding(
                    padding: const EdgeInsets.only(bottom: Gap.sm),
                    child: AppCard(
                      padding: const EdgeInsets.all(Gap.md),
                      onTap: () => Navigator.push(context, MaterialPageRoute(builder: (_) => PartnerDetailScreen(partnerId: k['id']))),
                      child: Row(children: [
                        Avatar(name: k['ad'], image: k['gorsel'], size: 36),
                        const SizedBox(width: Gap.md),
                        Expanded(child: Text(k['ad'], style: text.bodyLarge)),
                        if ((k['telefon'] ?? '') != '')
                          IconButton(
                            tooltip: 'Ara',
                            icon: const Icon(Icons.call_rounded),
                            onPressed: () => _launch(context, Uri(scheme: 'tel', path: k['telefon'])),
                          ),
                      ]),
                    ),
                  ),
              ],
            ]),
          );
        },
      ),
    );
  }
}

class _ActionButton extends StatelessWidget {
  const _ActionButton({required this.icon, required this.label, this.onTap});
  final IconData icon;
  final String label;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final enabled = onTap != null;
    return Expanded(
      child: Semantics(
        button: true,
        enabled: enabled,
        label: label,
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(Gap.radius),
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: Gap.sm),
            child: Opacity(
              opacity: enabled ? 1 : .38,
              child: Column(children: [
                Container(
                  width: 52,
                  height: 52,
                  decoration: BoxDecoration(color: scheme.primary.withValues(alpha: .1), borderRadius: BorderRadius.circular(16)),
                  child: Icon(icon, color: scheme.primary),
                ),
                const SizedBox(height: 6),
                Text(label, style: Theme.of(context).textTheme.labelMedium),
              ]),
            ),
          ),
        ),
      ),
    );
  }
}

class _Money extends StatelessWidget {
  const _Money({required this.label, required this.value, this.color});
  final String label, value;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    return Column(children: [
      Text(label, style: text.bodySmall),
      const SizedBox(height: 4),
      FittedBox(child: Text(value, style: text.titleSmall?.copyWith(color: color))),
    ]);
  }
}

class PartnerFormScreen extends StatefulWidget {
  const PartnerFormScreen({super.key});

  @override
  State<PartnerFormScreen> createState() => _PartnerFormScreenState();
}

class _PartnerFormScreenState extends State<PartnerFormScreen> {
  final _form = GlobalKey<FormState>();
  final _ad = TextEditingController(), _tel = TextEditingController(), _mail = TextEditingController();
  final _sehir = TextEditingController(), _vkn = TextEditingController();
  bool _sirket = true, _busy = false;

  Future<void> _save() async {
    if (!_form.currentState!.validate()) return;
    setState(() => _busy = true);
    final api = context.read<AppState>().api;
    final r = await runAction(
      context,
      () async => Map<String, dynamic>.from(await api.mobil('cari_olustur', {
        'ad': _ad.text.trim(),
        'sirket': _sirket,
        'telefon': _tel.text.trim(),
        'email': _mail.text.trim(),
        'sehir': _sehir.text.trim(),
        'vergi_no': _vkn.text.trim(),
      })),
      success: 'Cari oluşturuldu',
    );
    if (!mounted) return;
    setState(() => _busy = false);
    if (r != null) Navigator.pop(context, r);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Yeni cari')),
      bottomNavigationBar: BottomActionBar(children: [
        FilledButton(onPressed: _busy ? null : _save, child: const Text('Kaydet')),
      ]),
      body: Form(
        key: _form,
        child: ContentWidth(
          child: ListView(padding: const EdgeInsets.all(Gap.lg), children: [
            SegmentedButton<bool>(
              segments: const [
                ButtonSegment(value: true, label: Text('Şirket'), icon: Icon(Icons.business_rounded)),
                ButtonSegment(value: false, label: Text('Kişi'), icon: Icon(Icons.person_rounded)),
              ],
              selected: {_sirket},
              onSelectionChanged: (s) => setState(() => _sirket = s.first),
            ),
            const SizedBox(height: Gap.lg),
            TextFormField(
              controller: _ad,
              textCapitalization: TextCapitalization.words,
              decoration: InputDecoration(labelText: _sirket ? 'Unvan *' : 'Ad soyad *'),
              validator: (v) => (v ?? '').trim().isEmpty ? 'Ad gerekli' : null,
            ),
            const SizedBox(height: Gap.md),
            TextFormField(controller: _tel, keyboardType: TextInputType.phone, decoration: const InputDecoration(labelText: 'Telefon')),
            const SizedBox(height: Gap.md),
            TextFormField(
              controller: _mail,
              keyboardType: TextInputType.emailAddress,
              decoration: const InputDecoration(labelText: 'E-posta'),
              validator: (v) => (v ?? '').isNotEmpty && !v!.contains('@') ? 'Geçerli bir e-posta girin' : null,
            ),
            const SizedBox(height: Gap.md),
            TextFormField(controller: _sehir, decoration: const InputDecoration(labelText: 'Şehir')),
            const SizedBox(height: Gap.md),
            TextFormField(
              controller: _vkn,
              keyboardType: TextInputType.number,
              decoration: InputDecoration(labelText: _sirket ? 'Vergi kimlik no' : 'TC kimlik no'),
            ),
          ]),
        ),
      ),
    );
  }
}
