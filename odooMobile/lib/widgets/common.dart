import 'dart:async';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import 'package:shimmer/shimmer.dart';

import '../core/api.dart';
import '../core/format.dart';
import '../core/session.dart';
import '../core/theme.dart';

// ---------------------------------------------------------------------------
// Bildirimler
// ---------------------------------------------------------------------------

String errorText(Object e) => e is OdooException ? e.message : 'Beklenmeyen bir hata oluştu.';

void showSuccess(BuildContext context, String message) {
  HapticFeedback.lightImpact();
  final c = AtlasColors.of(context);
  ScaffoldMessenger.of(context)
    ..hideCurrentSnackBar()
    ..showSnackBar(SnackBar(
      backgroundColor: c.success,
      content: Row(children: [
        const Icon(Icons.check_circle_rounded, color: Colors.white, size: 20),
        const SizedBox(width: 10),
        Expanded(child: Text(message, style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w600))),
      ]),
    ));
}

void showError(BuildContext context, Object error) {
  HapticFeedback.heavyImpact();
  context.read<AppState>().handleError(error);
  final c = AtlasColors.of(context);
  ScaffoldMessenger.of(context)
    ..hideCurrentSnackBar()
    ..showSnackBar(SnackBar(
      backgroundColor: c.danger,
      duration: const Duration(seconds: 5),
      content: Row(children: [
        const Icon(Icons.error_rounded, color: Colors.white, size: 20),
        const SizedBox(width: 10),
        Expanded(child: Text(errorText(error), style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w600))),
      ]),
    ));
}

/// İşlemi çalıştırır, hata olursa gösterir; başarılıysa sonucu döndürür.
Future<T?> runAction<T>(BuildContext context, Future<T> Function() action, {String? success}) async {
  try {
    final r = await action();
    if (success != null && context.mounted) showSuccess(context, success);
    return r;
  } catch (e) {
    if (context.mounted) showError(context, e);
    return null;
  }
}

Future<bool> confirm(BuildContext context,
    {required String title, String? message, String ok = 'Onayla', bool destructive = false}) async {
  final scheme = Theme.of(context).colorScheme;
  final r = await showDialog<bool>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: Text(title),
      content: message == null ? null : Text(message),
      actions: [
        TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Vazgeç')),
        FilledButton(
          style: destructive ? FilledButton.styleFrom(backgroundColor: scheme.error) : null,
          onPressed: () => Navigator.pop(ctx, true),
          child: Text(ok),
        ),
      ],
    ),
  );
  return r ?? false;
}

/// Metin isteyen alt sayfa (red nedeni, not, geri bildirim...).
Future<String?> promptText(BuildContext context,
    {required String title, String? hint, String ok = 'Kaydet', bool required = false, bool destructive = false}) {
  final controller = TextEditingController();
  return showModalBottomSheet<String>(
    context: context,
    isScrollControlled: true,
    builder: (ctx) {
      final scheme = Theme.of(ctx).colorScheme;
      return Padding(
        padding: EdgeInsets.fromLTRB(20, 0, 20, MediaQuery.of(ctx).viewInsets.bottom + 20),
        child: StatefulBuilder(builder: (ctx, setState) {
          final valid = !required || controller.text.trim().isNotEmpty;
          return Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            Text(title, style: Theme.of(ctx).textTheme.titleLarge),
            const SizedBox(height: 16),
            TextField(
              controller: controller,
              autofocus: true,
              minLines: 3,
              maxLines: 6,
              onChanged: (_) => setState(() {}),
              decoration: InputDecoration(hintText: hint, labelText: required ? '$title *' : title),
            ),
            const SizedBox(height: 16),
            FilledButton(
              style: destructive ? FilledButton.styleFrom(backgroundColor: scheme.error) : null,
              onPressed: valid ? () => Navigator.pop(ctx, controller.text.trim()) : null,
              child: Text(ok),
            ),
          ]);
        }),
      );
    },
  );
}

// ---------------------------------------------------------------------------
// Veri yükleme
// ---------------------------------------------------------------------------

/// Future'ı yükler; iskelet, hata ve aşağı çekerek yenileme durumlarını yönetir.
class DataView<T> extends StatefulWidget {
  const DataView({super.key, required this.load, required this.builder, this.skeleton, this.refreshable = true});

