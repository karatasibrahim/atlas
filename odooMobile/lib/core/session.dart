import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:local_auth/local_auth.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'api.dart';
import 'theme.dart';

enum AuthStatus { starting, loggedOut, locked, loggedIn }

/// Uygulama durumu: sunucu bağlantısı, oturum, profil, tercihler ve rozet sayıları.
class AppState extends ChangeNotifier {
  AppState(this._prefs);

  final SharedPreferences _prefs;
  final _secure = const FlutterSecureStorage();
  final _localAuth = LocalAuthentication();

  OdooClient? _client;
  OdooClient get api => _client!;
  AuthStatus status = AuthStatus.starting;
  Map<String, dynamic> profile = {};
  Map<String, dynamic> badges = {'onay': 0, 'aktivite': 0};

  String get serverUrl => _prefs.getString('server') ?? '';
  String get database => _prefs.getString('db') ?? '';
  String get login => _prefs.getString('login') ?? '';
  bool get rememberMe => _prefs.getBool('remember') ?? true;
  bool get biometricEnabled => _prefs.getBool('biometric') ?? false;

  ThemeMode get themeMode => ThemeMode.values[_prefs.getInt('themeMode') ?? 0];
  AtlasPalette get palette => AtlasPalette.values[(_prefs.getInt('palette') ?? 0).clamp(0, AtlasPalette.values.length - 1)];

  Map<String, dynamic> get modules => Map<String, dynamic>.from(profile['moduller'] ?? {});
  bool can(String module) => modules[module] == true;
  String get currencySymbol => (profile['para_simge'] ?? '₺').toString();

  void setThemeMode(ThemeMode mode) {
    _prefs.setInt('themeMode', mode.index);
    notifyListeners();
  }

  void setPalette(AtlasPalette p) {
    _prefs.setInt('palette', p.index);
    notifyListeners();
  }

  Future<bool> biometricAvailable() async {
    try {
      return await _localAuth.isDeviceSupported() && await _localAuth.canCheckBiometrics;
    } catch (_) {
      return false;
    }
  }

  Future<bool> authenticateBiometric() async {
    try {
      return await _localAuth.authenticate(localizedReason: 'Atlas\'a giriş için kimliğinizi doğrulayın');
    } catch (_) {
      return false;
    }
  }

  Future<void> setBiometric(bool value) async {
    if (value && !await authenticateBiometric()) return;
    await _prefs.setBool('biometric', value);
    notifyListeners();
  }

  OdooClient _makeClient(String url, {String? sessionId}) {
    final c = OdooClient(baseUrl: url, sessionId: sessionId);
    c.onSessionExpired = _reauthenticate;
    return c;
  }

  /// Açılışta kayıtlı oturumu geri yükler.
  Future<void> restore() async {
    final sid = await _secure.read(key: 'session_id');
    if (serverUrl.isEmpty || sid == null) {
      status = AuthStatus.loggedOut;
      notifyListeners();
      return;
    }
    _client = _makeClient(serverUrl, sessionId: sid);
    if (biometricEnabled) {
      status = AuthStatus.locked;
      notifyListeners();
      return;
    }
    await _enter();
  }

  Future<void> unlock() async {
    if (await authenticateBiometric()) await _enter();
  }

  Future<void> _enter() async {
    try {
      await api.sessionInfo();
      await _loadProfile();
      status = AuthStatus.loggedIn;
    } on OdooException catch (e) {
      status = e.network && profile.isNotEmpty ? AuthStatus.loggedIn : AuthStatus.loggedOut;
    }
    notifyListeners();
  }

  Future<bool> _reauthenticate() async {
    final pw = await _secure.read(key: 'password');
    if (pw == null || database.isEmpty) {
      await _clearSession();
      return false;
    }
    try {
      await _client!.authenticate(database, login, pw);
      await _secure.write(key: 'session_id', value: _client!.sessionId);
      return true;
    } catch (_) {
      await _clearSession();
      return false;
    }
  }

  Future<List<String>> fetchDatabases(String url) => _makeClient(OdooClient.normalizeUrl(url)).databases();

  Future<void> signIn({required String url, required String db, required String user, required String password, required bool remember}) async {
    final normalized = OdooClient.normalizeUrl(url);
    final client = _makeClient(normalized);
    await client.authenticate(db, user, password);
    _client = client;
    await _prefs.setString('server', normalized);
    await _prefs.setString('db', db);
    await _prefs.setString('login', user);
    await _prefs.setBool('remember', remember);
    await _secure.write(key: 'session_id', value: client.sessionId);
    if (remember) {
      await _secure.write(key: 'password', value: password);
    } else {
      await _secure.delete(key: 'password');
      await _prefs.setBool('biometric', false);
    }
    await _loadProfile();
    status = AuthStatus.loggedIn;
    notifyListeners();
  }

  Future<void> _loadProfile() async {
    profile = Map<String, dynamic>.from(await api.mobil('profil'));
    await refreshBadges();
  }

  Future<void> refreshProfile() async {
    await _loadProfile();
    notifyListeners();
  }

  Future<void> refreshBadges() async {
    try {
      badges = Map<String, dynamic>.from(await api.mobil('rozetler'));
      notifyListeners();
    } catch (_) {}
  }

  Future<void> _clearSession() async {
    await _secure.delete(key: 'session_id');
    status = AuthStatus.loggedOut;
    profile = {};
    notifyListeners();
  }

  Future<void> signOut() async {
    await _client?.logout();
    await _secure.delete(key: 'password');
    await _prefs.setBool('biometric', false);
    await _clearSession();
  }

  /// Oturum düşerse (hata türünden) giriş ekranına döner.
  void handleError(Object error) {
    if (error is OdooException && error.sessionExpired) _clearSession();
  }

  Future<String?> storedPassword() => _secure.read(key: 'password');
}
