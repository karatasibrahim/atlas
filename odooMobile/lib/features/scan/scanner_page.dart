import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import '../../core/theme.dart';

enum ScanTone { ok, warning, error }

class ScanFeedback {
  const ScanFeedback(this.message, this.tone);
  final String message;
  final ScanTone tone;
}

/// Tek okutma: kodu döndürür.
Future<String?> scanOnce(BuildContext context, {String title = 'Barkod / QR okut'}) {
  return Navigator.of(context).push<String>(
    MaterialPageRoute(fullscreenDialog: true, builder: (_) => ScannerPage(title: title)),
  );
}

/// Kamera tarayıcı. [onCode] verilirse sürekli modda çalışır ve her okutmanın sonucunu ekranda gösterir.
class ScannerPage extends StatefulWidget {
  const ScannerPage({super.key, this.title = 'Barkod / QR okut', this.onCode, this.subtitle});
  final String title;
  final String? subtitle;
  final Future<ScanFeedback> Function(String code)? onCode;

  @override
  State<ScannerPage> createState() => _ScannerPageState();
}

class _ScannerPageState extends State<ScannerPage> with SingleTickerProviderStateMixin {
  final _controller = MobileScannerController(detectionSpeed: DetectionSpeed.normal, returnImage: false);
  late final AnimationController _line = AnimationController(vsync: this, duration: const Duration(milliseconds: 1800))
    ..repeat(reverse: true);
  bool _busy = false, _done = false;
  String? _lastCode;
  DateTime _lastAt = DateTime(2000);
  ScanFeedback? _feedback;
  Timer? _feedbackTimer;
  int _count = 0;

  @override
  void dispose() {
    _feedbackTimer?.cancel();
    _line.dispose();
    _controller.dispose();
    super.dispose();
  }

  Future<void> _handle(String code) async {
    if (_busy || _done) return;
    final now = DateTime.now();
    // Aynı kod kamera önünde dururken tekrar tekrar okunmasın
    if (code == _lastCode && now.difference(_lastAt) < const Duration(milliseconds: 1800)) return;
    _lastCode = code;
    _lastAt = now;
    if (widget.onCode == null) {
      _done = true;
      HapticFeedback.mediumImpact();
      Navigator.of(context).pop(code);
      return;
    }
    setState(() => _busy = true);
    final fb = await widget.onCode!(code);
    if (!mounted) return;
    switch (fb.tone) {
      case ScanTone.ok:
        HapticFeedback.lightImpact();
        _count++;
      case ScanTone.warning:
        HapticFeedback.mediumImpact();
        _count++;
      case ScanTone.error:
        HapticFeedback.heavyImpact();
        SystemSound.play(SystemSoundType.alert);
    }
    _lastAt = DateTime.now();
    setState(() {
      _busy = false;
      _feedback = fb;
    });
    _feedbackTimer?.cancel();
    _feedbackTimer = Timer(const Duration(seconds: 4), () {
      if (mounted) setState(() => _feedback = null);
    });
  }

