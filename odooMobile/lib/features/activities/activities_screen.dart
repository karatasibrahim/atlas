import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/format.dart';
import '../../core/session.dart';
import '../../core/theme.dart';
import '../../widgets/common.dart';
import '../approvals/approvals_screen.dart';
import '../crm/crm.dart';
import '../partners/partners.dart';
import '../sales/sales.dart';

IconData activityIcon(Map a) {
  final t = '${a['tur']} ${a['ikon']}'.toLowerCase();
  if (t.contains('phone') || t.contains('ara') || t.contains('call')) return Icons.call_rounded;
  if (t.contains('mail') || t.contains('e-posta') || t.contains('envelope')) return Icons.mail_rounded;
  if (t.contains('meeting') || t.contains('toplantı') || t.contains('users')) return Icons.groups_rounded;
  if (t.contains('upload') || t.contains('belge') || t.contains('document')) return Icons.upload_file_rounded;
  if (t.contains('onay') || t.contains('check')) return Icons.verified_rounded;
  return Icons.task_alt_rounded;
}

(String, Tone) activityState(String s) => switch (s) {
      'overdue' => ('Gecikmiş', Tone.danger),
      'today' => ('Bugün', Tone.warning),
      _ => ('Planlandı', Tone.success),
    };

/// İlgili kaydı mobilde açabiliyorsa açar.
void openRecord(BuildContext context, String? model, int? id) {
  if (model == null || id == null) return;
  final Widget? page = switch (model) {
    'crm.lead' => LeadDetailScreen(leadId: id),
    'sale.order' => SaleDetailScreen(orderId: id),
    'res.partner' => PartnerDetailScreen(partnerId: id),
    'atlas.onay.talep' => ApprovalDetailScreen(kaynak: 'onay', id: id),
    'hr.expense' => ApprovalDetailScreen(kaynak: 'masraf', id: id),
    'hr.leave' => ApprovalDetailScreen(kaynak: 'izin', id: id),
    _ => null,
  };
  if (page != null) Navigator.push(context, MaterialPageRoute(builder: (_) => page));
}

bool canOpenRecord(String? model) =>
    const {'crm.lead', 'sale.order', 'res.partner', 'atlas.onay.talep', 'hr.expense', 'hr.leave'}.contains(model);

Future<bool> completeActivity(BuildContext context, Map a) async {
  final fb = await promptText(context, title: 'Aktiviteyi tamamla', hint: 'Geri bildirim (isteğe bağlı)', ok: 'Tamamlandı');
  if (fb == null || !context.mounted) return false;
  final r = await runAction(context, () => context.read<AppState>().api.mobil('aktivite_tamamla', {'activity_id': a['id'], 'geri_bildirim': fb}),
      success: 'Aktivite tamamlandı');
  if (r != null && context.mounted) context.read<AppState>().refreshBadges();
  return r != null;
}

class ActivityTile extends StatelessWidget {
  const ActivityTile({super.key, required this.activity, required this.onDone});
  final Map activity;
  final VoidCallback onDone;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    final scheme = Theme.of(context).colorScheme;
    final (label, tone) = activityState(activity['durum'] ?? '');
    final (fg, bg) = StatusChip.colors(context, tone);
    return AppCard(
      padding: const EdgeInsets.all(Gap.md),
      onTap: canOpenRecord(activity['model']) ? () => openRecord(context, activity['model'], activity['res_id']) : null,
      child: Row(children: [
        Container(
          width: 44,
          height: 44,
          decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(12)),
          child: Icon(activityIcon(activity), color: fg, size: 22),
        ),
        const SizedBox(width: Gap.md),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(activity['baslik'], style: text.titleSmall, maxLines: 1, overflow: TextOverflow.ellipsis),
            Text(activity['kayit'] ?? '', style: text.bodySmall, maxLines: 1, overflow: TextOverflow.ellipsis),
            const SizedBox(height: 4),
            Row(children: [
              StatusChip(label, tone: tone),
              const SizedBox(width: Gap.sm),
              Text(Fmt.relative(activity['tarih']), style: text.bodySmall),
            ]),
          ]),
        ),
        IconButton(
          tooltip: 'Tamamla',
          onPressed: onDone,
          icon: Icon(Icons.check_circle_outline_rounded, color: scheme.primary),
        ),
      ]),
    );
  }
}

class ActivitiesScreen extends StatefulWidget {
  const ActivitiesScreen({super.key});

  @override
  State<ActivitiesScreen> createState() => _ActivitiesScreenState();
}

class _ActivitiesScreenState extends State<ActivitiesScreen> {
  final _key = GlobalKey<DataViewState<List>>();

  @override
  Widget build(BuildContext context) {
    final api = context.read<AppState>().api;
    return Scaffold(
      appBar: AppBar(title: const Text('Aktivitelerim')),
      body: DataView<List>(
        key: _key,
        load: () async => (await api.mobil('aktiviteler', {'limit': 200})) as List,
        builder: (context, items, _) {
          if (items.isEmpty) {
            return const EmptyState(icon: Icons.event_available_rounded, title: 'Planlanmış aktivite yok', message: 'Tüm işleriniz tamam.');
          }
          final groups = <String, List>{'overdue': [], 'today': [], 'planned': []};
          for (final a in items) {
            groups[groups.containsKey(a['durum']) ? a['durum'] : 'planned']!.add(a);
          }
          const titles = {'overdue': 'Gecikmiş', 'today': 'Bugün', 'planned': 'Yaklaşan'};
          return ListView(padding: const EdgeInsets.fromLTRB(Gap.lg, 0, Gap.lg, Gap.xxl), children: [
            for (final g in groups.entries)
              if (g.value.isNotEmpty) ...[
                SectionHeader('${titles[g.key]} (${g.value.length})'),
                for (final a in g.value)
                  Padding(
                    padding: const EdgeInsets.only(bottom: Gap.sm),
                    child: ActivityTile(
                      activity: a,
                      onDone: () async {
                        if (await completeActivity(context, a)) _key.currentState?.reload();
                      },
                    ),
                  ),
              ],
          ]);
        },
      ),
    );
  }
}
