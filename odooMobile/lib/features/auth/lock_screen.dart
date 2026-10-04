import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/session.dart';
import '../../core/theme.dart';
import '../../widgets/brand.dart';

/// Biyometrik kilit açıkken uygulama açılışında gösterilir.
class LockScreen extends StatefulWidget {
  const LockScreen({super.key});

  @override
  State<LockScreen> createState() => _LockScreenState();
}

class _LockScreenState extends State<LockScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => context.read<AppState>().unlock());
  }

  @override
  Widget build(BuildContext context) {
    final state = context.read<AppState>();
    final text = Theme.of(context).textTheme;
    return Scaffold(
      body: HeroBackground(
        radius: 0,
        child: SafeArea(
          child: SizedBox.expand(
            child: Column(children: [
              const Spacer(flex: 2),
              const AtlasLogo(size: 80, light: true),
              const SizedBox(height: Gap.xl),
              Text(state.login, style: text.titleMedium?.copyWith(color: Colors.white)),
              const Spacer(flex: 2),
              Semantics(
                button: true,
                label: 'Kilidi aç',
                child: InkResponse(
                  onTap: state.unlock,
                  radius: 48,
                  child: Container(
                    width: 84,
                    height: 84,
                    decoration: BoxDecoration(shape: BoxShape.circle, color: Colors.white.withValues(alpha: .16)),
                    child: const Icon(Icons.fingerprint_rounded, size: 48, color: Colors.white),
                  ),
                ),
              ),
              const SizedBox(height: Gap.md),
              Text('Kilidi açmak için dokunun', style: text.bodyMedium?.copyWith(color: Colors.white70)),
              const SizedBox(height: Gap.xl),
              TextButton(
                onPressed: state.signOut,
                style: TextButton.styleFrom(foregroundColor: Colors.white),
                child: const Text('Farklı hesapla giriş yap'),
              ),
              const SizedBox(height: Gap.lg),
            ]),
          ),
        ),
      ),
    );
  }
}
