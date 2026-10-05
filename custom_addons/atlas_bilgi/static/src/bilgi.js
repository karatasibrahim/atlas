import { Component, onMounted, onWillStart, proxy, t, useProps } from "@odoo/owl";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { registry } from "@web/core/registry";
import { imageUrl } from "@web/core/utils/urls";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { HistoryDialog } from "@html_editor/components/history_dialog/history_dialog";
import { getHtmlFieldMetadata, setHtmlFieldMetadata } from "@html_editor/fields/html_field";

const MODEL = "atlas.bilgi.makale";
const widgetProps = { record: t.object(), readonly: t.boolean().optional() };

function hataMetni(h) {
    return h?.data?.message || h?.message || String(h);
}

/** Başka makaleye geçiş: önce kaydet, sonra aynı ekranda (geçmişi büyütmeden) aç. */
async function makaleAc(env, record, id) {
    if (record.resId === id) {
        return;
    }
    if (record.isDirty) {
        await record.save();
    }
    const eylem = await env.services.orm.call(MODEL, "action_ac", [[id]]);
    return env.services.action.doAction(eylem, { stackPosition: "replaceCurrentAction" });
}

// ============================================================================ kenar çubuğu
export class AtlasBilgiKenar extends Component {
    static template = "atlas_bilgi.Kenar";
    props = useProps(widgetProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.surukle = null;
        this.state = proxy({
            veri: null,
            acik: {},
            cocuklar: {},
            arama: "",
            sonuclar: [],
            hedef: null,
            sablonlar: null,
        });
        onWillStart(() => this.yukle());
        // Makale adresiyle (ya da makaleler arası geçişte) açılınca üst çubukta Bilgi Bankası uygulaması seçili kalsın
        const menu = useService("menu");
        onMounted(() => {
            const uygulama = menu.getAll().find((m) => m.xmlid === "atlas_bilgi.menu_atlas_bilgi_root");
            if (uygulama && menu.getCurrentApp()?.id !== uygulama.id) {
                menu.setCurrentMenu(uygulama);
            }
        });
    }

    get resId() {
        return this.props.record.resId;
    }

    async yukle() {
        const veri = await this.orm.call(MODEL, "kenar_verisi", [this.resId || false]);
        const acik = { ...this.state.acik };
        for (const id of veri.zincir.slice(0, -1)) {
            acik[id] = true;
        }
        const cocuklar = {};
        await Promise.all(
            Object.keys(acik)
                .filter((id) => acik[id])
                .map(async (id) => {
                    cocuklar[id] = await this.orm.call(MODEL, "alt_makaleler", [parseInt(id, 10)]);
                })
        );
        this.state.cocuklar = cocuklar;
        this.state.acik = acik;
        this.state.veri = veri;
    }

    ad(d) {
        return d.id === this.resId ? this.props.record.data.name || "Adsız" : d.ad || "Adsız";
    }

    simge(d) {
        return (d.id === this.resId ? this.props.record.data.simge : d.simge) || "📄";
    }

    async ackapa(d, ev) {
        ev?.stopPropagation();
        if (this.state.acik[d.id]) {
            this.state.acik[d.id] = false;
            return;
        }
        this.state.cocuklar[d.id] = await this.orm.call(MODEL, "alt_makaleler", [d.id]);
        this.state.acik[d.id] = true;
    }

    git(id) {
        return makaleAc(this.env, this.props.record, id).catch((h) => this.notification.add(hataMetni(h), { type: "danger" }));
    }

    async yeni(ustId, kategori, ev) {
        ev?.stopPropagation();
        try {
            if (this.props.record.isDirty) {
                await this.props.record.save();
            }
            const id = await this.orm.call(MODEL, "yeni_makale", [ustId || false, kategori || "calisma"]);
            await this.git(id);
        } catch (h) {
            this.notification.add(hataMetni(h), { type: "danger" });
        }
    }

    // ---------------------------------------------------------------- arama
    async ara(ev) {
        this.state.arama = ev.target.value;
        clearTimeout(this._zaman);
        this._zaman = setTimeout(async () => {
            this.state.sonuclar = this.state.arama.trim().length >= 2 ? await this.orm.call(MODEL, "ara", [this.state.arama.trim()]) : [];
        }, 250);
    }

    sonucAc(s) {
        this.state.arama = "";
        this.state.sonuclar = [];
        return this.git(s.id);
    }

    // ---------------------------------------------------------------- şablonlar ve çöp
    async sablonAc() {
        const liste = await this.orm.call(MODEL, "sablonlar", []);
        const gruplar = {};
        for (const s of liste) {
            (gruplar[s.kategori] ||= []).push(s);
        }
        this.state.sablonlar = Object.entries(gruplar);
    }

