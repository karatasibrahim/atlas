import { Component, onWillStart, proxy, t, useProps } from "@odoo/owl";
import { DomainSelectorDialog } from "@web/core/domain_selector_dialog/domain_selector_dialog";
import { ExpressionEditorDialog } from "@web/core/expression_editor_dialog/expression_editor_dialog";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { alanSimgesi, archAgaci, hataMetni, sabitDogru, sabitMi, SIMGELER } from "../arac";

const GORSEL_TURLER = ["form", "list", "search"];
const KAPSAYICILAR = ["group", "page", "sheet", "list", "search", "header", "form", "kanban", "templates", "t", "div"];

/**
 * Studio görünüm düzenleyicisi: solda canlı tuval (form / liste / arama ya da genel ağaç), sağda
 * Ekle / Görüntüle / Özellikler panelleri. Her değişiklik sunucuda atlas.studio.islem_uygula ile
 * Studio miras görünümüne bir xpath olarak yazılır; geri al / yinele sunucudadır.
 */
export class AtlasStudioEditor extends Component {
    static template = "atlas_studio.Editor";
    props = useProps({
        baglam: t.object(),
        tur: t.string(),
        onKaydedildi: t.function().optional(() => () => {}),
    });

    setup() {
        this.orm = useService("orm");
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        this.yuk = null;
        this.state = proxy({
            durum: null,
            agac: null,
            secili: null,
            sekme: "ekle",
            gorunmezGoster: false,
            sayfalar: {},
            hedef: null,
            diyalog: null,
            ornekler: [],
            arama: "",
            alanBilgisi: null,
            grupAdlari: {},
            grupArama: "",
            grupSonuc: [],
            onaylar: null,
            xml: null,
            mesgul: false,
            yeniNitelik: "",
            yeniNitelikDeger: "",
        });
        this.alanTurleri = [];
        onWillStart(async () => {
            this.alanTurleri = await this.orm.call("atlas.studio", "alan_turleri", []);
            await this.yukle();
        });
    }

    get model() {
        return this.props.baglam.model;
    }

    get gorsel() {
        return GORSEL_TURLER.includes(this.props.tur);
    }

    get durum() {
        return this.state.durum;
    }

    get kok() {
        return this.state.agac?.kok;
    }

    // ------------------------------------------------------------------ yükleme
    async yukle() {
        const durum = await this.orm.call("atlas.studio", "gorunum_getir", [this.model, this.props.tur, this.props.baglam.eylem.id]);
        await this.isle(durum);
    }

    async isle(durum) {
        const onceki = this.state.secili && this.state.agac?.harita.get(this.state.secili);
        this.state.durum = durum;
        this.state.agac = archAgaci(durum.arch);
        this.state.secili = null;
        if (onceki) {
            const ayni = [...this.state.agac.harita.values()].find(
                (d) => d.tag === onceki.tag && d.attrs.name && d.attrs.name === onceki.attrs.name
            );
            if (ayni) {
                this.state.secili = ayni.anahtar;
            }
        }
        if (!this.state.secili && this.state.sekme === "ozellikler") {
            this.state.sekme = "ekle";
        }
        if (durum.tur === "list") {
            const alanlar = this.kok.children.filter((c) => c.tag === "field").map((c) => c.attrs.name);
            this.state.ornekler = await this.orm.call("atlas.studio", "ornek_kayitlar", [this.model, alanlar, 4]);
        }
        await this.grupAdlariYukle();
    }

    async grupAdlariYukle() {
        const xmlidler = new Set();
        for (const d of this.state.agac.harita.values()) {
            for (const g of (d.attrs.groups || "").split(",")) {
                if (g.trim() && !(g.trim().replace("!", "") in this.state.grupAdlari)) {
                    xmlidler.add(g.trim());
                }
            }
        }
        if (xmlidler.size) {
            Object.assign(this.state.grupAdlari, await this.orm.call("atlas.studio", "grup_adlari", [[...xmlidler]]));
        }
    }

    async calistir(fn) {
        if (this.state.mesgul) {
            return;
        }
        this.state.mesgul = true;
        try {
            return await fn();
        } catch (hata) {
            this.notification.add(hataMetni(hata), { type: "danger", title: "Studio" });
        } finally {
            this.state.mesgul = false;
        }
    }

    async uygula(islemler) {
        return this.calistir(async () => {
            const durum = await this.orm.call("atlas.studio", "islem_uygula", [this.durum.view_id, islemler]);
            await this.isle(durum);
            this.props.onKaydedildi();
            if (this.state.secili && this.state.sekme === "ozellikler") {
                await this.seciliBilgiYukle();
            }
            return true;
        });
    }

