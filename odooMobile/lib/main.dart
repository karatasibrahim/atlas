import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'core/session.dart';
import 'core/theme.dart';
import 'features/auth/lock_screen.dart';
import 'features/auth/login_screen.dart';
import 'features/shell/home_shell.dart';
import 'widgets/brand.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await initializeDateFormatting('tr_TR');
  SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);
  final prefs = await SharedPreferences.getInstance();
  final state = AppState(prefs);
  runApp(ChangeNotifierProvider.value(value: state, child: const AtlasApp()));
  state.restore();
}

class AtlasApp extends StatelessWidget {
  const AtlasApp({super.key});

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    return MaterialApp(
      title: 'Atlas',
      debugShowCheckedModeBanner: false,
      theme: AtlasTheme.build(state.palette, Brightness.light),
      darkTheme: AtlasTheme.build(state.palette, Brightness.dark),
      themeMode: state.themeMode,
      locale: const Locale('tr', 'TR'),
      supportedLocales: const [Locale('tr', 'TR'), Locale('en')],
      localizationsDelegates: const [
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      home: AnimatedSwitcher(
        duration: const Duration(milliseconds: 350),
        child: switch (state.status) {
          AuthStatus.starting => const SplashScreen(key: ValueKey('splash')),
          AuthStatus.loggedOut => const LoginScreen(key: ValueKey('login')),
          AuthStatus.locked => const LockScreen(key: ValueKey('lock')),
          AuthStatus.loggedIn => const HomeShell(key: ValueKey('home')),
        },
      ),
    );
  }
}

class SplashScreen extends StatelessWidget {
  const SplashScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final c = AtlasColors.of(context);
    return Scaffold(
      body: Container(
        decoration: BoxDecoration(gradient: LinearGradient(colors: [c.heroStart, c.heroEnd], begin: Alignment.topLeft, end: Alignment.bottomRight)),
        alignment: Alignment.center,
        child: const AtlasLogo(size: 88, light: true),
      ),
    );
  }
}
