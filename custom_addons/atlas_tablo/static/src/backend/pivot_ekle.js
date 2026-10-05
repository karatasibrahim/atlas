import { Component, xml } from "@odoo/owl";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

/** Pivot görünümünün dişli menüsü: "Hesap Tablosuna Ekle" (Enterprise "Insert in Spreadsheet" eşleniği) */
export class AtlasTabloPivotEkle extends Component {
    static template = xml`<DropdownItem class="'o_atlas_tablo_pivot_ekle'" onSelected.bind="this.ekle">
        <i class="oi me-1" data-icon="table_view"/>Hesap Tablosuna Ekle</DropdownItem>`;
    static components = { DropdownItem };

    setup() {
        this.action = useService("action");
    }

    ekle() {
        // Pivot kontrolcüsü ayarlarını getContext ile verir (Panoya Ekle ile aynı yol)
        const { context } = this.env.searchModel.getPreFavoriteValues();
        const baglam = { ...(this.env.searchModel.context || {}) };
        for (const anahtar of Object.keys(baglam)) {
            if (anahtar.startsWith("search_default_") || anahtar.startsWith("pivot_") || anahtar === "params") {
                delete baglam[anahtar];
            }
        }
        this.action.doAction({
            type: "ir.actions.client",
            tag: "atlas_tablo.duzenle",
            params: {
                yeni_pivot: {
                    resModel: this.env.searchModel.resModel,
                    rowGroupBys: context.pivot_row_groupby || [],
                    colGroupBys: context.pivot_column_groupby || [],
                    activeMeasures: context.pivot_measures || ["__count"],
                    domain: this.env.searchModel.domain,
                    context: baglam,
                    ad: this.env.config.getDisplayName?.() || this.env.searchModel.resModel,
                },
            },
        });
    }
}

registry.category("cogMenu").add(
    "atlas-tablo-pivot-ekle",
    {
        Component: AtlasTabloPivotEkle,
        groupNumber: 20,
        isDisplayed: (env) => env.config.viewType === "pivot" && Boolean(env.searchModel?.resModel),
    },
    { sequence: 50 }
);
