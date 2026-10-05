import { _t } from "@web/core/l10n/translation";
import { addSpreadsheetActionLazyLoader } from "@spreadsheet/assets_backend/spreadsheet_action_loader";

// o-spreadsheet paketi ilk açılışta yüklenir; asıl eylem paket içinde (bundle/editor.js) tanımlıdır
addSpreadsheetActionLazyLoader("atlas_tablo.duzenle", "tablo", _t("Hesap Tablosu"));
