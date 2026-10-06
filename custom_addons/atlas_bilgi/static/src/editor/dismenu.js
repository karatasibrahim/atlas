import { Component, xml } from "@odoo/owl";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { registry } from "@web/core/registry";
import { AtlasBilgiKayit, AtlasBilgiMakaleSec } from "./diyalog";

const MODEL = "atlas.bilgi.makale";

/** Liste / kanban dişli menüsü: görünümü (filtreleriyle) bir makaleye göm — Enterprise "Insert in Knowledge" */
export class AtlasBilgiGorunumuEkle extends Component {
    static template = xml`<DropdownItem class="'o_ab_dismenu_gorunum'" onSelected.bind="this.ac">
        <i class="oi me-1" data-icon="description"/>Bilgi Bankası makalesine ekle</DropdownItem>`;
    static components = { DropdownItem };

    setup() {
        // Menü kapanınca bu bileşen yok olur; useService çağrıları o zaman hiç dönmez. Servisler doğrudan kullanılır.
        const servisler = this.env.services;
        this.dialog = servisler.dialog;
        this.orm = servisler.orm;
        this.action = servisler.action;
        this.notification = servisler.notification;
    }

    ac() {
        const { domain } = this.env.searchModel;
        const { groupBys } = this.env.searchModel.getPreFavoriteValues();
        const ad = this.env.config.getDisplayName?.() || "";
        this.dialog.add(AtlasBilgiMakaleSec, {
            baslik: "Görünümü makaleye ekle",
            adGerekli: true,
            varsayilanAd: ad,
            onSec: async (makale, baslik) => {
                try {
                    const eylem = await this.orm.call(MODEL, "gorunum_ekle", [[makale.id], this.env.config.actionId, this.env.config.viewType,
                                                                              baslik || ad, domain, { group_by: groupBys }]);
                    this.action.doAction(eylem);
                } catch (h) {
                    this.notification.add(h?.data?.message || String(h), { type: "danger" });
                }
            },
        });
    }
}

/** Form dişli menüsü: bu kayıt için Bilgi Bankası (bağlı makaleler, arama, mesaj olarak ekleme) */
export class AtlasBilgiKayitMenu extends Component {
    static template = xml`<DropdownItem class="'o_ab_dismenu_kayit'" onSelected.bind="this.ac">
        <i class="oi me-1" data-icon="description"/>Bilgi Bankası</DropdownItem>`;
    static components = { DropdownItem };

    setup() {
        this.dialog = this.env.services.dialog;
    }

    ac() {
        const kayit = this.env.model.root;
        this.dialog.add(AtlasBilgiKayit, { resModel: kayit.resModel, resId: kayit.resId });
    }
}

registry.category("cogMenu").add("atlas-bilgi-gorunum-ekle", {
    Component: AtlasBilgiGorunumuEkle,
    groupNumber: 10,
    isDisplayed: ({ config }) => config.actionType === "ir.actions.act_window" && config.actionId && ["list", "kanban"].includes(config.viewType),
}, { sequence: 15 });

registry.category("cogMenu").add("atlas-bilgi-kayit", {
    Component: AtlasBilgiKayitMenu,
    groupNumber: 10,
    isDisplayed: (env) => env.config.viewType === "form" && Boolean(env.model?.root?.resId) && env.model.root.resModel !== MODEL,
}, { sequence: 16 });
