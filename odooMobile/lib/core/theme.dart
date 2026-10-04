import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

/// Uygulama renk temaları. Odoo'nun kurumsal renkleri esas alınmıştır.
enum AtlasPalette {
  odoo('Odoo Patlıcan', Color(0xFF714B67), Color(0xFFC79BBD), Color(0xFF017E84)),
  community('Odoo Community', Color(0xFF5E5398), Color(0xFFB4A9E6), Color(0xFF017E84)),
  turkuaz('Odoo Turkuaz', Color(0xFF017E84), Color(0xFF5CC8CE), Color(0xFF714B67)),
  lacivert('Atlas Lacivert', Color(0xFF1E3A8A), Color(0xFF93B4F5), Color(0xFF16A34A));

  const AtlasPalette(this.label, this.primary, this.primaryDark, this.accent);
  final String label;
  final Color primary;
  final Color primaryDark;
  final Color accent;
}

/// Anlamsal renkler (durumlar). Renk tek başına anlam taşımaz; her zaman etiketle birlikte kullanılır.
@immutable
class AtlasColors extends ThemeExtension<AtlasColors> {
  const AtlasColors({
    required this.success,
    required this.successContainer,
    required this.warning,
    required this.warningContainer,
    required this.danger,
    required this.dangerContainer,
    required this.info,
    required this.infoContainer,
    required this.neutralContainer,
    required this.heroStart,
    required this.heroEnd,
    required this.accent,
    required this.muted,
    required this.border,
  });

  final Color success, successContainer, warning, warningContainer, danger, dangerContainer;
  final Color info, infoContainer, neutralContainer, heroStart, heroEnd, accent, muted, border;

  static AtlasColors of(BuildContext context) => Theme.of(context).extension<AtlasColors>()!;

  @override
  AtlasColors copyWith() => this;

  @override
  AtlasColors lerp(ThemeExtension<AtlasColors>? other, double t) {
    if (other is! AtlasColors) return this;
    Color l(Color a, Color b) => Color.lerp(a, b, t)!;
    return AtlasColors(
      success: l(success, other.success),
      successContainer: l(successContainer, other.successContainer),
      warning: l(warning, other.warning),
      warningContainer: l(warningContainer, other.warningContainer),
      danger: l(danger, other.danger),
      dangerContainer: l(dangerContainer, other.dangerContainer),
      info: l(info, other.info),
      infoContainer: l(infoContainer, other.infoContainer),
      neutralContainer: l(neutralContainer, other.neutralContainer),
      heroStart: l(heroStart, other.heroStart),
      heroEnd: l(heroEnd, other.heroEnd),
      accent: l(accent, other.accent),
      muted: l(muted, other.muted),
      border: l(border, other.border),
    );
  }
}

/// Boşluk ve köşe ölçüleri (4/8 ritmi).
class Gap {
  static const double xs = 4, sm = 8, md = 12, lg = 16, xl = 24, xxl = 32;
  static const double radius = 16, radiusSm = 12, radiusLg = 24;
}

class AtlasTheme {
  static const _headFont = 'Lexend';
  static const _bodyFont = 'SourceSans3';

