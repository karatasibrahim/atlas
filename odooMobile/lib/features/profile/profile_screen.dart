import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/session.dart';
import '../../core/theme.dart';
import '../../widgets/brand.dart';
import '../../widgets/common.dart';
import '../activities/activities_screen.dart';
import '../hr/hr.dart';

class ProfileScreen extends StatelessWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final p = state.profile;
    final text = Theme.of(context).textTheme;
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(title: const Text('Profil')),
      body: RefreshIndicator(
        onRefresh: () => runAction(context, state.refreshProfile),
        child: ContentWidth(
          child: ListView(padding: const EdgeInsets.all(Gap.lg), children: [
            AppCard(
              child: Row(children: [
                Avatar(name: p['ad'] ?? '?', image: p['avatar'], size: 64),
                const SizedBox(width: Gap.lg),
                Expanded(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text(p['ad'] ?? '', style: text.titleLarge),
                    if ((p['unvan'] ?? '') != '' || (p['departman'] ?? '') != '')
                      Text([p['unvan'], p['departman']].where((s) => (s ?? '') != '').join(' • '), style: text.bodyMedium),
                    Text(p['email'] ?? '', style: text.bodySmall),
                  ]),
                ),
              ]),
            ),
            const SizedBox(height: Gap.md),
            AppCard(
              padding: EdgeInsets.zero,
              child: Column(children: [
                ListTile(
                  leading: const Icon(Icons.business_rounded),
                  title: const Text('Şirket'),
                  subtitle: Text(p['sirket'] ?? ''),
                ),
                if (state.can('devam'))
                  ListTile(
                    leading: const Icon(Icons.fingerprint_rounded),
                    title: const Text('Giriş / çıkış geçmişi'),
                    trailing: const Icon(Icons.chevron_right_rounded),
                    onTap: () => Navigator.push(context, MaterialPageRoute(builder: (_) => const AttendanceScreen())),
                  ),
                ListTile(
                  leading: const Icon(Icons.event_note_rounded),
                  title: const Text('Aktivitelerim'),
                  trailing: Row(mainAxisSize: MainAxisSize.min, children: [
                    if ((state.badges['aktivite'] ?? 0) > 0) Badge(label: Text('${state.badges['aktivite']}')),
                    const Icon(Icons.chevron_right_rounded),
                  ]),
                  onTap: () => Navigator.push(context, MaterialPageRoute(builder: (_) => const ActivitiesScreen())),
                ),
              ]),
            ),
            const SectionHeader('Görünüm'),
            AppCard(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text('Tema', style: text.labelLarge),
                const SizedBox(height: Gap.sm),
                SizedBox(
                  width: double.infinity,
                  child: SegmentedButton<ThemeMode>(
                    segments: const [
                      ButtonSegment(value: ThemeMode.system, label: Text('Sistem'), icon: Icon(Icons.brightness_auto_rounded)),
                      ButtonSegment(value: ThemeMode.light, label: Text('Açık'), icon: Icon(Icons.light_mode_rounded)),
                      ButtonSegment(value: ThemeMode.dark, label: Text('Koyu'), icon: Icon(Icons.dark_mode_rounded)),
                    ],
                    selected: {state.themeMode},
                    onSelectionChanged: (s) => state.setThemeMode(s.first),
                  ),
                ),
                const SizedBox(height: Gap.lg),
                Text('Renk teması', style: text.labelLarge),
                const SizedBox(height: Gap.md),
                Wrap(spacing: Gap.md, runSpacing: Gap.md, children: [
                  for (final pal in AtlasPalette.values)
                    Semantics(
                      button: true,
                      selected: state.palette == pal,
                      label: pal.label,
                      child: InkWell(
                        borderRadius: BorderRadius.circular(Gap.radius),
                        onTap: () => state.setPalette(pal),
                        child: Container(
                          width: 72,
                          padding: const EdgeInsets.symmetric(vertical: Gap.sm),
                          decoration: BoxDecoration(
                            borderRadius: BorderRadius.circular(Gap.radius),
                            border: Border.all(color: state.palette == pal ? scheme.primary : scheme.outlineVariant, width: state.palette == pal ? 2 : 1),
                          ),
                          child: Column(children: [
                            Container(
                              width: 36,
                              height: 36,
                              decoration: BoxDecoration(
                                shape: BoxShape.circle,
                                gradient: LinearGradient(colors: [pal.primary, pal.accent], begin: Alignment.topLeft, end: Alignment.bottomRight),
                              ),
                              child: state.palette == pal ? const Icon(Icons.check_rounded, color: Colors.white, size: 20) : null,
                            ),
                            const SizedBox(height: 6),
                            Text(pal.label, style: text.labelSmall, textAlign: TextAlign.center, maxLines: 2),
                          ]),
                        ),
                      ),
                    ),
                ]),
              ]),
            ),
            const SectionHeader('Güvenlik'),
            AppCard(
              padding: EdgeInsets.zero,
              child: FutureBuilder<bool>(
                future: state.biometricAvailable(),
                builder: (context, snap) {
                  final available = snap.data == true && state.rememberMe;
                  return SwitchListTile.adaptive(
                    secondary: const Icon(Icons.face_unlock_rounded),
                    title: const Text('Biyometrik kilit'),
                    subtitle: Text(
                      !state.rememberMe
                          ? 'Kullanmak için "Oturumu açık tut" ile giriş yapın'
                          : (snap.data == false ? 'Cihazda Face ID / parmak izi yok' : 'Açılışta Face ID / parmak izi iste'),
                    ),
                    value: state.biometricEnabled,
                    onChanged: available ? state.setBiometric : null,
                  );
                },
              ),
            ),
            const SectionHeader('Bağlantı'),
            AppCard(
              padding: const EdgeInsets.symmetric(horizontal: Gap.lg, vertical: Gap.sm),
              child: Column(children: [
                InfoRow('Sunucu', state.serverUrl),
                InfoRow('Veritabanı', state.database),
                InfoRow('Kullanıcı', state.login),
              ]),
            ),
            const SizedBox(height: Gap.xl),
            OutlinedButton.icon(
              style: OutlinedButton.styleFrom(foregroundColor: scheme.error),
              onPressed: () async {
                if (await confirm(context, title: 'Çıkış yapılsın mı?', ok: 'Çıkış yap', destructive: true)) state.signOut();
              },
              icon: const Icon(Icons.logout_rounded),
              label: const Text('Çıkış yap'),
            ),
            const SizedBox(height: Gap.xl),
            const Center(child: AtlasLogo(size: 36)),
            const SizedBox(height: Gap.sm),
            Center(child: Text('Atlas Mobil 1.0.0', style: text.bodySmall)),
            const SizedBox(height: Gap.xl),
          ]),
        ),
      ),
    );
  }
}
