import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

/// Sunucudan dönen kullanıcıya gösterilebilir hata (UserError, AccessError, ValidationError...).
class OdooException implements Exception {
  OdooException(this.message, {this.type = '', this.sessionExpired = false, this.network = false});
  final String message;
  final String type;
  final bool sessionExpired;
  final bool network;

  @override
  String toString() => message;
}

/// Odoo 20 JSON-RPC istemcisi. Oturum çerezi (session_id) ile çalışır;
/// iş mantığı sunucudaki atlas.mobil / atlas.barkod modellerindedir.
class OdooClient {
  OdooClient({required this.baseUrl, this.sessionId});

  String baseUrl;
  String? sessionId;
  Map<String, dynamic> userContext = {};
  final _http = http.Client();
  int _id = 0;

  /// Oturum süresi dolduğunda çağrılır; true dönerse istek bir kez tekrarlanır.
  Future<bool> Function()? onSessionExpired;

  static String normalizeUrl(String url) {
    var u = url.trim();
    if (u.isEmpty) return u;
    if (!u.startsWith('http://') && !u.startsWith('https://')) u = 'https://$u';
    while (u.endsWith('/')) {
      u = u.substring(0, u.length - 1);
    }
    return u;
  }

  Map<String, String> get authHeaders => sessionId == null ? {} : {'Cookie': 'session_id=$sessionId'};

  String absolute(String path) => path.startsWith('http') ? path : '$baseUrl$path';

  Future<dynamic> _rpc(String path, Map<String, dynamic> params, {bool retry = true}) async {
    final uri = Uri.parse('$baseUrl$path');
    final body = jsonEncode({'jsonrpc': '2.0', 'method': 'call', 'id': ++_id, 'params': params});
    http.Response res;
    try {
      res = await _http
          .post(uri, headers: {'Content-Type': 'application/json', 'Accept': 'application/json', ...authHeaders}, body: body)
          .timeout(const Duration(seconds: 40));
    } on TimeoutException {
      throw OdooException('Sunucu yanıt vermedi. Bağlantınızı kontrol edip tekrar deneyin.', network: true);
    } on SocketException {
      throw OdooException('Sunucuya ulaşılamıyor. İnternet bağlantınızı ve sunucu adresini kontrol edin.', network: true);
    } on HandshakeException {
      throw OdooException('Güvenli bağlantı kurulamadı (SSL). Sunucu adresini kontrol edin.', network: true);
    } on http.ClientException catch (e) {
      throw OdooException('Bağlantı hatası: ${e.message}', network: true);
    }

    final cookie = res.headers['set-cookie'];
    if (cookie != null) {
      final m = RegExp(r'session_id=([^;]+)').firstMatch(cookie);
      if (m != null) sessionId = m.group(1);
    }
    if (res.statusCode == 404) {
      throw OdooException('Adres bulunamadı (404). Sunucu adresinin bir Odoo sunucusu olduğundan emin olun.');
    }
    if (res.statusCode >= 500 && res.body.isEmpty) {
      throw OdooException('Sunucu hatası (${res.statusCode}).');
    }
    Map<String, dynamic> data;
    try {
      data = jsonDecode(utf8.decode(res.bodyBytes)) as Map<String, dynamic>;
    } catch (_) {
      throw OdooException('Sunucudan beklenmeyen yanıt (${res.statusCode}).');
    }
    final error = data['error'];
    if (error is Map) {
      final errData = (error['data'] as Map?) ?? {};
      final name = (errData['name'] ?? '').toString();
      final expired = name.contains('SessionExpired') || (error['code'] == 100);
      if (expired) {
        if (retry && onSessionExpired != null && await onSessionExpired!()) {
          return _rpc(path, params, retry: false);
        }
        throw OdooException('Oturumunuzun süresi doldu. Lütfen tekrar giriş yapın.', type: name, sessionExpired: true);
      }
      var message = (errData['message'] ?? error['message'] ?? 'Bilinmeyen hata').toString();
      if (name.endsWith('AccessDenied')) message = 'Kullanıcı adı veya parola hatalı.';
      throw OdooException(message.trim(), type: name);
    }
    return data['result'];
  }

  Future<List<String>> databases() async {
    final r = await _rpc('/web/database/list', {});
    return (r as List).cast<String>();
  }

  Future<Map<String, dynamic>> authenticate(String db, String login, String password) async {
    sessionId = null;
    final r = await _rpc('/web/session/authenticate', {'db': db, 'login': login, 'password': password}, retry: false);
    if (r == null || r['uid'] == null || r['uid'] == false) {
      throw OdooException('Kullanıcı adı veya parola hatalı.');
    }
    userContext = Map<String, dynamic>.from(r['user_context'] ?? {});
    return Map<String, dynamic>.from(r);
  }

  Future<Map<String, dynamic>> sessionInfo() async {
    final r = await _rpc('/web/session/get_session_info', {});
    userContext = Map<String, dynamic>.from(r['user_context'] ?? {});
    return Map<String, dynamic>.from(r);
  }

  Future<void> logout() async {
    try {
      await _rpc('/web/session/destroy', {}, retry: false);
    } catch (_) {}
    sessionId = null;
  }

  /// model.method(*args, **kwargs) çağrısı. Bağlam kullanıcının dili ve saat dilimidir.
  Future<dynamic> call(String model, String method, {List args = const [], Map<String, dynamic> kwargs = const {}}) {
    return _rpc('/web/dataset/call_kw/$model/$method', {
      'model': model,
      'method': method,
      'args': args,
      'kwargs': {
        ...kwargs,
        'context': {...userContext, ...?kwargs['context'] as Map<String, dynamic>?},
      },
    });
  }

  /// Mobil API kısa yolu: `atlas.mobil.<method>(**kwargs)`
  Future<dynamic> mobil(String method, [Map<String, dynamic> kwargs = const {}]) =>
      call('atlas.mobil', method, kwargs: kwargs);

  /// Barkod API kısa yolu: `atlas.barkod.<method>(**kwargs)`
  Future<dynamic> barkod(String method, [Map<String, dynamic> kwargs = const {}]) =>
      call('atlas.barkod', method, kwargs: kwargs);
}
