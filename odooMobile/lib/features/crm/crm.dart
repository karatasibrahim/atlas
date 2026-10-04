import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/api.dart';
import '../../core/format.dart';
import '../../core/session.dart';
import '../../core/theme.dart';
import '../../widgets/common.dart';
import '../partners/partners.dart';
import '../sales/sales.dart';

/// Fırsat hattı: her aşama bir sekme; kartlar aşamalar arası taşınabilir.
class CrmPipelineScreen extends StatefulWidget {
  const CrmPipelineScreen({super.key});

  @override
  State<CrmPipelineScreen> createState() => _CrmPipelineScreenState();
}

class _CrmPipelineScreenState extends State<CrmPipelineScreen> {
  bool _mine = true;
  String _search = '';
  final _key = GlobalKey<DataViewState<List>>();

  OdooClient get _api => context.read<AppState>().api;

  Future<void> _create() async {
    final r = await Navigator.push(context, MaterialPageRoute(builder: (_) => const LeadFormScreen()));
    if (r != null) _key.currentState?.reload();
  }

  @override
  Widget build(BuildContext context) {
    return DataView<List>(
      key: _key,
      refreshable: false,
      skeleton: Scaffold(appBar: AppBar(title: const Text('CRM')), body: const SkeletonList()),
      load: () async => (await _api.mobil('crm_hat', {'arama': _search, 'benim': _mine})) as List,
      builder: (context, stages, reload) {
        final visible = stages.where((s) => s['katlanir'] != true || (s['firsatlar'] as List).isNotEmpty).toList();
        final sym = context.read<AppState>().currencySymbol;
        return DefaultTabController(
          length: visible.length,
          child: Scaffold(
            appBar: AppBar(
              title: const Text('CRM'),
              actions: [
                IconButton(
                  tooltip: _mine ? 'Tüm fırsatları göster' : 'Yalnızca benimkiler',
                  icon: Icon(_mine ? Icons.person_rounded : Icons.groups_rounded),
                  onPressed: () {
                    setState(() => _mine = !_mine);
                    reload();
                  },
                ),
              ],
              bottom: PreferredSize(
                preferredSize: const Size.fromHeight(112),
                child: Column(children: [
                  Padding(
                    padding: const EdgeInsets.fromLTRB(Gap.lg, 0, Gap.lg, Gap.sm),
                    child: SearchField(hint: 'Fırsat veya müşteri ara', onChanged: (v) {
                      _search = v;
                      reload();
                    }),
                  ),
                  TabBar(
                    isScrollable: true,
                    tabAlignment: TabAlignment.start,
                    tabs: [
                      for (final s in visible) Tab(text: '${s['ad']}  ${(s['firsatlar'] as List).length}'),
                    ],
                  ),
                ]),
              ),
            ),
            floatingActionButton: FloatingActionButton.extended(
                onPressed: _create, icon: const Icon(Icons.add_rounded), label: const Text('Yeni fırsat')),
            body: TabBarView(children: [
              for (final s in visible)
                RefreshIndicator(
                  onRefresh: reload,
                  child: (s['firsatlar'] as List).isEmpty
                      ? const EmptyState(icon: Icons.filter_alt_off_rounded, title: 'Bu aşamada fırsat yok')
                      : ListView(padding: const EdgeInsets.fromLTRB(Gap.lg, Gap.md, Gap.lg, 96), children: [
                          Padding(
                            padding: const EdgeInsets.only(bottom: Gap.md, left: 4),
                            child: Text('Beklenen gelir: ${Fmt.money(s['toplam'], sym)}', style: Theme.of(context).textTheme.labelLarge),
                          ),
                          for (final l in s['firsatlar'] as List)
                            Padding(
                              padding: const EdgeInsets.only(bottom: Gap.sm),
                              child: LeadCard(
                                lead: l,
                                onTap: () async {
                                  await Navigator.push(context, MaterialPageRoute(builder: (_) => LeadDetailScreen(leadId: l['id'])));
                                  reload();
                                },
                              ),
                            ),
                        ]),
                ),
            ]),
          ),
        );
      },
    );
  }
}

