import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/api.dart';
import '../../core/format.dart';
import '../../core/session.dart';
import '../../core/theme.dart';
import '../../widgets/common.dart';
import '../scan/scanner_page.dart';
import 'doc_screen.dart';

/// İşlem türüne göre açık belgeler (veya sayım için lokasyonlar).
class DocListScreen extends StatefulWidget {
  const DocListScreen({super.key, required this.islem, required this.title});
  final String islem;
  final String title;

  @override
  State<DocListScreen> createState() => _DocListScreenState();
}

class _DocListScreenState extends State<DocListScreen> {
  String _search = '';
  final _key = GlobalKey<DataViewState<List>>();

  Future<void> _open(Map item) async {
    await Navigator.push(context,
        MaterialPageRoute(builder: (_) => DocScreen(islem: widget.islem, id: item['id'], title: item['ad'])));
    _key.currentState?.reload();
  }

  /// Belge/lokasyon QR'ını okutarak doğrudan aç.
  Future<void> _scanToOpen() async {
    final code = await scanOnce(context, title: widget.islem == 'sayim' ? 'Lokasyon okut' : 'Belge okut');
    if (code == null || !mounted) return;
    final info = await runAction(context, () async => Map<String, dynamic>.from(
        await context.read<AppState>().api.barkod('cozumle', {'code': code})));
    if (info == null || !mounted) return;
    final target = widget.islem == 'sayim' ? info['lokasyon'] : info['belge'];
    if (target == null) {
      showError(context, OdooException(widget.islem == 'sayim' ? 'Okutulan kod bir lokasyon değil.' : 'Okutulan kod bu işleme ait bir belge değil.'));
      return;
    }
    _open(target);
  }

  @override
  Widget build(BuildContext context) {
    final api = context.read<AppState>().api;
    final text = Theme.of(context).textTheme;
    final sayim = widget.islem == 'sayim';
    return Scaffold(
      appBar: AppBar(title: Text(widget.title), actions: [
        IconButton(tooltip: sayim ? 'Lokasyon okut' : 'Belge okut', onPressed: _scanToOpen, icon: const Icon(Icons.qr_code_scanner_rounded)),
      ]),
      body: Column(children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(Gap.lg, Gap.sm, Gap.lg, Gap.sm),
          child: SearchField(hint: sayim ? 'Lokasyon ara' : 'Belge no, cari veya kaynak ara', onChanged: (v) {
            setState(() => _search = v);
            _key.currentState?.reload();
          }),
        ),
        Expanded(
          child: DataView<List>(
            key: _key,
            load: () async => (await api.barkod('belge_listesi', {'islem': widget.islem, 'arama': _search})) as List,
            builder: (context, items, _) {
              final filtered = sayim && _search.isNotEmpty
                  ? items.where((i) => '${i['ad']} ${i['alt']}'.toLowerCase().contains(_search.toLowerCase())).toList()
                  : items;
              if (filtered.isEmpty) {
                return EmptyState(
                  icon: Icons.inbox_rounded,
                  title: 'Bekleyen iş yok',
                  message: sayim ? 'Lokasyon bulunamadı.' : 'Bu işlem için açık belge bulunmuyor.',
                );
              }
              return ListView.separated(
                padding: const EdgeInsets.fromLTRB(Gap.lg, Gap.sm, Gap.lg, Gap.xxl),
                itemCount: filtered.length,
                separatorBuilder: (_, _) => const SizedBox(height: Gap.sm),
                itemBuilder: (context, i) {
                  final it = filtered[i] as Map;
                  final (label, tone) = States.picking(it['durum'] ?? '');
                  return AppCard(
                    onTap: () => _open(it),
                    child: Row(children: [
                      Expanded(
                        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                          Text(it['ad'], style: text.titleSmall),
                          if ((it['alt'] ?? '') != '') ...[
                            const SizedBox(height: 2),
                            Text(it['alt'], style: text.bodyMedium, maxLines: 1, overflow: TextOverflow.ellipsis),
                          ],
                          if ((it['bilgi'] ?? '') != '' || (it['tarih'] ?? '') != '') ...[
                            const SizedBox(height: 4),
                            Text([it['bilgi'], if ((it['tarih'] ?? '') != '') Fmt.date(it['tarih'])].where((s) => s != '').join('  •  '),
                                style: text.bodySmall),
                          ],
                        ]),
                      ),
                      if (!sayim) StatusChip(label, tone: tone),
                      if (sayim) const Icon(Icons.chevron_right_rounded),
                    ]),
                  );
                },
              );
            },
          ),
        ),
      ]),
    );
  }
}