    async sablonSec(s) {
        this.state.sablonlar = null;
        try {
            const id = await this.orm.call(MODEL, "yeni_makale", [false, "calisma", s.id]);
            await this.git(id);
        } catch (h) {
            this.notification.add(hataMetni(h), { type: "danger" });
        }
    }

    copAc() {
        return this.action.doAction("atlas_bilgi.action_atlas_bilgi_cop");
    }

    // ---------------------------------------------------------------- sürükle-bırak
    basla(d, ust, ev) {
        ev.stopPropagation();
        this.surukle = { id: d.id, ust };
        ev.dataTransfer.effectAllowed = "move";
        ev.dataTransfer.setData("text/plain", String(d.id));
    }

    uzerinde(d, ust, kardesler, ev) {
        if (!this.surukle || this.surukle.id === d.id) {
            return;
        }
        ev.preventDefault();
        ev.stopPropagation();
        const r = ev.currentTarget.getBoundingClientRect();
        const oran = (ev.clientY - r.top) / r.height;
        const konum = oran < 0.28 ? "once" : oran > 0.72 ? "sonra" : "ic";
        if (this.state.hedef?.id !== d.id || this.state.hedef?.konum !== konum) {
            this.state.hedef = { id: d.id, konum, ust, kardesler, kategori: d.kategori };
        }
    }

    bolumUzerinde(kategori, ev) {
        if (!this.surukle) {
            return;
        }
        ev.preventDefault();
        this.state.hedef = { bolum: kategori };
    }

    async birak(ev) {
        ev.preventDefault();
        ev.stopPropagation();
        const h = this.state.hedef;
        const s = this.surukle;
        this.state.hedef = null;
        this.surukle = null;
        if (!h || !s) {
            return;
        }
        let ust = false;
        let once = false;
        let kategori = false;
        if (h.bolum) {
            kategori = h.bolum;
        } else if (h.konum === "ic") {
            ust = h.id;
        } else {
            ust = h.ust || false;
            kategori = h.kategori;
            const ids = h.kardesler.map((k) => k.id).filter((id) => id !== s.id);
            const i = ids.indexOf(h.id);
            once = h.konum === "once" ? h.id : ids[i + 1] || false;
        }
        try {
            await this.orm.call(MODEL, "makale_tasi", [s.id, ust, kategori, once]);
            if (ust) {
                this.state.acik[ust] = true;
            }
            await this.yukle();
            if (s.id === this.resId) {
                await this.props.record.load();
            }
        } catch (hata) {
            this.notification.add(hataMetni(hata), { type: "danger" });
        }
    }

    bitti() {
        this.state.hedef = null;
        this.surukle = null;
    }

    hedefSinif(d) {
        const h = this.state.hedef;
        return h && h.id === d.id ? `o_ab_hedef_${h.konum}` : "";
    }
}

// ============================================================================ üst yol (breadcrumb)
export class AtlasBilgiYol extends Component {
    static template = "atlas_bilgi.Yol";
    props = useProps(widgetProps);

    setup() {
        this.orm = useService("orm");
        this.state = proxy({ zincir: [] });
        onWillStart(async () => {
            if (this.props.record.resId) {
                this.state.zincir = await this.orm.call(MODEL, "ust_zincir", [[this.props.record.resId]]);
            }
        });
    }

    get ustler() {
        return this.state.zincir.slice(0, -1);
    }

    git(id) {
        return makaleAc(this.env, this.props.record, id);
    }

    get sonDuzenleme() {
        const d = this.props.record.data.son_duzenleme;
        const kim = this.props.record.data.son_duzenleyen_id;
        if (!d) {
            return "";
        }
        return `${kim?.display_name || ""} · ${d.toFormat("dd.MM.yyyy HH:mm")}`;
    }
}

// ============================================================================ diğer işlemler menüsü
export class AtlasBilgiMenu extends Component {
    static template = "atlas_bilgi.Menu";
    props = useProps(widgetProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        this.state = proxy({ acik: false });
    }

    get kayit() {
        return this.props.record;
    }

    get yazabilir() {
        return this.kayit.data.kullanici_yetkisi === "write";
    }

    async calistir(metot, yeniden = false) {
        this.state.acik = false;
        try {
            if (this.kayit.isDirty) {
                await this.kayit.save();
            }
            const sonuc = await this.orm.call(MODEL, metot, [[this.kayit.resId]]);
            if (sonuc && typeof sonuc === "object") {
                return this.action.doAction(sonuc, { stackPosition: metot === "action_cope_at" ? "replaceCurrentAction" : undefined });
            }
            if (yeniden) {
                await this.kayit.load();
            }
        } catch (h) {
            this.notification.add(hataMetni(h), { type: "danger" });
        }
    }