class LeadCard extends StatelessWidget {
  const LeadCard({super.key, required this.lead, this.onTap});
  final Map lead;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    final scheme = Theme.of(context).colorScheme;
    final stars = (lead['oncelik'] ?? 0) as int;
    return AppCard(
      onTap: onTap,
      padding: const EdgeInsets.all(Gap.md),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(child: Text(lead['ad'], style: text.titleSmall, maxLines: 2, overflow: TextOverflow.ellipsis)),
          if (stars > 0)
            Row(mainAxisSize: MainAxisSize.min, children: [
              for (var i = 0; i < stars; i++) const Icon(Icons.star_rounded, size: 16, color: Color(0xFFF59E0B)),
            ]),
        ]),
        if ((lead['cari'] ?? '') != '') Text(lead['cari'], style: text.bodyMedium),
        const SizedBox(height: Gap.sm),
        Row(children: [
          Text(Fmt.money(lead['gelir'], lead['para_simge'] ?? '₺'), style: text.titleSmall?.copyWith(color: scheme.primary)),
          const SizedBox(width: Gap.sm),
          StatusChip(Fmt.percent(lead['olasilik']), tone: Tone.info),
          const Spacer(),
          if ((lead['kapanis'] ?? false) != false)
            Text(Fmt.dateShort(lead['kapanis']), style: text.bodySmall),
        ]),
        if ((lead['etiketler'] as List?)?.isNotEmpty ?? false) ...[
          const SizedBox(height: Gap.sm),
          Wrap(spacing: 6, runSpacing: 6, children: [for (final e in lead['etiketler']) StatusChip(e)]),
        ],
      ]),
    );
  }
}

class LeadDetailScreen extends StatefulWidget {
  const LeadDetailScreen({super.key, required this.leadId});
  final int leadId;

  @override
  State<LeadDetailScreen> createState() => _LeadDetailScreenState();
}

class _LeadDetailScreenState extends State<LeadDetailScreen> {
  final _key = GlobalKey<DataViewState<List>>();
  OdooClient get _api => context.read<AppState>().api;

  Future<void> _setStage(int stageId) async {
    final r = await runAction(context, () => _api.mobil('crm_asama', {'lead_id': widget.leadId, 'asama_id': stageId}),
        success: 'Aşama güncellendi');
    if (r != null) _key.currentState?.reload();
  }

  Future<void> _won() async {
    final r = await runAction(context, () => _api.mobil('crm_kazanildi', {'lead_id': widget.leadId}), success: 'Tebrikler! Fırsat kazanıldı');
    if (r != null) _key.currentState?.reload();
  }

  Future<void> _lost() async {
    final reasons = (await runAction(context, () => _api.mobil('crm_kayip_nedenleri'))) as List?;
    if (reasons == null || !mounted) return;
    final reason = await showModalBottomSheet<int>(
      context: context,
      builder: (ctx) => SafeArea(
        child: ListView(shrinkWrap: true, children: [
          Padding(padding: const EdgeInsets.fromLTRB(20, 0, 20, 8), child: Text('Kayıp nedeni', style: Theme.of(ctx).textTheme.titleLarge)),
          for (final r in reasons) ListTile(title: Text(r['ad']), onTap: () => Navigator.pop(ctx, r['id'] as int)),
          ListTile(title: const Text('Neden belirtmeden'), onTap: () => Navigator.pop(ctx, 0)),
        ]),
      ),
    );
    if (reason == null || !mounted) return;
    final r = await runAction(context, () => _api.mobil('crm_kaybedildi', {'lead_id': widget.leadId, 'neden_id': reason}),
        success: 'Fırsat kaybedildi olarak işaretlendi');
    if (r != null && mounted) Navigator.pop(context, true);
  }

  Future<void> _note() async {
    final note = await promptText(context, title: 'Not ekle', hint: 'Görüşme notu', required: true);
    if (note == null || !mounted) return;
    final r = await runAction(context, () => _api.mobil('not_ekle', {'model': 'crm.lead', 'res_id': widget.leadId, 'metin': note}),
        success: 'Not eklendi');
    if (r != null) _key.currentState?.reload();
  }