  Future<void> _manual() async {
    final controller = TextEditingController();
    final code = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Kodu elle gir'),
        content: TextField(
          controller: controller,
          autofocus: true,
          decoration: const InputDecoration(labelText: 'Barkod, seri veya belge no'),
          onSubmitted: (v) => Navigator.pop(ctx, v.trim()),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Vazgeç')),
          FilledButton(onPressed: () => Navigator.pop(ctx, controller.text.trim()), child: const Text('Tamam')),
        ],
      ),
    );
    if (code != null && code.isNotEmpty) {
      _lastCode = null;
      _handle(code);
    }
  }

  @override
  Widget build(BuildContext context) {
    final size = MediaQuery.of(context).size;
    final box = (size.width * .72).clamp(200.0, 340.0);
    final c = AtlasColors.of(context);
    return Scaffold(
      backgroundColor: Colors.black,
      extendBodyBehindAppBar: true,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        foregroundColor: Colors.white,
        systemOverlayStyle: SystemUiOverlayStyle.light,
        title: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(widget.title, style: const TextStyle(color: Colors.white, fontFamily: 'Lexend', fontSize: 18)),
          if (widget.subtitle != null)
            Text(widget.subtitle!, style: const TextStyle(color: Colors.white70, fontSize: 13), overflow: TextOverflow.ellipsis),
        ]),
        actions: [
          ValueListenableBuilder(
            valueListenable: _controller,
            builder: (context, value, _) => IconButton(
              tooltip: 'Fener',
              icon: Icon(value.torchState == TorchState.on ? Icons.flash_on_rounded : Icons.flash_off_rounded),
              onPressed: _controller.toggleTorch,
            ),
          ),
          IconButton(tooltip: 'Kamerayı çevir', icon: const Icon(Icons.cameraswitch_rounded), onPressed: _controller.switchCamera),
        ],
      ),
      body: Stack(fit: StackFit.expand, children: [
        MobileScanner(
          controller: _controller,
          onDetect: (capture) {
            final code = capture.barcodes.map((b) => b.rawValue).whereType<String>().firstOrNull;
            if (code != null && code.isNotEmpty) _handle(code);
          },
          errorBuilder: (context, error) => _CameraError(error: error, onManual: _manual),
        ),
        // Karartma ve okutma çerçevesi
        IgnorePointer(
          child: CustomPaint(painter: _OverlayPainter(box: box, color: Colors.black.withValues(alpha: .55))),
        ),
        IgnorePointer(
          child: Center(
            child: SizedBox(
              width: box,
              height: box,
              child: Stack(children: [
                CustomPaint(size: Size(box, box), painter: _CornerPainter(Colors.white)),
                AnimatedBuilder(
                  animation: _line,
                  builder: (_, _) => Positioned(
                    left: 16,
                    right: 16,
                    top: 12 + (box - 24) * _line.value,
                    child: Container(
                      height: 2,
                      decoration: BoxDecoration(
                        boxShadow: [BoxShadow(color: Theme.of(context).colorScheme.secondary, blurRadius: 12, spreadRadius: 1)],
                        color: Theme.of(context).colorScheme.secondary,
                      ),
                    ),
                  ),
                ),
                if (_busy) const Center(child: CircularProgressIndicator(color: Colors.white)),
              ]),
            ),
          ),
        ),
        Positioned(
          left: 16,
          right: 16,
          bottom: MediaQuery.of(context).padding.bottom + 24,
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            AnimatedSwitcher(
              duration: const Duration(milliseconds: 200),
              child: _feedback == null
                  ? Text(
                      widget.onCode == null ? 'Kodu çerçeveye hizalayın' : 'Okuttukça belgeye eklenir • $_count okutma',
                      key: const ValueKey('hint'),
                      style: const TextStyle(color: Colors.white, fontSize: 15),
                    )
                  : Container(
                      key: ValueKey(_feedback),
                      width: double.infinity,
                      padding: const EdgeInsets.all(14),
                      decoration: BoxDecoration(
                        color: switch (_feedback!.tone) { ScanTone.ok => c.success, ScanTone.warning => c.warning, ScanTone.error => c.danger },
                        borderRadius: BorderRadius.circular(14),
                      ),
                      child: Row(children: [
                        Icon(
                          switch (_feedback!.tone) {
                            ScanTone.ok => Icons.check_circle_rounded,
                            ScanTone.warning => Icons.warning_rounded,
                            ScanTone.error => Icons.cancel_rounded
                          },
                          color: Colors.white,
                        ),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Text(_feedback!.message,
                              style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w600, fontSize: 15)),
                        ),
                      ]),
                    ),
            ),
            const SizedBox(height: 16),
            Row(children: [
              Expanded(
                child: OutlinedButton.icon(
                  style: OutlinedButton.styleFrom(foregroundColor: Colors.white, side: const BorderSide(color: Colors.white54)),
                  onPressed: _manual,
                  icon: const Icon(Icons.keyboard_rounded),
                  label: const Text('Elle gir'),
                ),
              ),
              if (widget.onCode != null) ...[
                const SizedBox(width: 12),
                Expanded(
                  child: FilledButton.icon(
                    style: FilledButton.styleFrom(backgroundColor: Colors.white, foregroundColor: Colors.black),
                    onPressed: () => Navigator.pop(context),
                    icon: const Icon(Icons.done_rounded),
                    label: const Text('Bitti'),
                  ),
                ),
              ],
            ]),
          ]),
        ),
      ]),
    );
  }
}

class _CameraError extends StatelessWidget {
  const _CameraError({required this.error, required this.onManual});
  final MobileScannerException error;
  final VoidCallback onManual;

  @override
  Widget build(BuildContext context) {
    final denied = error.errorCode == MobileScannerErrorCode.permissionDenied;
    return Container(
      color: Colors.black,
      padding: const EdgeInsets.all(32),
      alignment: Alignment.center,
      child: Column(mainAxisSize: MainAxisSize.min, children: [
        const Icon(Icons.no_photography_rounded, color: Colors.white54, size: 56),
        const SizedBox(height: 16),
        Text(denied ? 'Kamera izni verilmedi' : 'Kamera açılamadı',
            style: const TextStyle(color: Colors.white, fontSize: 18, fontFamily: 'Lexend')),
        const SizedBox(height: 8),
        Text(
          denied ? 'Ayarlar > Atlas bölümünden kamera iznini açın veya kodu elle girin.' : 'Kodu elle girebilirsiniz.',
          style: const TextStyle(color: Colors.white70),
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: 20),
        FilledButton.tonal(onPressed: onManual, child: const Text('Kodu elle gir')),
      ]),
    );
  }
}

class _OverlayPainter extends CustomPainter {
  _OverlayPainter({required this.box, required this.color});
  final double box;
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final rect = Rect.fromCenter(center: size.center(Offset.zero), width: box, height: box);
    final path = Path()
      ..addRect(Offset.zero & size)
      ..addRRect(RRect.fromRectAndRadius(rect, const Radius.circular(24)))
      ..fillType = PathFillType.evenOdd;
    canvas.drawPath(path, Paint()..color = color);
  }

  @override
  bool shouldRepaint(covariant _OverlayPainter old) => old.box != box;
}

class _CornerPainter extends CustomPainter {
  _CornerPainter(this.color);
  final Color color;

  @override
  void paint(Canvas canvas, Size s) {
    final p = Paint()
      ..color = color
      ..strokeWidth = 4
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round;
    const l = 34.0, r = 24.0;
    final w = s.width, h = s.height;
    canvas.drawPath(Path()..moveTo(0, l)..lineTo(0, r)..arcToPoint(const Offset(r, 0), radius: const Radius.circular(r))..lineTo(l, 0), p);
    canvas.drawPath(Path()..moveTo(w - l, 0)..lineTo(w - r, 0)..arcToPoint(Offset(w, r), radius: const Radius.circular(r))..lineTo(w, l), p);
    canvas.drawPath(Path()..moveTo(w, h - l)..lineTo(w, h - r)..arcToPoint(Offset(w - r, h), radius: const Radius.circular(r))..lineTo(w - l, h), p);
    canvas.drawPath(Path()..moveTo(l, h)..lineTo(r, h)..arcToPoint(Offset(0, h - r), radius: const Radius.circular(r))..lineTo(0, h - l), p);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