  final Future<T> Function() load;
  final Widget Function(BuildContext context, T data, Future<void> Function() reload) builder;
  final Widget? skeleton;
  final bool refreshable;

  @override
  State<DataView<T>> createState() => DataViewState<T>();
}

class DataViewState<T> extends State<DataView<T>> {
  T? _data;
  Object? _error;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    reload();
  }

  Future<void> reload() async {
    try {
      final d = await widget.load();
      if (!mounted) return;
      setState(() {
        _data = d;
        _error = null;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      context.read<AppState>().handleError(e);
      setState(() {
        _error = e;
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    Widget child;
    if (_loading && _data == null) {
      child = widget.skeleton ?? const SkeletonList();
    } else if (_error != null && _data == null) {
      child = ErrorState(error: _error!, onRetry: () {
        setState(() => _loading = true);
        reload();
      });
    } else {
      child = widget.builder(context, _data as T, reload);
      if (widget.refreshable) child = RefreshIndicator(onRefresh: reload, child: child);
    }
    return AnimatedSwitcher(duration: const Duration(milliseconds: 220), child: child);
  }
}

class SkeletonList extends StatelessWidget {
  const SkeletonList({super.key, this.count = 7, this.header = false});
  final int count;
  final bool header;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Shimmer.fromColors(
      baseColor: scheme.surfaceContainer,
      highlightColor: scheme.surfaceContainerLow,
      child: ListView(
        physics: const NeverScrollableScrollPhysics(),
        padding: const EdgeInsets.all(Gap.lg),
        children: [
          if (header) ...[
            Container(height: 140, decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(Gap.radius))),
            const SizedBox(height: Gap.lg),
          ],
          for (var i = 0; i < count; i++)
            Padding(
              padding: const EdgeInsets.only(bottom: Gap.md),
              child: Row(children: [
                Container(width: 44, height: 44, decoration: const BoxDecoration(color: Colors.white, shape: BoxShape.circle)),
                const SizedBox(width: Gap.md),
                Expanded(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Container(height: 14, width: double.infinity, color: Colors.white),
                    const SizedBox(height: 8),
                    Container(height: 12, width: 140, color: Colors.white),
                  ]),
                ),
              ]),
            ),
        ],
      ),
    );
  }
}

class ErrorState extends StatelessWidget {
  const ErrorState({super.key, required this.error, required this.onRetry});
  final Object error;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final network = error is OdooException && (error as OdooException).network;
    return EmptyState(
      icon: network ? Icons.wifi_off_rounded : Icons.error_outline_rounded,
      title: network ? 'Bağlantı yok' : 'Yüklenemedi',
      message: errorText(error),
      action: FilledButton.tonalIcon(onPressed: onRetry, icon: const Icon(Icons.refresh_rounded), label: const Text('Tekrar dene')),
    );
  }
}

class EmptyState extends StatelessWidget {
  const EmptyState({super.key, required this.icon, required this.title, this.message, this.action});
  final IconData icon;
  final String title;
  final String? message;
  final Widget? action;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final text = Theme.of(context).textTheme;
    return LayoutBuilder(
      builder: (context, c) => SingleChildScrollView(
        physics: const AlwaysScrollableScrollPhysics(),
        child: ConstrainedBox(
          constraints: BoxConstraints(minHeight: c.maxHeight.isFinite ? c.maxHeight : 300),
          child: Center(
            child: Padding(
              padding: const EdgeInsets.all(Gap.xxl),
              child: Column(mainAxisSize: MainAxisSize.min, children: [
                Container(
                  padding: const EdgeInsets.all(20),
                  decoration: BoxDecoration(color: scheme.primary.withValues(alpha: .08), shape: BoxShape.circle),
                  child: Icon(icon, size: 40, color: scheme.primary),
                ),
                const SizedBox(height: Gap.lg),
                Text(title, style: text.titleMedium, textAlign: TextAlign.center),
                if (message != null) ...[
                  const SizedBox(height: Gap.sm),
                  Text(message!, style: text.bodyMedium?.copyWith(color: scheme.onSurfaceVariant), textAlign: TextAlign.center),
                ],
                if (action != null) ...[const SizedBox(height: Gap.xl), action!],
              ]),
            ),
          ),
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Görsel bileşenler
// ---------------------------------------------------------------------------

enum Tone { success, warning, danger, info, neutral, primary }

class StatusChip extends StatelessWidget {
  const StatusChip(this.label, {super.key, this.tone = Tone.neutral, this.icon});
  final String label;
  final Tone tone;
  final IconData? icon;

  static (Color, Color) colors(BuildContext context, Tone tone) {
    final c = AtlasColors.of(context);
    final scheme = Theme.of(context).colorScheme;
    return switch (tone) {
      Tone.success => (c.success, c.successContainer),
      Tone.warning => (c.warning, c.warningContainer),
      Tone.danger => (c.danger, c.dangerContainer),
      Tone.info => (c.info, c.infoContainer),
      Tone.primary => (scheme.primary, scheme.primary.withValues(alpha: .12)),
      Tone.neutral => (scheme.onSurfaceVariant, c.neutralContainer),
    };
  }

  @override
  Widget build(BuildContext context) {
    final (fg, bg) = colors(context, tone);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(999)),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        if (icon != null) ...[Icon(icon, size: 14, color: fg), const SizedBox(width: 4)],
        Text(label, style: Theme.of(context).textTheme.labelSmall?.copyWith(color: fg)),
      ]),
    );
  }
}

