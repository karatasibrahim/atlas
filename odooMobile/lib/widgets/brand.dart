import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../core/theme.dart';

/// Atlas amblemi: yuvarlatılmış kare içinde dağ/A biçimli işaret ve yörünge.
class AtlasLogo extends StatelessWidget {
  const AtlasLogo({super.key, this.size = 56, this.light = false, this.showText = true});
  final double size;
  final bool light;
  final bool showText;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final fg = light ? Colors.white : scheme.primary;
    return Semantics(
      label: 'Atlas',
      child: Column(mainAxisSize: MainAxisSize.min, children: [
        Container(
          width: size,
          height: size,
          decoration: BoxDecoration(
            color: light ? Colors.white.withValues(alpha: .14) : scheme.primary.withValues(alpha: .1),
            borderRadius: BorderRadius.circular(size * .3),
            border: Border.all(color: fg.withValues(alpha: .35), width: 1.2),
          ),
          child: CustomPaint(painter: _MarkPainter(fg)),
        ),
        if (showText) ...[
          SizedBox(height: size * .22),
          Text('ATLAS',
              style: TextStyle(
                  fontFamily: 'Lexend', fontWeight: FontWeight.w700, fontSize: size * .3, letterSpacing: size * .08, color: fg)),
        ],
      ]),
    );
  }
}

class _MarkPainter extends CustomPainter {
  _MarkPainter(this.color);
  final Color color;

  @override
  void paint(Canvas canvas, Size s) {
    final p = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = s.width * .075
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round;
    final path = Path()
      ..moveTo(s.width * .24, s.height * .72)
      ..lineTo(s.width * .5, s.height * .26)
      ..lineTo(s.width * .76, s.height * .72);
    canvas.drawPath(path, p);
    canvas.drawLine(Offset(s.width * .36, s.height * .56), Offset(s.width * .64, s.height * .56), p);
    final orbit = Paint()
      ..color = color.withValues(alpha: .55)
      ..style = PaintingStyle.stroke
      ..strokeWidth = s.width * .035;
    canvas.save();
    canvas.translate(s.width / 2, s.height * .52);
    canvas.rotate(-math.pi / 9);
    canvas.drawOval(Rect.fromCenter(center: Offset.zero, width: s.width * .78, height: s.height * .26), orbit);
    canvas.restore();
  }

  @override
  bool shouldRepaint(covariant _MarkPainter old) => old.color != color;
}

/// Marka renkli degrade başlık alanı (dekoratif daireli).
class HeroBackground extends StatelessWidget {
  const HeroBackground({super.key, required this.child, this.radius = 28});
  final Widget child;
  final double radius;

  @override
  Widget build(BuildContext context) {
    final c = AtlasColors.of(context);
    return ClipRRect(
      borderRadius: BorderRadius.vertical(bottom: Radius.circular(radius)),
      child: Container(
        decoration: BoxDecoration(
          gradient: LinearGradient(colors: [c.heroStart, c.heroEnd], begin: Alignment.topLeft, end: Alignment.bottomRight),
        ),
        child: Stack(children: [
          Positioned(right: -60, top: -40, child: _circle(200, .08)),
          Positioned(right: 60, bottom: -90, child: _circle(160, .06)),
          Positioned(left: -40, bottom: -50, child: _circle(120, .05)),
          child,
        ]),
      ),
    );
  }

  Widget _circle(double size, double alpha) => IgnorePointer(
        child: Container(
            width: size, height: size, decoration: BoxDecoration(shape: BoxShape.circle, color: Colors.white.withValues(alpha: alpha))),
      );
}
