import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:provider/provider.dart';

import '../../core/format.dart';
import '../../core/session.dart';
import '../../core/theme.dart';
import '../../widgets/brand.dart';
import '../../widgets/common.dart';
import '../activities/activities_screen.dart';
import '../crm/crm.dart';
import '../hr/hr.dart';
import '../inventory/doc_list.dart';
import '../products/product_detail.dart';
import '../sales/sales.dart';
import '../shell/home_shell.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  final _key = GlobalKey<DataViewState<Map<String, dynamic>>>();

  String _greeting() {
    final h = DateTime.now().hour;
    if (h < 6) return 'İyi geceler';
    if (h < 12) return 'Günaydın';
    if (h < 18) return 'İyi günler';
    return 'İyi akşamlar';
  }

  Future<void> _go(Widget page) async {
    await Navigator.push(context, MaterialPageRoute(builder: (_) => page));
    _key.currentState?.reload();
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final api = state.api;
    return Scaffold(
      body: DataView<Map<String, dynamic>>(
        key: _key,
        load: () async {
          final r = Map<String, dynamic>.from(await api.mobil('ozet'));
          state.refreshBadges();
          return r;
        },
        skeleton: const SkeletonList(header: true, count: 5),
        builder: (context, d, reload) => CustomScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          slivers: [
            SliverToBoxAdapter(child: _header(state)),
            SliverToBoxAdapter(
              child: ContentWidth(
                max: 900,
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(Gap.lg, Gap.lg, Gap.lg, Gap.xxl),
                  child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: _sections(context, d, state)
                      .animate(interval: 50.ms)
                      .fadeIn(duration: 300.ms)
                      .slideY(begin: .04, curve: Curves.easeOutCubic)),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _header(AppState state) {
    final text = Theme.of(context).textTheme;
    final name = (state.profile['ad'] ?? '').toString().split(' ').first;
    return HeroBackground(
      child: SafeArea(
        bottom: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(Gap.xl, Gap.lg, Gap.lg, Gap.xl),
          child: Row(children: [
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(Fmt.fullDate(DateTime.now()), style: text.bodyMedium?.copyWith(color: Colors.white70)),
                const SizedBox(height: 4),
                Text('${_greeting()}, $name', style: text.headlineSmall?.copyWith(color: Colors.white)),
                const SizedBox(height: 2),
                Text(state.profile['sirket'] ?? '', style: text.bodyMedium?.copyWith(color: Colors.white70)),
              ]),
            ),
            Semantics(
              button: true,
              label: 'Profil',
              child: InkWell(
                customBorder: const CircleBorder(),
                onTap: () => HomeShell.switchTab(context, 4),
                child: Container(
                  padding: const EdgeInsets.all(2),
                  decoration: BoxDecoration(
                      shape: BoxShape.circle, color: Colors.white, border: Border.all(color: Colors.white54, width: 2)),
                  child: Avatar(name: state.profile['ad'] ?? '?', image: state.profile['avatar'], size: 48),
                ),
              ),
            ),
          ]),
        ),
      ),
    );
  }

  List<Widget> _sections(BuildContext context, Map<String, dynamic> d, AppState state) {
    final sym = (d['para_simge'] ?? '₺').toString();
    final satis = d['satis'] as Map?;
    final tahsilat = d['tahsilat'] as Map?;
    final depo = d['depo'] as Map?;
    final crm = d['crm'] as Map?;
    final aktiviteler = (d['aktiviteler'] as List?) ?? [];
    final c = AtlasColors.of(context);
    final kpis = <Widget>[
      if (satis != null)
        KpiCard(
          icon: Icons.trending_up_rounded,
          label: 'Bu ay satış',
          value: Fmt.compactMoney(satis['bu_ay'], sym),
          trend: satis['degisim'] == null ? null : Fmt.d(satis['degisim']),
          caption: satis['degisim'] == null ? 'Bugün ${Fmt.compactMoney(satis['bugun'], sym)}' : 'geçen ayın aynı dönemine göre',
          onTap: () => _go(const SalesListScreen()),
        ),
      if (tahsilat != null)
        KpiCard(
          icon: Icons.account_balance_wallet_rounded,
          label: 'Açık alacak',
          value: Fmt.compactMoney(tahsilat['acik'], sym),
          caption: Fmt.d(tahsilat['vadesi_gecen']) > 0 ? '${Fmt.compactMoney(tahsilat['vadesi_gecen'], sym)} vadesi geçti' : 'Vadesi geçen yok',
          captionColor: Fmt.d(tahsilat['vadesi_gecen']) > 0 ? c.danger : c.success,
        ),
      KpiCard(
        icon: Icons.verified_rounded,
        label: 'Onayımı bekleyen',
        value: '${d['onay_bekleyen'] ?? 0}',
        caption: (d['onay_bekleyen'] ?? 0) == 0 ? 'Bekleyen yok' : 'Karar bekliyor',
        captionColor: (d['onay_bekleyen'] ?? 0) == 0 ? c.success : c.warning,
        onTap: () => HomeShell.switchTab(context, 3),
      ),
      if (crm != null)
        KpiCard(
          icon: Icons.handshake_rounded,
          label: 'Fırsatlarım',
          value: Fmt.compactMoney(crm['beklenen'], sym),
          caption: '${crm['acik']} açık fırsat',
          onTap: () => _go(const CrmPipelineScreen()),
        )
      else if (satis != null)
        KpiCard(
          icon: Icons.request_quote_rounded,
          label: 'Açık teklif',
          value: '${satis['acik_teklif']}',
          caption: '${satis['faturalanacak']} sipariş faturalanacak',
          onTap: () => _go(const SalesListScreen()),
        ),
    ];

    return [
      if (d['devam'] is Map) ...[
        AttendanceCard(data: d['devam']),
        const SizedBox(height: Gap.lg),
      ],
      _QuickActions(state: state, onGo: _go),
      const SizedBox(height: Gap.lg),
      LayoutBuilder(builder: (context, cons) {
        final cols = cons.maxWidth > 640 ? 4 : 2;
        final w = (cons.maxWidth - Gap.md * (cols - 1)) / cols;
        return Wrap(spacing: Gap.md, runSpacing: Gap.md, children: [for (final k in kpis) SizedBox(width: w, child: k)]);
      }),
      if (satis != null) ...[
        const SectionHeader('Son 7 gün satış'),
        AppCard(child: SizedBox(height: 180, child: SalesChart(series: (satis['seri'] as List).cast<Map>(), symbol: sym))),
      ],
      if (depo != null) ...[
        const SectionHeader('Depo iş listesi'),
        Row(children: [
          Expanded(child: _DepotCounter(label: 'Mal kabul', count: depo['mal_kabul'], icon: Icons.move_to_inbox_rounded,
              onTap: () => _go(const DocListScreen(islem: 'mal_kabul', title: 'Mal Kabul')))),
          const SizedBox(width: Gap.md),
          Expanded(child: _DepotCounter(label: 'Sevkiyat', count: depo['sevkiyat'], icon: Icons.local_shipping_rounded,
              onTap: () => _go(const DocListScreen(islem: 'sevkiyat', title: 'Sevkiyat')))),
          const SizedBox(width: Gap.md),
          Expanded(child: _DepotCounter(label: 'Üretim', count: depo['uretim'], icon: Icons.precision_manufacturing_rounded,
              onTap: state.can('uretim') ? () => _go(const DocListScreen(islem: 'uretim', title: 'Üretim')) : null)),
        ]),
      ],
      SectionHeader(
        'Aktivitelerim${(d['aktivite_sayisi'] ?? 0) > 0 ? ' • ${d['aktivite_sayisi']} bugün/gecikmiş' : ''}',
        action: 'Tümü',
        onAction: () => _go(const ActivitiesScreen()),
      ),
      if (aktiviteler.isEmpty)
        AppCard(
          child: Row(children: [
            Icon(Icons.event_available_rounded, color: c.success),
            const SizedBox(width: Gap.md),
            const Expanded(child: Text('Planlanmış aktivite yok. Harika!')),
          ]),
        ),
      for (final a in aktiviteler)
        Padding(
          padding: const EdgeInsets.only(bottom: Gap.sm),
          child: ActivityTile(
            activity: a,
            onDone: () async {
              if (await completeActivity(context, a)) _key.currentState?.reload();
            },
          ),
        ),
    ];
  }
}

