import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../../core/session.dart';
import '../approvals/approvals_screen.dart';
import '../apps/apps_screen.dart';
import '../dashboard/dashboard_screen.dart';
import '../profile/profile_screen.dart';
import '../scan/scan_lookup.dart';

/// Ana iskelet: alt gezinme (Ana Sayfa, Uygulamalar, Tara, Onaylar, Profil).
class HomeShell extends StatefulWidget {
  const HomeShell({super.key});

  static void switchTab(BuildContext context, int index) =>
      context.findAncestorStateOfType<_HomeShellState>()?._select(index);

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> with WidgetsBindingObserver {
  int _index = 0;
  final _pages = const [DashboardScreen(), AppsScreen(), SizedBox.shrink(), ApprovalsScreen(), ProfileScreen()];

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) context.read<AppState>().refreshBadges();
  }

  void _select(int i) {
    if (i == 2) {
      HapticFeedback.selectionClick();
      openScanLookup(context);
      return;
    }
    setState(() => _index = i);
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final scheme = Theme.of(context).colorScheme;
    final onay = (state.badges['onay'] ?? 0) as int;
    return Scaffold(
      body: IndexedStack(index: _index, children: _pages),
      bottomNavigationBar: DecoratedBox(
        decoration: BoxDecoration(border: Border(top: BorderSide(color: scheme.outlineVariant))),
        child: NavigationBar(
          selectedIndex: _index,
          onDestinationSelected: _select,
          labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
          destinations: [
            const NavigationDestination(icon: Icon(Icons.space_dashboard_outlined), selectedIcon: Icon(Icons.space_dashboard_rounded), label: 'Ana Sayfa'),
            const NavigationDestination(icon: Icon(Icons.apps_rounded), selectedIcon: Icon(Icons.apps_rounded), label: 'Uygulamalar'),
            NavigationDestination(
              icon: Container(
                width: 52,
                height: 36,
                decoration: BoxDecoration(
                  gradient: LinearGradient(colors: [scheme.primary, scheme.secondary]),
                  borderRadius: BorderRadius.circular(14),
                ),
                child: Icon(Icons.qr_code_scanner_rounded, color: scheme.onPrimary, size: 22),
              ),
              label: 'Tara',
              tooltip: 'Barkod / QR tara',
            ),
            NavigationDestination(
              icon: Badge(isLabelVisible: onay > 0, label: Text('$onay'), child: const Icon(Icons.task_alt_outlined)),
              selectedIcon: Badge(isLabelVisible: onay > 0, label: Text('$onay'), child: const Icon(Icons.task_alt_rounded)),
              label: 'Onaylar',
            ),
            const NavigationDestination(icon: Icon(Icons.person_outline_rounded), selectedIcon: Icon(Icons.person_rounded), label: 'Profil'),
          ],
        ),
      ),
    );
  }
}