    geriAl() {
        return this.calistir(async () => {
            await this.isle(await this.orm.call("atlas.studio", "geri_al", [this.durum.view_id]));
            this.props.onKaydedildi();
        });
    }

    yinele() {
        return this.calistir(async () => {
            await this.isle(await this.orm.call("atlas.studio", "yinele", [this.durum.view_id]));
            this.props.onKaydedildi();
        });
    }

    sifirla() {
        this.state.diyalog = { tur: "onayla", metin: "Bu görünümdeki tüm Studio değişiklikleri kaldırılacak. Devam edilsin mi?", eylem: async () => {
            await this.calistir(async () => this.isle(await this.orm.call("atlas.studio", "sifirla", [this.durum.view_id])));
            this.props.onKaydedildi();
        } };
    }

    // ------------------------------------------------------------------ düğüm yardımcıları
    dugum(anahtar) {
        return this.state.agac?.harita.get(anahtar);
    }

    get secili() {
        return this.state.secili ? this.dugum(this.state.secili) : null;
    }

    alan(ad) {
        return this.durum.alanlar[ad] || { string: ad, type: "char" };
    }

    etiket(d) {
        if (d.tag === "field") {
            return d.attrs.string || this.alan(d.attrs.name).string;
        }
        return d.attrs.string || d.attrs.name || d.text || d.tag;
    }

    gizli(d) {
        if (this.state.gorunmezGoster) {
            return false;
        }
        if (sabitDogru(d.attrs.invisible) || sabitDogru(d.attrs.column_invisible)) {
            return true;
        }
        // koşullu görünen uyarı kutuları ve şeritler tuvali kalabalıklaştırmasın (Görünmez öğeleri göster ile açılır)
        const sinif = d.attrs.class || "";
        return Boolean(d.attrs.invisible) && ((d.tag === "div" && sinif.includes("alert")) || (d.tag === "widget" && d.attrs.name === "web_ribbon"));
    }

    istatEtiket(c) {
        if (c.attrs.string) {
            return c.attrs.string;
        }
        const ara = (d) => {
            for (const x of d.children) {
                if (x.tag === "field" && (x.attrs.string || x.attrs.widget === "statinfo")) {
                    return x.attrs.string || this.alan(x.attrs.name).string;
                }
                if (x.text && x.tag === "span") {
                    return x.text;
                }
                const ic = ara(x);
                if (ic) {
                    return ic;
                }
            }
            for (const x of d.children) {
                if (x.tag === "field") {
                    return this.alan(x.attrs.name).string;
                }
            }
            return "";
        };
        return ara(c) || c.attrs.name || "Düğme";
    }

    sinif(d, ek = "") {
        const s = [ek, "o_as_d"];
        if (this.state.secili === d.anahtar) {
            s.push("o_as_secili");
        }
        if (sabitDogru(d.attrs.invisible) || sabitDogru(d.attrs.column_invisible)) {
            s.push("o_as_gizli");
        } else if (d.attrs.invisible) {
            s.push("o_as_kosullu");
        }
        if (this.state.hedef?.anahtar === d.anahtar) {
            s.push(`o_as_hedef_${this.state.hedef.konum}`);
        }
        return s.join(" ");
    }

    onizleme(d) {
        const f = this.alan(d.attrs.name);
        const w = d.attrs.widget;
        if (w === "statusbar" || w === "priority" || w === "image" || w === "signature") {
            return "";
        }
        return (
            {
                char: "Metin",
                text: "Uzun metin…",
                html: "Biçimli metin…",
                integer: "0",
                float: "0,00",
                monetary: "0,00 ₺",
                date: "gg.aa.yyyy",
                datetime: "gg.aa.yyyy ss:dd",
                boolean: "",
                selection: (f.selection || [])[0]?.[1] || "Seçim",
                many2one: f.relation ? `${f.string}…` : "Seçin…",
                many2many: "Etiketler…",
                binary: "Dosya yükle",
            }[f.type] || ""
        );
    }

    ozelAlan(d) {
        return d.tag === "field" && this.alan(d.attrs.name).ozel;
    }

    sayfaAktif(notebook) {
        const i = this.state.sayfalar[notebook.anahtar] || 0;
        const gorunur = notebook.children.filter((p) => !this.gizli(p));
        return gorunur[Math.min(i, gorunur.length - 1)];
    }

    sayfaSec(notebook, sayfa, ev) {
        ev.stopPropagation();
        const gorunur = notebook.children.filter((p) => !this.gizli(p));
        this.state.sayfalar[notebook.anahtar] = gorunur.indexOf(sayfa);
        this.sec(sayfa, ev);
    }

    altGruplu(d) {
        return d.children.some((c) => c.tag === "group");
    }

    ilkAlt(d, tag) {
        return d.children.find((c) => c.tag === tag);
    }

