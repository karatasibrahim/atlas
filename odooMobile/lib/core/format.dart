import 'package:intl/intl.dart';

/// Türkçe sayı, para ve tarih biçimleri.
class Fmt {
  static final _num = NumberFormat.decimalPattern('tr_TR');
  static final _money = NumberFormat.currency(locale: 'tr_TR', symbol: '', decimalDigits: 2);
  static final _compact = NumberFormat.compact(locale: 'tr_TR');
  static final _date = DateFormat('d MMM y', 'tr_TR');
  static final _dateShort = DateFormat('d MMM', 'tr_TR');
  static final _dateTime = DateFormat('d MMM y, HH:mm', 'tr_TR');
  static final _time = DateFormat('HH:mm', 'tr_TR');
  static final _weekday = DateFormat('EEE', 'tr_TR');
  static final _full = DateFormat('d MMMM y, EEEE', 'tr_TR');

  static double d(dynamic v) => v is num ? v.toDouble() : double.tryParse('$v') ?? 0;

  static String money(dynamic v, [String symbol = '₺']) => '${_money.format(d(v)).trim()} $symbol';

  static String compactMoney(dynamic v, [String symbol = '₺']) {
    final x = d(v);
    return x.abs() >= 1000000 ? '${_compact.format(x)} $symbol' : '${_num.format(x.round())} $symbol';
  }

  static String qty(dynamic v) {
    final x = d(v);
    return x == x.roundToDouble() ? _num.format(x.round()) : _num.format(double.parse(x.toStringAsFixed(3)));
  }

  static String percent(dynamic v) => '%${_num.format(d(v).round())}';

  /// Sunucudan gelen tarih ('2026-10-04') veya UTC tarih-saat ('...Z') değerini yerel saate çevirir.
  static DateTime? parse(dynamic v) {
    if (v == null || v == false || v == '') return null;
    final dt = DateTime.tryParse(v.toString());
    return dt == null ? null : (dt.isUtc ? dt.toLocal() : dt);
  }

  static String date(dynamic v) => _f(v, _date);
  static String dateShort(dynamic v) => _f(v, _dateShort);
  static String dateTime(dynamic v) => _f(v, _dateTime);
  static String time(dynamic v) => _f(v, _time);
  static String weekday(dynamic v) => _f(v, _weekday);
  static String fullDate(DateTime v) => _full.format(v);

  static String _f(dynamic v, DateFormat f) {
    final dt = parse(v);
    return dt == null ? '' : f.format(dt);
  }

  /// "3 gün önce", "bugün", "yarın" gibi göreli ifade.
  static String relative(dynamic v) {
    final dt = parse(v);
    if (dt == null) return '';
    final now = DateTime.now();
    final day = DateTime(dt.year, dt.month, dt.day);
    final today = DateTime(now.year, now.month, now.day);
    final diff = day.difference(today).inDays;
    if (diff == 0) {
      final hasTime = v.toString().contains('T') || v.toString().contains(' ');
      if (!hasTime) return 'Bugün';
      final mins = now.difference(dt).inMinutes;
      if (mins < 1) return 'Az önce';
      if (mins < 60) return '$mins dk önce';
      return 'Bugün ${_time.format(dt)}';
    }
    if (diff == -1) return 'Dün';
    if (diff == 1) return 'Yarın';
    if (diff < 0 && diff > -7) return '${-diff} gün önce';
    if (diff > 0 && diff < 7) return '$diff gün sonra';
    return _date.format(dt);
  }

  static String hours(dynamic v) {
    final x = d(v);
    final h = x.floor();
    final m = ((x - h) * 60).round();
    return m == 0 ? '$h sa' : '$h sa $m dk';
  }

  static String initials(String name) {
    final parts = name.trim().split(RegExp(r'\s+')).where((p) => p.isNotEmpty).toList();
    if (parts.isEmpty) return '?';
    if (parts.length == 1) return parts.first.substring(0, 1).toUpperCase();
    return (parts.first.substring(0, 1) + parts[1].substring(0, 1)).toUpperCase();
  }
}