class KpiCard extends StatelessWidget {
  const KpiCard({super.key, required this.icon, required this.label, required this.value, this.caption, this.captionColor, this.trend, this.onTap});
  final IconData icon;
  final String label, value;
  final String? caption;
  final Color? captionColor;
  final double? trend;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    final scheme = Theme.of(context).colorScheme;
    final c = AtlasColors.of(context);
    return AppCard(
      onTap: onTap,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Container(
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(color: scheme.primary.withValues(alpha: .1), borderRadius: BorderRadius.circular(10)),
            child: Icon(icon, size: 20, color: scheme.primary),
          ),
          const Spacer(),
          if (trend != null)
            StatusChip(
              '${trend! >= 0 ? '+' : '−'}${Fmt.percent(trend!.abs())}',
              tone: trend! >= 0 ? Tone.success : Tone.danger,
              icon: trend! >= 0 ? Icons.arrow_upward_rounded : Icons.arrow_downward_rounded,
            ),
        ]),
        const SizedBox(height: Gap.md),
        Text(label, style: text.bodySmall),
        const SizedBox(height: 2),
        FittedBox(fit: BoxFit.scaleDown, alignment: Alignment.centerLeft, child: Text(value, style: text.headlineSmall)),
        if (caption != null) ...[
          const SizedBox(height: 2),
          Text(caption!, style: text.bodySmall?.copyWith(color: captionColor ?? c.muted), maxLines: 1, overflow: TextOverflow.ellipsis),
        ],
      ]),
    );
  }
}