    dugmeKutusu(d) {
        return d.tag === "div" && (d.attrs.name === "button_box" || (d.attrs.class || "").includes("oe_button_box"));
    }

    // ------------------------------------------------------------------ seçim ve özellikler
    async sec(d, ev) {
        ev?.stopPropagation();
        ev?.preventDefault?.();
        this.state.secili = d.anahtar;
        this.state.sekme = "ozellikler";
        await this.seciliBilgiYukle();
    }

    async seciliBilgiYukle() {
        const d = this.secili;
        this.state.alanBilgisi = null;
        this.state.onaylar = null;
        this.state.grupArama = "";
        this.state.grupSonuc = [];
        if (!d) {
            return;
        }
        if (d.tag === "field" && d.attrs.name in this.durum.alanlar) {
            this.state.alanBilgisi = await this.orm.call("atlas.studio", "alan_bilgisi", [this.model, d.attrs.name]);
        }
        const hedef = this.onayHedefi(d);
        if (hedef) {
            this.state.onaylar = await this.orm.call("atlas.studio", "onay_kurallari", [this.model, hedef]);
        }
    }

    nitelik(d, degerler) {
        return this.uygula({ islem: "nitelik", hedef_yol: d.yol, nitelikler: degerler });
    }

    metinNitelik(d, ad, ev) {
        const deger = ev.target.value;
        if ((d.attrs[ad] || "") !== deger) {
            this.nitelik(d, { [ad]: deger });
        }
    }

    kutuNitelik(d, ad, ev) {
        this.nitelik(d, { [ad]: ev.target.checked ? "True" : "" });
    }

    kosulDuzenle(d, ad) {
        const alanlar = Object.fromEntries(Object.entries(this.durum.alanlar).map(([n, f]) => [n, { ...f, name: n }]));
        const mevcut = d.attrs[ad];
        this.dialog.add(ExpressionEditorDialog, {
            resModel: this.model,
            fields: alanlar,
            expression: mevcut && !sabitMi(mevcut) ? mevcut : "False",
            onConfirm: (ifade) => this.nitelik(d, { [ad]: ifade === "False" ? "" : ifade }),
        });
    }

    alanAlaniDomain(d) {
        const f = this.alan(d.attrs.name);
        this.dialog.add(DomainSelectorDialog, {
            resModel: f.relation,
            domain: d.attrs.domain || "[]",
            isDebugMode: true,
            onConfirm: (domain) => this.nitelik(d, { domain: domain === "[]" ? "" : domain }),
        });
    }

    secenek(d, anahtar) {
        const metin = d.attrs.options || "";
        return new RegExp(`['"]${anahtar}['"]\\s*:\\s*(True|true|1)`).test(metin);
    }

