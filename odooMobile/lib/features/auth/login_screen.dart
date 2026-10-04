import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:provider/provider.dart';

import '../../core/session.dart';
import '../../core/theme.dart';
import '../../widgets/brand.dart';
import '../../widgets/common.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _form = GlobalKey<FormState>();
  late final TextEditingController _server, _db, _user;
  final _password = TextEditingController();
  final _serverFocus = FocusNode();
  List<String> _databases = [];
  bool _loadingDbs = false, _busy = false, _obscure = true, _remember = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    final s = context.read<AppState>();
    _server = TextEditingController(text: s.serverUrl);
    _db = TextEditingController(text: s.database);
    _user = TextEditingController(text: s.login);
    _remember = s.rememberMe;
    _serverFocus.addListener(() {
      if (!_serverFocus.hasFocus) _fetchDatabases();
    });
    if (s.serverUrl.isNotEmpty) _fetchDatabases();
  }

  @override
  void dispose() {
    for (final c in [_server, _db, _user, _password]) {
      c.dispose();
    }
    _serverFocus.dispose();
    super.dispose();
  }

  Future<void> _fetchDatabases() async {
    if (_server.text.trim().isEmpty) return;
    setState(() => _loadingDbs = true);
    try {
      final dbs = await context.read<AppState>().fetchDatabases(_server.text);
      setState(() {
        _databases = dbs;
        if (dbs.length == 1 || (!dbs.contains(_db.text) && dbs.isNotEmpty)) _db.text = dbs.first;
      });
    } catch (_) {
      // Veritabanı listesi kapalı olabilir (list_db = False); elle girilir.
      setState(() => _databases = []);
    } finally {
      if (mounted) setState(() => _loadingDbs = false);
    }
  }

  Future<void> _submit() async {
    FocusScope.of(context).unfocus();
    if (!_form.currentState!.validate()) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await context.read<AppState>().signIn(
            url: _server.text,
            db: _db.text.trim(),
            user: _user.text.trim(),
            password: _password.text,
            remember: _remember,
          );
    } catch (e) {
      setState(() => _error = errorText(e));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  String? _required(String? v, String label) => (v == null || v.trim().isEmpty) ? '$label gerekli' : null;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    final scheme = Theme.of(context).colorScheme;
    final top = MediaQuery.of(context).padding.top;
    return Scaffold(
      body: SingleChildScrollView(
        keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
        child: Column(children: [
          HeroBackground(
            radius: 36,
            child: SizedBox(
              width: double.infinity,
              child: Padding(
                padding: EdgeInsets.fromLTRB(Gap.xl, top + 48, Gap.xl, 72),
                child: Column(children: [
                  const AtlasLogo(size: 72, light: true).animate().fadeIn(duration: 400.ms).scale(begin: const Offset(.9, .9)),
                  const SizedBox(height: Gap.lg),
                  Text('İşletmeniz cebinizde',
                      style: text.titleMedium?.copyWith(color: Colors.white.withValues(alpha: .9), fontWeight: FontWeight.w400)),
                ]),
              ),
            ),
          ),
          Transform.translate(
            offset: const Offset(0, -40),
            child: ContentWidth(
              max: 480,
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: Gap.lg),
                child: Card(
                  elevation: 6,
                  shadowColor: Colors.black26,
                  child: Padding(
                    padding: const EdgeInsets.all(Gap.xl),
                    child: Form(
                      key: _form,
                      child: AutofillGroup(
                        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                          Text('Giriş yap', style: text.headlineSmall),
                          const SizedBox(height: 4),
                          Text('Atlas ERP hesabınızla oturum açın', style: text.bodyMedium?.copyWith(color: scheme.onSurfaceVariant)),
                          const SizedBox(height: Gap.xl),
                          TextFormField(
                            controller: _server,
                            focusNode: _serverFocus,
                            keyboardType: TextInputType.url,
                            autocorrect: false,
                            textInputAction: TextInputAction.next,
                            decoration: InputDecoration(
                              labelText: 'Sunucu adresi',
                              hintText: 'erp.sirketiniz.com',
                              prefixIcon: const Icon(Icons.dns_rounded),
                              suffixIcon: _loadingDbs
                                  ? const Padding(padding: EdgeInsets.all(14), child: SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2)))
                                  : null,
                            ),
                            validator: (v) => _required(v, 'Sunucu adresi'),
                          ),
                          const SizedBox(height: Gap.md),
                          if (_databases.length > 1)
                            DropdownButtonFormField<String>(
                              initialValue: _databases.contains(_db.text) ? _db.text : null,
                              items: [for (final d in _databases) DropdownMenuItem(value: d, child: Text(d))],
                              onChanged: (v) => _db.text = v ?? '',
                              decoration: const InputDecoration(labelText: 'Veritabanı', prefixIcon: Icon(Icons.storage_rounded)),
                              validator: (v) => _required(v, 'Veritabanı'),
                            )
                          else
                            TextFormField(
                              controller: _db,
                              autocorrect: false,
                              textInputAction: TextInputAction.next,
                              decoration: const InputDecoration(labelText: 'Veritabanı', prefixIcon: Icon(Icons.storage_rounded)),
                              validator: (v) => _required(v, 'Veritabanı'),
                            ),
                          const SizedBox(height: Gap.md),
                          TextFormField(
                            controller: _user,
                            autocorrect: false,
                            keyboardType: TextInputType.emailAddress,
                            textInputAction: TextInputAction.next,
                            autofillHints: const [AutofillHints.username, AutofillHints.email],
                            decoration: const InputDecoration(labelText: 'Kullanıcı adı / e-posta', prefixIcon: Icon(Icons.person_rounded)),
                            validator: (v) => _required(v, 'Kullanıcı adı'),
                          ),
                          const SizedBox(height: Gap.md),
                          TextFormField(
                            controller: _password,
                            obscureText: _obscure,
                            autofillHints: const [AutofillHints.password],
                            textInputAction: TextInputAction.done,
                            onFieldSubmitted: (_) => _submit(),
                            decoration: InputDecoration(
                              labelText: 'Parola',
                              prefixIcon: const Icon(Icons.lock_rounded),
                              suffixIcon: IconButton(
                                tooltip: _obscure ? 'Parolayı göster' : 'Parolayı gizle',
                                icon: Icon(_obscure ? Icons.visibility_rounded : Icons.visibility_off_rounded),
                                onPressed: () => setState(() => _obscure = !_obscure),
                              ),
                            ),
                            validator: (v) => (v == null || v.isEmpty) ? 'Parola gerekli' : null,
                          ),
                          const SizedBox(height: Gap.sm),
                          SwitchListTile.adaptive(
                            contentPadding: EdgeInsets.zero,
                            value: _remember,
                            onChanged: (v) => setState(() => _remember = v),
                            title: const Text('Oturumu açık tut'),
                            subtitle: Text('Oturum süresi dolunca otomatik yenilenir', style: text.bodySmall),
                          ),
                          AnimatedSize(
                            duration: const Duration(milliseconds: 200),
                            child: _error == null
                                ? const SizedBox(width: double.infinity)
                                : Container(
                                    margin: const EdgeInsets.only(bottom: Gap.md),
                                    padding: const EdgeInsets.all(Gap.md),
                                    decoration: BoxDecoration(
                                        color: AtlasColors.of(context).dangerContainer, borderRadius: BorderRadius.circular(Gap.radiusSm)),
                                    child: Row(children: [
                                      Icon(Icons.error_outline_rounded, color: AtlasColors.of(context).danger),
                                      const SizedBox(width: Gap.sm),
                                      Expanded(child: Text(_error!, style: TextStyle(color: AtlasColors.of(context).danger))),
                                    ]),
                                  ),
                          ),
                          FilledButton(
                            onPressed: _busy ? null : _submit,
                            child: _busy
                                ? const SizedBox(width: 22, height: 22, child: CircularProgressIndicator(strokeWidth: 2.4, color: Colors.white))
                                : const Text('Giriş yap'),
                          ),
                        ]),
                      ),
                    ),
                  ),
                ),
              ).animate().fadeIn(delay: 120.ms, duration: 350.ms).slideY(begin: .06, curve: Curves.easeOutCubic),
            ),
          ),
          Padding(
            padding: const EdgeInsets.only(bottom: Gap.xl),
            child: Text('Atlas ERP • Odoo 20', style: text.bodySmall),
          ),
        ]),
      ),
    );
  }
}