  static ThemeData build(AtlasPalette palette, Brightness brightness) {
    final dark = brightness == Brightness.dark;
    final primary = dark ? palette.primaryDark : palette.primary;
    final scheme = ColorScheme.fromSeed(seedColor: palette.primary, brightness: brightness).copyWith(
      primary: primary,
      onPrimary: dark ? const Color(0xFF1B1020) : Colors.white,
      secondary: palette.accent,
      surface: dark ? const Color(0xFF12131A) : const Color(0xFFFFFFFF),
      surfaceContainerLowest: dark ? const Color(0xFF0B0C11) : const Color(0xFFF6F7FB),
      surfaceContainerLow: dark ? const Color(0xFF181A22) : const Color(0xFFF1F3F8),
      surfaceContainer: dark ? const Color(0xFF1E2029) : const Color(0xFFEBEEF4),
      onSurface: dark ? const Color(0xFFF1F2F6) : const Color(0xFF111827),
      onSurfaceVariant: dark ? const Color(0xFFA9AEBC) : const Color(0xFF4B5563),
      outlineVariant: dark ? const Color(0xFF2C2F3A) : const Color(0xFFE2E5EC),
      error: dark ? const Color(0xFFF87171) : const Color(0xFFDC2626),
    );

    final colors = AtlasColors(
      success: dark ? const Color(0xFF4ADE80) : const Color(0xFF15803D),
      successContainer: dark ? const Color(0xFF12301E) : const Color(0xFFDCFCE7),
      warning: dark ? const Color(0xFFFBBF24) : const Color(0xFFB45309),
      warningContainer: dark ? const Color(0xFF3A2A0B) : const Color(0xFFFEF3C7),
      danger: dark ? const Color(0xFFF87171) : const Color(0xFFDC2626),
      dangerContainer: dark ? const Color(0xFF3B1414) : const Color(0xFFFEE2E2),
      info: dark ? const Color(0xFF38BDF8) : const Color(0xFF0369A1),
      infoContainer: dark ? const Color(0xFF0C2C3E) : const Color(0xFFE0F2FE),
      neutralContainer: dark ? const Color(0xFF262833) : const Color(0xFFF1F3F8),
      heroStart: dark ? Color.lerp(palette.primary, Colors.black, .35)! : palette.primary,
      heroEnd: dark ? Color.lerp(palette.accent, Colors.black, .45)! : Color.lerp(palette.primary, palette.accent, .55)!,
      accent: palette.accent,
      muted: scheme.onSurfaceVariant,
      border: scheme.outlineVariant,
    );

    final base = ThemeData(useMaterial3: true, colorScheme: scheme, brightness: brightness, fontFamily: _bodyFont);
    final t = base.textTheme;
    TextStyle? h(TextStyle? s, FontWeight w, [double ls = -0.2]) =>
        s?.copyWith(fontFamily: _headFont, fontWeight: w, letterSpacing: ls, color: scheme.onSurface);
    final text = t.copyWith(
      displaySmall: h(t.displaySmall, FontWeight.w600, -0.8),
      headlineMedium: h(t.headlineMedium, FontWeight.w600, -0.6),
      headlineSmall: h(t.headlineSmall, FontWeight.w600, -0.4),
      titleLarge: h(t.titleLarge, FontWeight.w600),
      titleMedium: h(t.titleMedium, FontWeight.w500, -0.1),
      titleSmall: h(t.titleSmall, FontWeight.w500, 0),
      bodyLarge: t.bodyLarge?.copyWith(fontSize: 16, height: 1.45, color: scheme.onSurface),
      bodyMedium: t.bodyMedium?.copyWith(fontSize: 15, height: 1.45, color: scheme.onSurface),
      bodySmall: t.bodySmall?.copyWith(fontSize: 13, height: 1.4, color: scheme.onSurfaceVariant),
      labelLarge: t.labelLarge?.copyWith(fontSize: 15, fontWeight: FontWeight.w600, letterSpacing: 0.1),
      labelMedium: t.labelMedium?.copyWith(fontSize: 13, fontWeight: FontWeight.w600),
      labelSmall: t.labelSmall?.copyWith(fontSize: 12, fontWeight: FontWeight.w600, letterSpacing: 0.2),
    );

    final rounded = RoundedRectangleBorder(borderRadius: BorderRadius.circular(Gap.radiusSm));
    return base.copyWith(
      textTheme: text,
      extensions: [colors],
      scaffoldBackgroundColor: scheme.surfaceContainerLowest,
      splashFactory: InkSparkle.splashFactory,
      appBarTheme: AppBarTheme(
        backgroundColor: scheme.surfaceContainerLowest,
        surfaceTintColor: Colors.transparent,
        scrolledUnderElevation: 0.5,
        elevation: 0,
        centerTitle: false,
        titleTextStyle: text.titleLarge,
        foregroundColor: scheme.onSurface,
        systemOverlayStyle: dark ? SystemUiOverlayStyle.light : SystemUiOverlayStyle.dark,
      ),
      cardTheme: CardThemeData(
        color: scheme.surface,
        elevation: 0,
        margin: EdgeInsets.zero,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(Gap.radius),
          side: BorderSide(color: scheme.outlineVariant),
        ),
      ),
      dividerTheme: DividerThemeData(color: scheme.outlineVariant, space: 1, thickness: 1),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(minimumSize: const Size(48, 52), shape: rounded, textStyle: text.labelLarge),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
            minimumSize: const Size(48, 52), shape: rounded, textStyle: text.labelLarge, side: BorderSide(color: scheme.outlineVariant)),
      ),
      textButtonTheme: TextButtonThemeData(style: TextButton.styleFrom(minimumSize: const Size(48, 44), textStyle: text.labelLarge)),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: dark ? scheme.surfaceContainer : scheme.surface,
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
        border: OutlineInputBorder(borderRadius: BorderRadius.circular(Gap.radiusSm), borderSide: BorderSide(color: scheme.outlineVariant)),
        enabledBorder:
            OutlineInputBorder(borderRadius: BorderRadius.circular(Gap.radiusSm), borderSide: BorderSide(color: scheme.outlineVariant)),
        focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(Gap.radiusSm), borderSide: BorderSide(color: primary, width: 2)),
        labelStyle: TextStyle(color: scheme.onSurfaceVariant),
      ),
      chipTheme: base.chipTheme.copyWith(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
        side: BorderSide(color: scheme.outlineVariant),
        labelStyle: text.labelMedium,
      ),
      navigationBarTheme: NavigationBarThemeData(
        height: 68,
        backgroundColor: scheme.surface,
        surfaceTintColor: Colors.transparent,
        indicatorColor: primary.withValues(alpha: dark ? .22 : .12),
        labelTextStyle: WidgetStateProperty.resolveWith((s) => text.labelSmall?.copyWith(
            color: s.contains(WidgetState.selected) ? primary : scheme.onSurfaceVariant)),
        iconTheme: WidgetStateProperty.resolveWith(
            (s) => IconThemeData(color: s.contains(WidgetState.selected) ? primary : scheme.onSurfaceVariant, size: 24)),
      ),
      bottomSheetTheme: BottomSheetThemeData(
        backgroundColor: scheme.surface,
        surfaceTintColor: Colors.transparent,
        showDragHandle: true,
        shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(Gap.radiusLg))),
      ),
      dialogTheme: DialogThemeData(
        backgroundColor: scheme.surface,
        surfaceTintColor: Colors.transparent,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(Gap.radiusLg)),
      ),
      snackBarTheme: SnackBarThemeData(
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(Gap.radiusSm)),
      ),
      segmentedButtonTheme: SegmentedButtonThemeData(
        style: SegmentedButton.styleFrom(
          selectedBackgroundColor: primary.withValues(alpha: dark ? .25 : .12),
          selectedForegroundColor: primary,
          side: BorderSide(color: scheme.outlineVariant),
        ),
      ),
      pageTransitionsTheme: const PageTransitionsTheme(builders: {
        TargetPlatform.android: PredictiveBackPageTransitionsBuilder(),
        TargetPlatform.iOS: CupertinoPageTransitionsBuilder(),
      }),
    );
  }
}