    secenekDegistir(d, anahtar, ev) {
        let nesne = {};
        try {
            nesne = d.attrs.options ? JSON.parse(d.attrs.options.replace(/'/g, '"').replace(/\bTrue\b/g, "true").replace(/\bFalse\b/g, "false")) : {};
        } catch {
            nesne = {};
        }
        if (ev.target.checked) {
            nesne[anahtar] = true;
        } else {
            delete nesne[anahtar];
        }
        const metin = Object.keys(nesne).length
            ? "{" + Object.entries(nesne).map(([k, v]) => `'${k}': ${v === true ? "True" : v === false ? "False" : JSON.stringify(v)}`).join(", ") + "}"
            : "";
        this.nitelik(d, { options: metin });
    }

    widgetler(d) {
        const tip = this.alan(d.attrs.name).type;
        return registry
            .category("fields")
            .getEntries()
            .filter(([ad, tanim]) => !ad.includes(".") && (tanim.supportedTypes || []).includes(tip))
            .map(([ad, tanim]) => [ad, tanim.displayName || ad])
            .sort((a, b) => String(a[1]).localeCompare(String(b[1]), "tr"));
    }

    gruplar(d) {
        return (d.attrs.groups || "")
            .split(",")
            .map((g) => g.trim())
            .filter(Boolean)
            .map((g) => ({ xmlid: g.replace("!", ""), yasak: g.startsWith("!"), ad: this.state.grupAdlari[g.replace("!", "")] || g }));
    }

    async grupAra(ev) {
        this.state.grupArama = ev.target.value;
        this.state.grupSonuc = this.state.grupArama.length >= 2 ? await this.orm.call("atlas.studio", "grup_ara", [this.state.grupArama]) : [];
    }

    grupEkle(d, g, yasak) {
        this.state.grupAdlari[g.xmlid] = g.ad;
        const liste = this.gruplar(d).filter((x) => x.xmlid !== g.xmlid);
        liste.push({ xmlid: g.xmlid, yasak });
        this.state.grupArama = "";
        this.state.grupSonuc = [];
        this.nitelik(d, { groups: liste.map((x) => (x.yasak ? "!" : "") + x.xmlid).join(",") });
    }

    grupCikar(d, xmlid) {
        this.nitelik(d, { groups: this.gruplar(d).filter((x) => x.xmlid !== xmlid).map((x) => (x.yasak ? "!" : "") + x.xmlid).join(",") });
    }

    async alanOzellik(degerler) {
        await this.calistir(async () => {
            await this.orm.call("atlas.studio", "alan_ozellik", [this.model, this.secili.attrs.name, degerler]);
            this.state.alanBilgisi = await this.orm.call("atlas.studio", "alan_bilgisi", [this.model, this.secili.attrs.name]);
            this.props.onKaydedildi();
            if ("etiket" in degerler) {
                await this.isle(await this.orm.call("atlas.studio", "gorunum_getir", [this.model, this.props.tur, this.props.baglam.eylem.id]));
            }
        });
    }

    varsayilanYaz(ev) {
        const f = this.alan(this.secili.attrs.name);
        let deger = ev.target.type === "checkbox" ? ev.target.checked : ev.target.value;
        if (["integer", "many2one"].includes(f.type) && deger !== "") {
            deger = parseInt(deger, 10);
        } else if (["float", "monetary"].includes(f.type) && deger !== "") {
            deger = parseFloat(String(deger).replace(",", "."));
        }
        this.alanOzellik({ varsayilan: deger });
    }

    kaldir(d) {
        this.state.secili = null;
        this.state.sekme = "ekle";
        return this.uygula({ islem: "kaldir", hedef_yol: d.yol });
    }

    // ------------------------------------------------------------------ onay adımları
    onayHedefi(d) {
        if (d.tag !== "button" || this.props.tur !== "form") {
            return false;
        }
        if (d.attrs.name === "atlas_studio_onayli_calistir") {
            const m = (d.attrs.context || "").match(/atlas_studio_onay['"]\s*:\s*['"][^:'"]+:([^'"]+)['"]/);
            return m ? m[1] : false;
        }
        if (d.attrs.type === "object" && d.attrs.name) {
            return `metot:${d.attrs.name}`;
        }
        if (d.attrs.type === "action" && /^\d+$/.test(d.attrs.name || "")) {
            return `eylem:${d.attrs.name}`;
        }
        return false;
    }

    onayEkle() {
        this.state.onaylar.push({ grup: false, aciklama: "", bildirim: true });
    }

    async onayGrupAra(onay, ev) {
        onay._arama = ev.target.value;
        onay._sonuc = onay._arama.length >= 2 ? await this.orm.call("atlas.studio", "grup_ara", [onay._arama]) : [];
    }

    async onaylariKaydet(d) {
        const hedef = this.onayHedefi(d);
        const kurallar = this.state.onaylar.map((o) => ({ grup_id: o.grup ? o.grup[0] : false, aciklama: o.aciklama, bildirim: o.bildirim }));
        await this.calistir(() => this.orm.call("atlas.studio", "onay_kurallari_kaydet", [this.model, hedef, kurallar]));
        const sarili = d.attrs.name === "atlas_studio_onayli_calistir";
        if (kurallar.length && !sarili) {
            await this.nitelik(d, {
                name: "atlas_studio_onayli_calistir",
                type: "object",
                context: `{'atlas_studio_onay': '${this.model}:${hedef}'}`,
            });
        } else if (!kurallar.length && sarili) {
            const [tur, ad] = [hedef.split(":")[0], hedef.split(":").slice(1).join(":")];
            await this.nitelik(d, { name: ad, type: tur === "metot" ? "object" : "action", context: "" });
        } else {
            this.notification.add("Onay adımları kaydedildi.", { type: "success" });
        }
    }

    // ------------------------------------------------------------------ sürükle bırak
    surukleBasla(yuk, ev) {
        ev.stopPropagation();
        this.yuk = yuk;
        ev.dataTransfer.effectAllowed = "copyMove";
        ev.dataTransfer.setData("text/plain", "atlas_studio");
    }

    surukleBitti() {
        this.state.hedef = null;
    }

    uzerinde(d, ev, yatay = false) {
        if (!this.yuk) {
            return;
        }
        ev.preventDefault();
        ev.stopPropagation();
        let konum;
        const bosKapsayici = KAPSAYICILAR.includes(d.tag) && !d.children.length;
        if (bosKapsayici || (["page", "sheet"].includes(d.tag))) {
            konum = "inside";
        } else {
            const r = ev.currentTarget.getBoundingClientRect();
            konum = yatay ? (ev.clientX < r.left + r.width / 2 ? "before" : "after") : ev.clientY < r.top + r.height / 2 ? "before" : "after";
        }
        if (this.state.hedef?.anahtar !== d.anahtar || this.state.hedef?.konum !== konum) {
            this.state.hedef = { anahtar: d.anahtar, konum };
        }
    }

    birak(ev) {
        ev.preventDefault();
        ev.stopPropagation();
        const hedef = this.state.hedef;
        const yuk = this.yuk;
        this.state.hedef = null;
        this.yuk = null;
        if (hedef && yuk) {
            this.yerlestir(yuk, hedef);
        }
    }

    /** Tıklayarak eklemede varsayılan konum */
    varsayilanHedef() {
        const kok = this.kok;
        if (this.props.tur === "form") {
            const sheet = [...this.state.agac.harita.values()].find((d) => d.tag === "sheet");
            const grup = [...this.state.agac.harita.values()].find(
                (d) => d.tag === "group" && !this.altGruplu(d) && !this.gizli(d) && (!sheet || d.anahtar.startsWith(sheet.anahtar))
            );
            if (grup) {
                return { anahtar: grup.anahtar, konum: "inside" };
            }
            return { anahtar: (sheet || kok).anahtar, konum: "inside" };
        }
        return { anahtar: kok.anahtar, konum: "inside" };
    }

    ekleTikla(yuk) {
        this.yerlestir(yuk, this.varsayilanHedef());
    }

    /** Bileşenleri form gövdesine yerleştirirken hedefi en dıştaki gruba taşır */
    disGrup(hedef) {
        let d = this.dugum(hedef.anahtar);
        if (hedef.konum === "inside" && ["group", "page", "sheet"].includes(d.tag) && d.tag !== "group") {
            return hedef;
        }
        let konum = hedef.konum;
        while (d.ust && ["group", "field"].includes(d.tag) && d.ust.tag === "group") {
            d = d.ust;
            konum = "after";
        }
        if (d.tag === "field") {
            konum = "after";
        }
        return { anahtar: d.anahtar, konum };
    }

    async yerlestir(yuk, hedef) {
        const hedefDugum = this.dugum(hedef.anahtar);
        if (!hedefDugum) {
            return;
        }
        if (yuk.kaynak) {
            if (yuk.kaynak.anahtar === hedef.anahtar) {
                return;
            }
            return this.uygula({ islem: "tasi", kaynak_yol: yuk.kaynak.yol, hedef_yol: hedefDugum.yol, konum: hedef.konum });
        }
        if (yuk.alan) {
            return this.alanDugumuEkle({ name: yuk.alan }, hedef);
        }
        if (yuk.tur) {
            this.state.diyalog = { tur: "alan", alanTur: yuk.tur, hedef, etiket: "", secenekler: "", iliski: "", tersAlan: "", yol: "",
                                   modeller: [], tersler: [], avatar: false };
            return;
        }
        if (yuk.bilesen) {
            return this.bilesenEkle(yuk.bilesen, hedef);
        }
    }

    alanDugumuEkle(attrs, hedef) {
        const d = this.dugum(hedef.anahtar);
        const ek = { ...attrs };
        if (this.props.tur === "list" && this.alan(attrs.name).type === "many2many") {
            ek.widget = ek.widget || "many2many_tags";
        }
        if (this.props.tur === "form" && this.alan(attrs.name).type === "one2many" && !ek.widget) {
            // gömülü liste sunucunun varsayılan alt görünümüyle açılır
        }
        return this.uygula({ islem: "ekle", hedef_yol: d.yol, konum: hedef.konum, dugum: { tag: "field", attrs: ek } });
    }

    async bilesenEkle(bilesen, hedef) {
        if (bilesen === "sekmeler") {
            hedef = this.disGrup(hedef);
            return this.uygula({ islem: "ekle", hedef_yol: this.dugum(hedef.anahtar).yol, konum: hedef.konum, dugum: {
                tag: "notebook", children: [{ tag: "page", attrs: { string: "Yeni Sekme", name: `studio_sayfa_${Date.now() % 1e8}` } }] } });
        }
        if (bilesen === "sutunlar") {
            hedef = this.disGrup(hedef);
            const ad = `studio_grup_${Date.now() % 1e8}`;
            return this.uygula({ islem: "ekle", hedef_yol: this.dugum(hedef.anahtar).yol, konum: hedef.konum, dugum: {
                tag: "group", attrs: { name: ad }, children: [{ tag: "group", attrs: { name: `${ad}_sol` } }, { tag: "group", attrs: { name: `${ad}_sag` } }] } });
        }
        if (bilesen === "ayrac") {
            const tag = this.props.tur === "search" ? "separator" : "separator";
            return this.uygula({ islem: "ekle", hedef_yol: this.dugum(hedef.anahtar).yol, konum: hedef.konum, dugum: { tag, attrs: this.props.tur === "search" ? {} : { string: "Başlık" } } });
        }
        if (bilesen === "dugme") {
            const eylemler = await this.orm.call("atlas.studio", "sunucu_eylemleri", [this.model]);
            this.state.diyalog = { tur: "dugme", etiket: "", hedefTur: eylemler.length ? "eylem" : "metot", eylem: eylemler[0]?.id || false, metot: "", stil: "btn-primary", eylemler };
            return;
        }
        if (bilesen === "akilli") {
            const iliskiler = await this.orm.call("atlas.studio", "gelen_iliskiler", [this.model]);
            this.state.diyalog = { tur: "akilli", iliskiler, iliski: iliskiler[0]?.id || false, etiket: "", simge: "list_alt" };
            return;
        }
        if (bilesen === "filtre") {
            this.state.diyalog = { tur: "filtre", etiket: "", domain: "[]", hedef };
            return;
        }
        if (bilesen === "gruplama") {
            this.state.diyalog = { tur: "gruplama", alan: "", hedef };
            return;
        }
    }

    // ------------------------------------------------------------------ diyaloglar
    diyalogKapat() {
        this.state.diyalog = null;
    }

    async onaylaCalistir() {
        const eylem = this.state.diyalog.eylem;
        this.state.diyalog = null;
        await eylem();
    }

    async modelAra(ev) {
        this.state.diyalog.modeller = await this.orm.call("atlas.studio", "modeller", [ev.target.value]);
    }

    async iliskiSec(ev) {
        const dl = this.state.diyalog;
        dl.iliski = ev.target.value;
        if (dl.alanTur === "one2many" && dl.iliski) {
            const tumu = await this.orm.call("atlas.studio", "gelen_iliskiler", [this.model]);
            dl.tersler = tumu.filter((r) => r.model === dl.iliski);
            dl.tersAlan = dl.tersler[0]?.alan || "";
        }
    }

    async alanDiyaloguOnayla() {
        const dl = this.state.diyalog;
        const tanim = { tur: dl.alanTur, etiket: dl.etiket, iliski: dl.iliski, ters_alan: dl.tersAlan, yol: dl.yol, avatar: dl.avatar };
        if (dl.alanTur === "selection") {
            tanim.secenekler = dl.secenekler
                .split("\n")
                .map((s) => s.trim())
                .filter(Boolean)
                .map((s, i) => [s.includes("=") ? s.split("=")[0].trim() : `${i + 1}`, s.includes("=") ? s.split("=").slice(1).join("=").trim() : s]);
        }
        let sonuc;
        try {
            sonuc = await this.orm.call("atlas.studio", "alan_olustur", [this.model, tanim]);
        } catch (hata) {
            this.notification.add(hataMetni(hata), { type: "danger", title: "Studio" });
            return;
        }
        this.state.diyalog = null;
        const durum = await this.orm.call("atlas.studio", "gorunum_getir", [this.model, this.props.tur, this.props.baglam.eylem.id]);
        this.state.durum.alanlar = durum.alanlar;
        await this.alanDugumuEkle({ name: sonuc.ad, ...sonuc.nitelikler }, dl.hedef);
    }

    async dugmeDiyaloguOnayla() {
        const dl = this.state.diyalog;
        if (!dl.etiket || (dl.hedefTur === "eylem" ? !dl.eylem : !dl.metot)) {
            this.notification.add("Etiket ve hedef gerekli.", { type: "warning" });
            return;
        }
        const dugme = { tag: "button", attrs: { string: dl.etiket, class: dl.stil, type: dl.hedefTur === "eylem" ? "action" : "object",
                                                 name: dl.hedefTur === "eylem" ? String(dl.eylem) : dl.metot } };
        this.state.diyalog = null;
        const header = this.ilkAlt(this.kok, "header");
        if (header) {
            return this.uygula({ islem: "ekle", hedef_yol: header.yol, konum: "inside", dugum: dugme });
        }
        const sheet = this.ilkAlt(this.kok, "sheet") || this.kok.children[0];
        if (sheet) {
            return this.uygula({ islem: "ekle", hedef_yol: sheet.yol, konum: "before", dugum: { tag: "header", children: [dugme] } });
        }
        return this.uygula({ islem: "ekle", hedef_yol: [], konum: "inside", dugum: { tag: "header", children: [dugme] } });
    }

    async akilliDiyaloguOnayla() {
        const dl = this.state.diyalog;
        if (!dl.iliski || !dl.etiket) {
            this.notification.add("İlişki ve etiket gerekli.", { type: "warning" });
            return;
        }
        this.state.diyalog = null;
        await this.calistir(async () => {
            await this.isle(await this.orm.call("atlas.studio", "akilli_dugme_ekle", [this.durum.view_id, parseInt(dl.iliski, 10), dl.etiket, dl.simge]));
            this.props.onKaydedildi();
        });
    }

    filtreDomain() {
        this.dialog.add(DomainSelectorDialog, {
            resModel: this.model,
            domain: this.state.diyalog.domain,
            isDebugMode: true,
            onConfirm: (domain) => {
                if (this.state.diyalog) {
                    this.state.diyalog.domain = domain;
                }
            },
        });
    }

    filtreDiyaloguOnayla() {
        const dl = this.state.diyalog;
        this.state.diyalog = null;
        const ad = `studio_filtre_${Date.now() % 1e8}`;
        return this.uygula({ islem: "ekle", hedef_yol: this.dugum(dl.hedef.anahtar).yol, konum: dl.hedef.konum,
                             dugum: { tag: "filter", attrs: { name: ad, string: dl.etiket || "Filtre", domain: dl.domain } } });
    }

    gruplamaDiyaloguOnayla() {
        const dl = this.state.diyalog;
        if (!dl.alan) {
            return;
        }
        this.state.diyalog = null;
        return this.uygula({ islem: "ekle", hedef_yol: this.dugum(dl.hedef.anahtar).yol, konum: dl.hedef.konum,
                             dugum: { tag: "filter", attrs: { name: `studio_grupla_${dl.alan}`, string: this.alan(dl.alan).string, context: `{'group_by': '${dl.alan}'}` } } });
    }

    get gruplanabilirAlanlar() {
        return Object.entries(this.durum.alanlar)
            .filter(([, f]) => f.groupable !== false && f.store !== false && !["one2many", "many2many", "binary", "html", "text"].includes(f.type))
            .map(([ad, f]) => [ad, f.string])
            .sort((a, b) => a[1].localeCompare(b[1], "tr"));
    }

    get simgeler() {
        return SIMGELER;
    }

    // ------------------------------------------------------------------ XML düzenleyici
    async xmlAc() {
        const veri = await this.orm.call("atlas.studio", "xml_getir", [this.durum.view_id]);
        this.state.xml = { ...veri, metin: veri.studio };
    }

    xmlYaz(ev) {
        this.state.xml.metin = ev.target.value;
    }

    async xmlKaydet() {
        await this.calistir(async () => {
            await this.isle(await this.orm.call("atlas.studio", "xml_kaydet", [this.durum.view_id, this.state.xml.metin]));
            this.state.xml = null;
            this.props.onKaydedildi();
        });
    }

    // ------------------------------------------------------------------ Ekle paneli
    get yeniAlanTurleri() {
        if (this.props.tur === "search") {
            return [];
        }
        return this.alanTurleri.map((t) => ({ ...t, simge: alanSimgesi(t.tur) }));
    }

    get mevcutAlanlar() {
        const kullanilan = new Set([...this.state.agac.harita.values()].filter((d) => d.tag === "field" && this.ustKok(d)).map((d) => d.attrs.name));
        const arama = this.state.arama.toLocaleLowerCase("tr");
        return Object.entries(this.durum.alanlar)
            .filter(([ad, f]) => !kullanilan.has(ad) && !["id", "__last_update"].includes(ad) && !ad.startsWith("message_") && !ad.startsWith("activity_"))
            .filter(([ad, f]) => !arama || f.string.toLocaleLowerCase("tr").includes(arama) || ad.includes(arama))
            .filter(([, f]) => this.props.tur !== "search" || f.store !== false)
            .map(([ad, f]) => ({ ad, etiket: f.string, tur: f.type, simge: alanSimgesi(f.type), ozel: f.ozel }))
            .sort((a, b) => a.etiket.localeCompare(b.etiket, "tr"));
    }

    /** Alt görünümlerin (gömülü liste) içindeki alanlar sayılmasın */
    ustKok(d) {
        let u = d.ust;
        while (u) {
            if (u.tag === "field") {
                return false;
            }
            u = u.ust;
        }
        return true;
    }

    get bilesenler() {
        if (this.props.tur === "form") {
            return [
                { k: "sekmeler", ad: "Sekmeler", simge: "table_view" },
                { k: "sutunlar", ad: "Sütunlar", simge: "view_list" },
                { k: "ayrac", ad: "Başlık / Ayraç", simge: "remove" },
                { k: "dugme", ad: "Üst Düğme", simge: "play_arrow" },
                { k: "akilli", ad: "Akıllı Düğme", simge: "bar_chart" },
            ];
        }
        if (this.props.tur === "list") {
            return [{ k: "dugme_liste", ad: "Satır Düğmesi", simge: "play_arrow" }];
        }
        if (this.props.tur === "search") {
            return [
                { k: "filtre", ad: "Filtre", simge: "filter_alt" },
                { k: "gruplama", ad: "Gruplama", simge: "account_tree" },
                { k: "ayrac", ad: "Ayraç", simge: "remove" },
            ];
        }
        return [];
    }

    async bilesenTikla(b) {
        if (b.k === "dugme_liste") {
            const eylemler = await this.orm.call("atlas.studio", "sunucu_eylemleri", [this.model]);
            this.state.diyalog = { tur: "dugme", liste: true, etiket: "", hedefTur: eylemler.length ? "eylem" : "metot", eylem: eylemler[0]?.id || false, metot: "", stil: "btn-link", eylemler };
            return;
        }
        if (["filtre", "gruplama", "ayrac"].includes(b.k) && this.props.tur === "search") {
            return this.bilesenEkle(b.k, { anahtar: this.kok.anahtar, konum: "inside" });
        }
        return this.ekleTikla({ bilesen: b.k });
    }

    async listeDugmesiOnayla() {
        const dl = this.state.diyalog;
        if (!dl.etiket) {
            return;
        }
        this.state.diyalog = null;
        return this.uygula({ islem: "ekle", hedef_yol: [], konum: "inside", dugum: { tag: "button", attrs: {
            string: dl.etiket, class: dl.stil, type: dl.hedefTur === "eylem" ? "action" : "object", name: dl.hedefTur === "eylem" ? String(dl.eylem) : dl.metot } } });
    }

    // ------------------------------------------------------------------ Görüntüle paneli
    kokSecenek(ad) {
        const v = this.kok.attrs[ad];
        return !(v === "0" || v === "false" || v === "False");
    }

    kokSecenekYaz(ad, ev) {
        return this.nitelik(this.kok, { [ad]: ev.target.checked ? "" : "0" });
    }

    get chatterVar() {
        return [...this.state.agac.harita.values()].find((d) => d.tag === "chatter");
    }

    chatterDegistir(ev) {
        const c = this.chatterVar;
        if (ev.target.checked && !c) {
            return this.uygula({ islem: "ekle", hedef_yol: [], konum: "inside", dugum: { tag: "chatter" } });
        }
        if (!ev.target.checked && c) {
            return this.uygula({ islem: "kaldir", hedef_yol: c.yol });
        }
    }

    get siralama() {
        const [alan, yon] = (this.kok.attrs.default_order || "").split(",")[0].trim().split(/\s+/);
        return { alan: alan || "", yon: (yon || "asc").toLowerCase() };
    }

    siralamaYaz(alan, yon) {
        return this.nitelik(this.kok, { default_order: alan ? `${alan} ${yon}` : "" });
    }

    get siralanabilirAlanlar() {
        return Object.entries(this.durum.alanlar)
            .filter(([, f]) => f.sortable !== false && f.store !== false && !["one2many", "many2many", "binary", "html"].includes(f.type))
            .map(([ad, f]) => [ad, f.string])
            .sort((a, b) => a[1].localeCompare(b[1], "tr"));
    }

    get kokNitelikleri() {
        return Object.entries(this.kok.attrs);
    }

    kokNitelikEkle() {
        const ad = (this.state.yeniNitelik || "").trim();
        if (!ad) {
            return;
        }
        this.state.yeniNitelik = "";
        return this.nitelik(this.kok, { [ad]: this.state.yeniNitelikDeger || "" });
    }

    // ------------------------------------------------------------------ arama görünümü
    aramaDugumleri(tur) {
        return [...this.state.agac.harita.values()].filter((d) => {
            if (!this.ustKok(d) || d === this.kok) {
                return false;
            }
            if (tur === "alan") {
                return d.tag === "field";
            }
            if (tur === "gruplama") {
                return d.tag === "filter" && (d.attrs.context || "").includes("group_by");
            }
            if (tur === "filtre") {
                return (d.tag === "filter" && !(d.attrs.context || "").includes("group_by")) || d.tag === "separator";
            }
            return false;
        });
    }

    listeSutunlari() {
        return this.kok.children.filter((c) => ["field", "button"].includes(c.tag) && !this.gizli(c));
    }

    ornekDeger(kayit, d) {
        const v = kayit[d.attrs.name];
        if (v === false || v === null || v === undefined) {
            return "";
        }
        if (Array.isArray(v)) {
            return v[1] ?? "";
        }
        const f = this.alan(d.attrs.name);
        if (f.type === "selection") {
            return (f.selection || []).find((s) => s[0] === v)?.[1] || v;
        }
        if (f.type === "boolean") {
            return v ? "✓" : "";
        }
        return String(v);
    }

    sutunGenisligi(d) {
        return d.attrs.width ? `width: ${d.attrs.width}` : "";
    }
}