class AppCard extends StatelessWidget {
  const AppCard({super.key, required this.child, this.onTap, this.padding = const EdgeInsets.all(Gap.lg), this.color});
  final Widget child;
  final VoidCallback? onTap;
  final EdgeInsets padding;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    return Card(
      color: color,
      clipBehavior: Clip.antiAlias,
      child: InkWell(onTap: onTap, child: Padding(padding: padding, child: child)),
    );
  }
}

class SectionHeader extends StatelessWidget {
  const SectionHeader(this.title, {super.key, this.action, this.onAction, this.padding});
  final String title;
  final String? action;
  final VoidCallback? onAction;
  final EdgeInsets? padding;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: padding ?? const EdgeInsets.fromLTRB(4, Gap.xl, 0, Gap.sm),
      child: Row(children: [
        Expanded(child: Text(title, style: Theme.of(context).textTheme.titleMedium)),
        if (action != null) TextButton(onPressed: onAction, child: Text(action!)),
      ]),
    );
  }
}

/// Oturum çereziyle sunucudan görsel yükler.
class NetImage extends StatelessWidget {
  const NetImage(this.path, {super.key, this.fit = BoxFit.cover, this.placeholder});
  final String path;
  final BoxFit fit;
  final Widget? placeholder;

  @override
  Widget build(BuildContext context) {
    final api = context.read<AppState>().api;
    return CachedNetworkImage(
      imageUrl: api.absolute(path),
      httpHeaders: api.authHeaders,
      fit: fit,
      fadeInDuration: const Duration(milliseconds: 180),
      placeholder: (_, _) => placeholder ?? const SizedBox.shrink(),
      errorWidget: (_, _, _) => placeholder ?? const SizedBox.shrink(),
    );
  }
}

class Avatar extends StatelessWidget {
  const Avatar({super.key, required this.name, this.image, this.size = 44, this.square = false});
  final String name;
  final String? image;
  final double size;
  final bool square;

  static const _hues = [Color(0xFF714B67), Color(0xFF017E84), Color(0xFF2563EB), Color(0xFFB45309), Color(0xFF7C3AED),
    Color(0xFF0F766E), Color(0xFFBE185D), Color(0xFF4D7C0F)];

  @override
  Widget build(BuildContext context) {
    final color = _hues[name.codeUnits.fold<int>(0, (a, b) => a + b) % _hues.length];
    final fallback = Container(
      color: color.withValues(alpha: .14),
      alignment: Alignment.center,
      child: Text(Fmt.initials(name),
          style: TextStyle(color: color, fontWeight: FontWeight.w700, fontFamily: 'Lexend', fontSize: size * .36)),
    );
    final radius = square ? BorderRadius.circular(size * .28) : BorderRadius.circular(size);
    return Semantics(
      label: name,
      image: true,
      child: ClipRRect(
        borderRadius: radius,
        child: SizedBox(
          width: size,
          height: size,
          child: image == null || image == '' ? fallback : NetImage(image!, placeholder: fallback),
        ),
      ),
    );
  }
}