    copeAt() {
        this.state.acik = false;
        this.dialog.add(ConfirmationDialog, {
            title: "Çöpe at",
            body: "Makale ve tüm alt sayfaları çöp kutusuna taşınacak (30 gün sonra kalıcı silinir).",
            confirmLabel: "Çöpe At",
            confirm: () => this.calistir("action_cope_at"),
            cancel: () => {},
        });
    }

    gecmis() {
        this.state.acik = false;
        const kayit = this.kayit;
        const meta = kayit.data.html_field_history_metadata?.body;
        if (!meta) {
            this.notification.add("Bu makalenin henüz geri yüklenebilecek bir önceki sürümü yok.", { type: "info" });
            return;
        }
        this.dialog.add(HistoryDialog, {
            title: "Sürüm Geçmişi",
            recordId: kayit.resId,
            recordModel: MODEL,
            versionedFieldName: "body",
            historyMetadata: meta,
            restoreRequested: (html, kapat) => {
                kayit.update({ body: setHtmlFieldMetadata(html, getHtmlFieldMetadata(kayit.data.body)) });
                kapat();
            },
        });
    }
}

// ============================================================================ kapak alanı
export class AtlasBilgiKapak extends Component {
    static template = "atlas_bilgi.Kapak";
    props = useProps(standardFieldProps);

    get deger() {
        return this.props.record.data[this.props.name];
    }

    get url() {
        const v = this.deger;
        if (!v) {
            return "";
        }
        if (v.content) {
            return `data:image/png;base64,${v.content}`;
        }
        return imageUrl(this.props.record.resModel, this.props.record.resId, this.props.name, { unique: v.checksum || this.props.record.data.son_duzenleme });
    }

    get stil() {
        const konum = this.props.record.data.kapak_konum ?? 50;
        return `background-image: url('${this.url}'); background-position: center ${konum}%;`;
    }

    sec() {
        const girdi = document.createElement("input");
        girdi.type = "file";
        girdi.accept = "image/*";
        girdi.onchange = () => {
            const dosya = girdi.files[0];
            if (!dosya) {
                return;
            }
            const okuyucu = new FileReader();
            okuyucu.onload = () => {
                this.props.record.update({ [this.props.name]: { filename: dosya.name, content: okuyucu.result.split(",")[1] } });
            };
            okuyucu.readAsDataURL(dosya);
        };
        girdi.click();
    }

    kaldir() {
        this.props.record.update({ [this.props.name]: false });
    }

    kaydir(fark) {
        const konum = Math.max(0, Math.min(100, (this.props.record.data.kapak_konum ?? 50) + fark));
        this.props.record.update({ kapak_konum: konum });
    }
}

// ============================================================================ emoji simge alanı
const EMOJILER = (
    "📄 📘 📗 📕 📙 📒 📝 📌 📎 📊 📈 📉 🗂️ 🗃️ 🗓️ 📅 ✅ ☑️ ❓ ❗ 💡 🔥 ⭐ 🚀 🎯 🏁 🏆 🎉 💼 🏢 🏭 🏬 🚚 📦 🛒 💰 💳 🧾 " +
    "⚙️ 🛠️ 🔧 🔒 🔑 🧪 🧭 🗺️ 🌍 📞 ✉️ 💬 👥 👤 🤝 🙋 👋 🧑‍💻 🧑‍🏫 🎓 📚 🧠 ❤️ 🌱 ☕ 🍀 ⚡ 🔔 🛡️ ⚖️ 🗳️ 🧩 🖥️ 📱"
).split(" ");

export class AtlasBilgiEmoji extends Component {
    static template = "atlas_bilgi.Emoji";
    props = useProps(standardFieldProps);

    setup() {
        this.state = proxy({ acik: false });
    }

    get deger() {
        return this.props.record.data[this.props.name] || "";
    }

    get emojiler() {
        return EMOJILER;
    }

    sec(e) {
        this.state.acik = false;
        this.props.record.update({ [this.props.name]: e });
    }

    rastgele() {
        this.sec(EMOJILER[Math.floor(Math.random() * EMOJILER.length)]);
    }
}

registry.category("view_widgets").add("atlas_bilgi_kenar", { component: AtlasBilgiKenar });
registry.category("view_widgets").add("atlas_bilgi_yol", {
    component: AtlasBilgiYol,
    fieldDependencies: [
        { name: "son_duzenleme", type: "datetime" },
        { name: "son_duzenleyen_id", type: "many2one" },
    ],
});
registry.category("view_widgets").add("atlas_bilgi_menu", { component: AtlasBilgiMenu });
registry.category("fields").add("atlas_bilgi_kapak", {
    component: AtlasBilgiKapak,
    supportedTypes: ["binary"],
    fieldDependencies: [{ name: "kapak_konum", type: "float" }],
});
registry.category("fields").add("atlas_bilgi_emoji", { component: AtlasBilgiEmoji, supportedTypes: ["char"] });
