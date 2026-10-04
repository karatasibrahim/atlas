import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:provider/provider.dart';

import '../../core/session.dart';
import '../../core/theme.dart';
import '../activities/activities_screen.dart';
import '../approvals/approvals_screen.dart';
import '../crm/crm.dart';
import '../hr/hr.dart';
import '../inventory/doc_list.dart';
import '../inventory/inventory_hub.dart';
import '../partners/partners.dart';
import '../products/product_detail.dart';
import '../sales/sales.dart';

class AppEntry {
  const AppEntry(this.title, this.icon, this.colors, this.module, this.builder);
  final String title;
  final IconData icon;
  final List<Color> colors;
  final String? module;
  final WidgetBuilder builder;
}

/// Odoo ana ekranı gibi renkli uygulama simgeleri; kullanıcının yetkisine göre süzülür.
final appEntries = <AppEntry>[
  AppEntry('Satış', Icons.point_of_sale_rounded, const [Color(0xFFE76F51), Color(0xFFF4A261)], 'satis', (_) => const SalesListScreen()),
  AppEntry('CRM', Icons.handshake_rounded, const [Color(0xFF017E84), Color(0xFF2EC4B6)], 'crm', (_) => const CrmPipelineScreen()),
  AppEntry('Cariler', Icons.contacts_rounded, const [Color(0xFF714B67), Color(0xFFB07AA1)], 'cari', (_) => const PartnerListScreen()),
  AppEntry('Ürünler', Icons.inventory_2_rounded, const [Color(0xFF3A86FF), Color(0xFF7FB2FF)], null, (_) => const ProductListScreen()),
  AppEntry('Depo', Icons.warehouse_rounded, const [Color(0xFF7C3AED), Color(0xFFA78BFA)], 'depo', (_) => const InventoryHub()),
  AppEntry('Mal Kabul', Icons.move_to_inbox_rounded, const [Color(0xFF0E7490), Color(0xFF22D3EE)], 'depo',
      (_) => const DocListScreen(islem: 'mal_kabul', title: 'Mal Kabul')),
  AppEntry('Sevkiyat', Icons.local_shipping_rounded, const [Color(0xFF6D28D9), Color(0xFF8B5CF6)], 'depo',
      (_) => const DocListScreen(islem: 'sevkiyat', title: 'Sevkiyat')),
  AppEntry('Stok Sayımı', Icons.fact_check_rounded, const [Color(0xFF15803D), Color(0xFF4ADE80)], 'depo',
      (_) => const DocListScreen(islem: 'sayim', title: 'Stok Sayımı')),
  AppEntry('Üretim', Icons.precision_manufacturing_rounded, const [Color(0xFFB45309), Color(0xFFF59E0B)], 'uretim',
      (_) => const DocListScreen(islem: 'uretim', title: 'Üretim')),
  AppEntry('Onaylar', Icons.verified_rounded, const [Color(0xFF0F766E), Color(0xFF14B8A6)], 'onay',
      (_) => const ApprovalsScreen()),
  AppEntry('Giriş/Çıkış', Icons.fingerprint_rounded, const [Color(0xFF1D4ED8), Color(0xFF60A5FA)], 'devam', (_) => const AttendanceScreen()),
  AppEntry('Masraflar', Icons.receipt_long_rounded, const [Color(0xFFBE185D), Color(0xFFF472B6)], 'masraf', (_) => const ExpensesScreen()),
  AppEntry('İzinler', Icons.beach_access_rounded, const [Color(0xFF0369A1), Color(0xFF38BDF8)], 'izin', (_) => const LeavesScreen()),
  AppEntry('Aktiviteler', Icons.event_note_rounded, const [Color(0xFF4D7C0F), Color(0xFFA3E635)], null, (_) => const ActivitiesScreen()),
];

class AppsScreen extends StatelessWidget {
  const AppsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final apps = appEntries.where((a) => a.module == null || state.can(a.module!)).toList();
    final width = MediaQuery.of(context).size.width;
    final columns = width > 900 ? 6 : (width > 600 ? 5 : (width < 360 ? 3 : 4));
    return Scaffold(
      appBar: AppBar(title: const Text('Uygulamalar')),
      body: GridView.builder(
        padding: const EdgeInsets.fromLTRB(Gap.lg, Gap.md, Gap.lg, Gap.xxl),
        gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(crossAxisCount: columns, mainAxisSpacing: Gap.lg, crossAxisSpacing: Gap.sm, childAspectRatio: .78),
        itemCount: apps.length,
        itemBuilder: (context, i) => AppIcon(entry: apps[i])
            .animate()
            .fadeIn(delay: (30 * i).ms, duration: 250.ms)
            .scale(begin: const Offset(.92, .92), curve: Curves.easeOutBack, duration: 300.ms),
      ),
    );
  }
}

class AppIcon extends StatelessWidget {
  const AppIcon({super.key, required this.entry, this.size = 64});
  final AppEntry entry;
  final double size;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: entry.title,
      child: InkWell(
        borderRadius: BorderRadius.circular(Gap.radius),
        onTap: () => Navigator.push(context, MaterialPageRoute(builder: entry.builder)),
        child: Column(children: [
          Container(
            width: size,
            height: size,
            decoration: BoxDecoration(
              gradient: LinearGradient(colors: entry.colors, begin: Alignment.topLeft, end: Alignment.bottomRight),
              borderRadius: BorderRadius.circular(size * .28),
              boxShadow: [BoxShadow(color: entry.colors.first.withValues(alpha: .3), blurRadius: 12, offset: const Offset(0, 6))],
            ),
            child: Icon(entry.icon, color: Colors.white, size: size * .48),
          ),
          const SizedBox(height: Gap.sm),
          Text(entry.title,
              textAlign: TextAlign.center,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: Theme.of(context).textTheme.labelMedium),
        ]),
      ),
    );
  }
}