class InfoRow extends StatelessWidget {
  const InfoRow(this.label, this.value, {super.key, this.icon, this.emphasize = false});
  final String label;
  final String value;
  final IconData? icon;
  final bool emphasize;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        if (icon != null) ...[Icon(icon, size: 20, color: scheme.onSurfaceVariant), const SizedBox(width: 12)],
        Expanded(flex: 2, child: Text(label, style: text.bodyMedium?.copyWith(color: scheme.onSurfaceVariant))),
        const SizedBox(width: 12),
        Expanded(
          flex: 3,
          child: Text(value.isEmpty ? '—' : value,
              textAlign: TextAlign.end,
              style: emphasize ? text.titleMedium : text.bodyMedium?.copyWith(fontWeight: FontWeight.w600)),
        ),
      ]),
    );
  }
}

/// Ekranlarda kullanılan gecikmeli arama kutusu.
class SearchField extends StatefulWidget {
  const SearchField({super.key, required this.onChanged, this.hint = 'Ara', this.trailing});
  final ValueChanged<String> onChanged;
  final String hint;
  final Widget? trailing;

  @override
  State<SearchField> createState() => _SearchFieldState();
}

class _SearchFieldState extends State<SearchField> {
  final _controller = TextEditingController();
  Timer? _debounce;

  @override
  void dispose() {
    _debounce?.cancel();
    _controller.dispose();
    super.dispose();
  }

  void _changed(String v) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 350), () => widget.onChanged(v.trim()));
    setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    return TextField(
      controller: _controller,
      onChanged: _changed,
      textInputAction: TextInputAction.search,
      decoration: InputDecoration(
        hintText: widget.hint,
        prefixIcon: const Icon(Icons.search_rounded),
        contentPadding: const EdgeInsets.symmetric(vertical: 12),
        suffixIcon: Row(mainAxisSize: MainAxisSize.min, children: [
          if (_controller.text.isNotEmpty)
            IconButton(
              tooltip: 'Temizle',
              icon: const Icon(Icons.close_rounded),
              onPressed: () {
                _controller.clear();
                _changed('');
              },
            ),
          ?widget.trailing,
        ]),
      ),
    );
  }
}

/// Geniş ekranlarda (tablet, yatay) içerik genişliğini sınırlar.
class ContentWidth extends StatelessWidget {
  const ContentWidth({super.key, required this.child, this.max = 720});
  final Widget child;
  final double max;

  @override
  Widget build(BuildContext context) =>
      Center(child: ConstrainedBox(constraints: BoxConstraints(maxWidth: max), child: child));
}

/// Alt kısımda sabit eylem çubuğu (güvenli alanı dikkate alır).
class BottomActionBar extends StatelessWidget {
  const BottomActionBar({super.key, required this.children});
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      decoration: BoxDecoration(color: scheme.surface, border: Border(top: BorderSide(color: scheme.outlineVariant))),
      padding: EdgeInsets.fromLTRB(Gap.lg, Gap.md, Gap.lg, Gap.md + MediaQuery.of(context).padding.bottom),
      child: Row(children: [
        for (var i = 0; i < children.length; i++) ...[
          if (i > 0) const SizedBox(width: Gap.md),
          Expanded(child: children[i]),
        ],
      ]),
    );
  }
}

/// Belge durumlarını etikete ve tona çevirir.
class States {
  static Tone sale(String s) => switch (s) { 'sale' => Tone.success, 'sent' => Tone.info, 'cancel' => Tone.danger, _ => Tone.neutral };

  static Tone approval(String s) => switch (s) {
        'onaylandi' || 'approved' || 'validate' || 'paid' || 'posted' || 'in_payment' => Tone.success,
        'beklemede' || 'submitted' || 'confirm' || 'validate1' => Tone.warning,
        'reddedildi' || 'refused' || 'refuse' || 'iptal' || 'cancel' => Tone.danger,
        _ => Tone.neutral,
      };

  static (String, Tone) picking(String s) => switch (s) {
        'assigned' => ('Hazır', Tone.success),
        'confirmed' => ('Bekliyor', Tone.warning),
        'waiting' => ('Başka işlem bekliyor', Tone.neutral),
        'done' => ('Tamamlandı', Tone.success),
        'cancel' => ('İptal', Tone.danger),
        'progress' => ('Devam ediyor', Tone.info),
        'to_close' => ('Kapanacak', Tone.info),
        'draft' => ('Taslak', Tone.neutral),
        _ => (s, Tone.neutral),
      };
}