  @override
  Widget build(BuildContext context) {
    return DataView<List>(
      key: _key,
      refreshable: false,
      skeleton: Scaffold(appBar: AppBar(), body: const SkeletonList(header: true)),
      load: () async => [
        Map<String, dynamic>.from(await _api.mobil('crm_detay', {'lead_id': widget.leadId})),
        await _api.mobil('crm_asamalar'),
      ],
      builder: (context, data, reload) {
        final l = data[0] as Map<String, dynamic>;
        final stages = (data[1] as List).where((s) => s['katlanir'] != true || s['id'] == l['asama_id']).toList();
        final text = Theme.of(context).textTheme;
        final scheme = Theme.of(context).colorScheme;
        final mesajlar = (l['mesajlar'] as List?) ?? [];
        final teklifler = (l['teklifler'] as List?) ?? [];
        return Scaffold(
          appBar: AppBar(title: const Text('Fırsat'), actions: [
            IconButton(tooltip: 'Not ekle', onPressed: _note, icon: const Icon(Icons.edit_note_rounded)),
          ]),
          bottomNavigationBar: l['olasilik'] == 100
              ? null
              : BottomActionBar(children: [
                  OutlinedButton(onPressed: _lost, child: const Text('Kaybedildi')),
                  FilledButton(onPressed: _won, child: const Text('Kazanıldı')),
                ]),
          body: RefreshIndicator(
            onRefresh: reload,
            child: ContentWidth(
              child: ListView(padding: const EdgeInsets.all(Gap.lg), children: [
                Text(l['ad'], style: text.headlineSmall),
                if ((l['cari'] ?? '') != '') ...[
                  const SizedBox(height: 4),
                  InkWell(
                    onTap: l['cari_id'] == false
                        ? null
                        : () => Navigator.push(context, MaterialPageRoute(builder: (_) => PartnerDetailScreen(partnerId: l['cari_id']))),
                    child: Text(l['cari'], style: text.titleMedium?.copyWith(color: scheme.primary)),
                  ),
                ],
                const SizedBox(height: Gap.lg),
                Row(children: [
                  Expanded(
                    child: AppCard(
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Text('Beklenen gelir', style: text.bodySmall),
                        const SizedBox(height: 4),
                        FittedBox(child: Text(Fmt.money(l['gelir'], l['para_simge']), style: text.titleLarge)),
                      ]),
                    ),
                  ),
                  const SizedBox(width: Gap.md),
                  Expanded(
                    child: AppCard(
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Text('Olasılık', style: text.bodySmall),
                        const SizedBox(height: 4),
                        Text(Fmt.percent(l['olasilik']), style: text.titleLarge),
                      ]),
                    ),
                  ),
                ]),
                const SectionHeader('Aşama'),
                Wrap(spacing: Gap.sm, runSpacing: Gap.sm, children: [
                  for (final s in stages)
                    ChoiceChip(
                      label: Text(s['ad']),
                      selected: s['id'] == l['asama_id'],
                      onSelected: s['id'] == l['asama_id'] ? null : (_) => _setStage(s['id']),
                    ),
                ]),
                if ((l['telefon'] ?? '') != '' || (l['email'] ?? '') != '') ...[
                  const SectionHeader('İletişim'),
                  Row(children: [
                    if ((l['telefon'] ?? '') != '')
                      Expanded(
                        child: OutlinedButton.icon(
                          onPressed: () => launchUrl(Uri(scheme: 'tel', path: l['telefon'])),
                          icon: const Icon(Icons.call_rounded),
                          label: const Text('Ara'),
                        ),
                      ),
                    if ((l['telefon'] ?? '') != '' && (l['email'] ?? '') != '') const SizedBox(width: Gap.md),
                    if ((l['email'] ?? '') != '')
                      Expanded(
                        child: OutlinedButton.icon(
                          onPressed: () => launchUrl(Uri(scheme: 'mailto', path: l['email'])),
                          icon: const Icon(Icons.mail_rounded),
                          label: const Text('E-posta'),
                        ),
                      ),
                  ]),
                ],
                if ((l['aciklama'] ?? '') != '') ...[
                  const SectionHeader('Açıklama'),
                  AppCard(child: Text(l['aciklama'])),
                ],
                if (teklifler.isNotEmpty) ...[
                  const SectionHeader('Teklifler'),
                  for (final t in teklifler) Padding(padding: const EdgeInsets.only(bottom: Gap.sm), child: SaleTile(order: t)),
                ],
                if (mesajlar.isNotEmpty) ...[
                  const SectionHeader('Son notlar'),
                  for (final m in mesajlar)
                    Padding(
                      padding: const EdgeInsets.only(bottom: Gap.sm),
                      child: AppCard(
                        padding: const EdgeInsets.all(Gap.md),
                        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                          Row(children: [
                            Avatar(name: m['yazar'], size: 28),
                            const SizedBox(width: Gap.sm),
                            Expanded(child: Text(m['yazar'], style: text.labelLarge)),
                            Text(Fmt.relative(m['tarih']), style: text.bodySmall),
                          ]),
                          const SizedBox(height: Gap.sm),
                          Text(m['metin']),
                        ]),
                      ),
                    ),
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

class LeadFormScreen extends StatefulWidget {
  const LeadFormScreen({super.key});

  @override
  State<LeadFormScreen> createState() => _LeadFormScreenState();
}

class _LeadFormScreenState extends State<LeadFormScreen> {
  final _form = GlobalKey<FormState>();
  final _ad = TextEditingController(), _gelir = TextEditingController(), _tel = TextEditingController();
  final _mail = TextEditingController(), _aciklama = TextEditingController();
  Map? _partner;
  double _olasilik = 20;
  bool _busy = false;

  Future<void> _save() async {
    if (!_form.currentState!.validate()) return;
    setState(() => _busy = true);
    final r = await runAction(
      context,
      () => context.read<AppState>().api.mobil('crm_olustur', {
        'ad': _ad.text.trim(),
        'partner_id': _partner?['id'] ?? false,
        'gelir': double.tryParse(_gelir.text.replaceAll('.', '').replaceAll(',', '.')) ?? 0,
        'olasilik': _olasilik,
        'telefon': _tel.text.trim(),
        'email': _mail.text.trim(),
        'aciklama': _aciklama.text.trim(),
      }),
      success: 'Fırsat oluşturuldu',
    );
    if (!mounted) return;
    setState(() => _busy = false);
    if (r != null) Navigator.pop(context, r);
  }

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    return Scaffold(
      appBar: AppBar(title: const Text('Yeni fırsat')),
      bottomNavigationBar: BottomActionBar(children: [FilledButton(onPressed: _busy ? null : _save, child: const Text('Kaydet'))]),
      body: Form(
        key: _form,
        child: ContentWidth(
          child: ListView(padding: const EdgeInsets.all(Gap.lg), children: [
            TextFormField(
              controller: _ad,
              decoration: const InputDecoration(labelText: 'Fırsat adı *', hintText: 'Örn. 50 adet panel teklifi'),
              validator: (v) => (v ?? '').trim().isEmpty ? 'Fırsat adı gerekli' : null,
            ),
            const SizedBox(height: Gap.md),
            AppCard(
              padding: const EdgeInsets.all(Gap.md),
              onTap: () async {
                final p = await Navigator.push<Map>(context, MaterialPageRoute(builder: (_) => const PartnerListScreen(picker: true)));
                if (p != null) setState(() => _partner = p);
              },
              child: Row(children: [
                const Icon(Icons.business_rounded),
                const SizedBox(width: Gap.md),
                Expanded(child: Text(_partner?['ad'] ?? 'Müşteri seçin (isteğe bağlı)', style: text.bodyLarge)),
                const Icon(Icons.chevron_right_rounded),
              ]),
            ),
            const SizedBox(height: Gap.md),
            TextFormField(
              controller: _gelir,
              keyboardType: const TextInputType.numberWithOptions(decimal: true),
              decoration: InputDecoration(labelText: 'Beklenen gelir', suffixText: context.read<AppState>().currencySymbol),
            ),
            const SizedBox(height: Gap.lg),
            Text('Olasılık: ${Fmt.percent(_olasilik)}', style: text.labelLarge),
            Slider(value: _olasilik, max: 100, divisions: 20, label: Fmt.percent(_olasilik), onChanged: (v) => setState(() => _olasilik = v)),
            const SizedBox(height: Gap.sm),
            TextFormField(controller: _tel, keyboardType: TextInputType.phone, decoration: const InputDecoration(labelText: 'Telefon')),
            const SizedBox(height: Gap.md),
            TextFormField(controller: _mail, keyboardType: TextInputType.emailAddress, decoration: const InputDecoration(labelText: 'E-posta')),
            const SizedBox(height: Gap.md),
            TextFormField(controller: _aciklama, minLines: 3, maxLines: 6, decoration: const InputDecoration(labelText: 'Açıklama')),
          ]),
        ),
      ),
    );
  }
}