class SalesChart extends StatelessWidget {
  const SalesChart({super.key, required this.series, required this.symbol});
  final List<Map> series;
  final String symbol;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final text = Theme.of(context).textTheme;
    final max = series.fold<double>(0, (a, s) => Fmt.d(s['tutar']) > a ? Fmt.d(s['tutar']) : a);
    return Semantics(
      label: 'Son yedi günün günlük satış grafiği',
      child: BarChart(
        BarChartData(
          maxY: max == 0 ? 1 : max * 1.15,
          gridData: FlGridData(
            show: true,
            drawVerticalLine: false,
            horizontalInterval: max == 0 ? 1 : max / 3,
            getDrawingHorizontalLine: (_) => FlLine(color: scheme.outlineVariant, strokeWidth: 1, dashArray: [4, 4]),
          ),
          borderData: FlBorderData(show: false),
          titlesData: FlTitlesData(
            topTitles: const AxisTitles(),
            rightTitles: const AxisTitles(),
            leftTitles: const AxisTitles(),
            bottomTitles: AxisTitles(
              sideTitles: SideTitles(
                showTitles: true,
                reservedSize: 26,
                getTitlesWidget: (v, _) => Padding(
                  padding: const EdgeInsets.only(top: 6),
                  child: Text(Fmt.weekday(series[v.toInt()]['tarih']), style: text.bodySmall),
                ),
              ),
            ),
          ),
          barTouchData: BarTouchData(
            touchTooltipData: BarTouchTooltipData(
              getTooltipColor: (_) => scheme.inverseSurface,
              getTooltipItem: (group, _, rod, _) => BarTooltipItem(
                '${Fmt.date(series[group.x]['tarih'])}\n${Fmt.money(rod.toY, symbol)}',
                TextStyle(color: scheme.onInverseSurface, fontWeight: FontWeight.w600),
              ),
            ),
          ),
          barGroups: [
            for (var i = 0; i < series.length; i++)
              BarChartGroupData(x: i, barRods: [
                BarChartRodData(
                  toY: Fmt.d(series[i]['tutar']),
                  width: 22,
                  borderRadius: const BorderRadius.vertical(top: Radius.circular(6)),
                  gradient: LinearGradient(
                    colors: i == series.length - 1 ? [scheme.secondary, scheme.primary] : [scheme.primary.withValues(alpha: .45), scheme.primary.withValues(alpha: .8)],
                    begin: Alignment.bottomCenter,
                    end: Alignment.topCenter,
                  ),
                ),
              ]),
          ],
        ),
        duration: const Duration(milliseconds: 400),
      ),
    );
  }
}

class _DepotCounter extends StatelessWidget {
  const _DepotCounter({required this.label, required this.count, required this.icon, this.onTap});
  final String label;
  final dynamic count;
  final IconData icon;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    final scheme = Theme.of(context).colorScheme;
    return AppCard(
      onTap: onTap,
      padding: const EdgeInsets.symmetric(vertical: Gap.lg, horizontal: Gap.sm),
      child: Column(children: [
        Icon(icon, color: scheme.primary),
        const SizedBox(height: Gap.sm),
        Text('${count ?? 0}', style: text.headlineSmall),
        Text(label, style: text.bodySmall, maxLines: 1, overflow: TextOverflow.ellipsis),
      ]),
    );
  }
}

class _QuickActions extends StatelessWidget {
  const _QuickActions({required this.state, required this.onGo});
  final AppState state;
  final Future<void> Function(Widget) onGo;

  @override
  Widget build(BuildContext context) {
    final actions = [
      if (state.can('satis')) (Icons.request_quote_rounded, 'Yeni teklif', () => onGo(const SaleCreateScreen())),
      if (state.can('masraf')) (Icons.add_a_photo_rounded, 'Masraf gir', () => onGo(const ExpenseFormScreen())),
      (Icons.manage_search_rounded, 'Ürün sorgula', () => onGo(const ProductListScreen())),
      if (state.can('crm')) (Icons.add_business_rounded, 'Yeni fırsat', () => onGo(const LeadFormScreen())),
      if (state.can('izin')) (Icons.beach_access_rounded, 'İzin iste', () => onGo(const LeaveFormScreen())),
    ];
    final text = Theme.of(context).textTheme;
    final scheme = Theme.of(context).colorScheme;
    return SizedBox(
      height: 92,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        itemCount: actions.length,
        separatorBuilder: (_, _) => const SizedBox(width: Gap.sm),
        itemBuilder: (context, i) {
          final (icon, label, onTap) = actions[i];
          return SizedBox(
            width: 92,
            child: AppCard(
              onTap: onTap,
              padding: const EdgeInsets.all(Gap.sm),
              child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
                Icon(icon, color: scheme.primary, size: 26),
                const SizedBox(height: 6),
                Text(label, style: text.labelSmall, textAlign: TextAlign.center, maxLines: 2),
              ]),
            ),
          );
        },
      ),
    );
  }
}
