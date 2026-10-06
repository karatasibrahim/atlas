import { Plugin } from "@html_editor/plugin";
import { withSequence } from "@html_editor/utils/resource";
import { _t } from "@web/core/l10n/translation";
import { AtlasBilgiGorunumSec, AtlasBilgiMakaleSec, AtlasBilgiYorumYaz } from "./diyalog";

const MODEL = "atlas.bilgi.makale";
const GOMULULER = ["atlasBilgiGorunum", "atlasBilgiAltSayfalar", "atlasBilgiYorum"];

/**
 * Bilgi Bankası düzenleyici eklentisi (Enterprise knowledge editör komutlarının eşleniği):
 * /Liste görünümü, /Kanban görünümü, /Alt sayfalar, /Makale bağlantısı ve seçili metne yorum.
 */
export class AtlasBilgiPlugin extends Plugin {
    static id = "atlasBilgi";
    static dependencies = ["dom", "history", "selection", "embeddedComponents"];

    resources = {
        user_commands: [
            { id: "atlasBilgiListe", title: _t("Liste görünümü"), description: _t("Bir menünün kayıtlarını liste olarak göm"),
              icon: "view_list", run: () => this.gorunumSec("list") },
            { id: "atlasBilgiKanban", title: _t("Kanban görünümü"), description: _t("Bir menünün kayıtlarını kanban olarak göm"),
              icon: "table_view", run: () => this.gorunumSec("kanban") },
            { id: "atlasBilgiAltSayfalar", title: _t("Alt sayfalar"), description: _t("Bu makalenin alt sayfalarını listele"),
              icon: "account_tree", run: () => this.altSayfalar() },
            { id: "atlasBilgiMakaleBag", title: _t("Makale bağlantısı"), description: _t("Başka bir makaleye bağlantı ekle"),
              icon: "link", run: () => this.makaleBaglantisi() },
            { id: "atlasBilgiYorum", title: _t("Yorum"), description: _t("Seçili metne yorum ekle"), icon: "add_comment",
              run: () => this.yorumEkle() },
        ],
        powerbox_categories: withSequence(25, { id: "atlas_bilgi", name: _t("Bilgi Bankası") }),
        powerbox_items: [
            { categoryId: "atlas_bilgi", commandId: "atlasBilgiListe" },
            { categoryId: "atlas_bilgi", commandId: "atlasBilgiKanban" },
            { categoryId: "atlas_bilgi", commandId: "atlasBilgiAltSayfalar" },
            { categoryId: "atlas_bilgi", commandId: "atlasBilgiMakaleBag" },
        ],
        toolbar_groups: withSequence(95, { id: "atlas_bilgi_yorum", namespaces: ["compact", "expanded"] }),
        toolbar_items: [{ id: "atlas_bilgi_yorum", groupId: "atlas_bilgi_yorum", commandId: "atlasBilgiYorum", description: _t("Yorum ekle") }],
        on_will_mount_component_handlers: ({ name, props }) => {
            if (GOMULULER.includes(name)) {
                props.makaleId = this.makaleId;
            }
        },
    };

    get makaleId() {
        return this.config.getRecordInfo?.().resId || false;
    }

    /** Gömülü bileşen yer tutucusunu imlecin olduğu yere ekler */
    gomuluEkle(ad, props, satirIci = false) {
        const el = this.document.createElement(satirIci ? "span" : "div");
        el.dataset.embedded = ad;
        el.dataset.oeProtected = "true";
        el.setAttribute("contenteditable", "false");
        el.dataset.embeddedProps = JSON.stringify(props);
        const parca = this.document.createDocumentFragment();
        parca.append(el);
        this.dependencies.dom.insert(parca);
        this.dependencies.history.commit();
    }

    gorunumSec(tur) {
        const secim = this.dependencies.selection.preserveSelection();
        this.services.dialog.add(AtlasBilgiGorunumSec, {
            tur,
            onSec: (s) => {
                secim.restore();
                this.gomuluEkle("atlasBilgiGorunum", { eylem_id: s.eylem_id, tur: s.tur, ad: s.ad });
            },
        });
    }

    altSayfalar() {
        this.gomuluEkle("atlasBilgiAltSayfalar", { makale_id: this.makaleId });
    }

    makaleBaglantisi() {
        const secim = this.dependencies.selection.preserveSelection();
        this.services.dialog.add(AtlasBilgiMakaleSec, {
            baslik: _t("Makale bağlantısı"),
            onSec: (m) => {
                secim.restore();
                const a = this.document.createElement("a");
                a.href = `/odoo/atlas.bilgi.makale/${m.id}`;
                a.textContent = `${m.simge || "📄"} ${m.ad}`;
                a.className = "o_ab_makale_bag";
                const parca = this.document.createDocumentFragment();
                parca.append(a, this.document.createTextNode(" "));
                this.dependencies.dom.insert(parca);
                this.dependencies.history.commit();
            },
        });
    }

    yorumEkle() {
        const secim = this.dependencies.selection.getEditableSelection();
        const metin = secim.isCollapsed ? "" : this.document.getSelection().toString();
        if (!metin.trim()) {
            this.services.notification.add(_t("Yorum için önce metin seçin."), { type: "info" });
            return;
        }
        if (!this.makaleId) {
            this.services.notification.add(_t("Önce makaleyi kaydedin."), { type: "warning" });
            return;
        }
        const son = { node: secim.endContainer, offset: secim.endOffset };
        this.services.dialog.add(AtlasBilgiYorumYaz, {
            metin,
            onKaydet: async (mesaj) => {
                const yorum = await this.services.orm.call(MODEL, "yorum_olustur", [[this.makaleId], metin, mesaj]);
                this.dependencies.selection.setSelection({ anchorNode: son.node, anchorOffset: son.offset });
                this.gomuluEkle("atlasBilgiYorum", { yorum_id: yorum.id }, true);
            },
        });
    }
}
