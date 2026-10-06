import { Component, markup, onWillStart, proxy, t, useProps } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { useService } from "@web/core/utils/hooks";

const MODEL = "atlas.bilgi.makale";

function hataMetni(h) {
    return h?.data?.message || h?.message || String(h);
}

/** Makaleye gömülecek menü / görünüm seçimi (/liste, /kanban) */
export class AtlasBilgiGorunumSec extends Component {
    static template = "atlas_bilgi.GorunumSec";
    static components = { Dialog };
    props = useProps({ close: t.function(), tur: t.string().optional("list"), onSec: t.function() });

    setup() {
        this.orm = useService("orm");
        this.state = proxy({ arama: "", sonuclar: [], secili: null, ad: "", tur: this.props.tur });
        onWillStart(() => this.ara());
    }

    async ara(ev) {
        if (ev) {
            this.state.arama = ev.target.value;
        }
        this.state.sonuclar = await this.orm.call(MODEL, "gorunum_secenekleri", [this.state.arama]);
    }

    sec(s) {
        this.state.secili = s;
        this.state.ad = s.ad;
        if (!s.modlar.includes(this.state.tur)) {
            this.state.tur = s.modlar[0];
        }
    }

    ekle() {
        const s = this.state.secili;
        if (!s) {
            return;
        }
        this.props.onSec({ eylem_id: s.eylem_id, tur: this.state.tur, ad: this.state.ad || s.ad });
        this.props.close();
    }
}

/** Makale seçimi (kayıttan bilgi bankasına, görünümü makaleye ekle, makale bağlantısı) */
export class AtlasBilgiMakaleSec extends Component {
    static template = "atlas_bilgi.MakaleSec";
    static components = { Dialog };
    props = useProps({
        close: t.function(),
        baslik: t.string().optional("Makale seçin"),
        onSec: t.function(),
        adGerekli: t.boolean().optional(false),
        varsayilanAd: t.string().optional(""),
    });

    setup() {
        this.orm = useService("orm");
        this.state = proxy({ arama: "", sonuclar: [], secili: null, ad: this.props.varsayilanAd });
        onWillStart(() => this.ara());
    }

    async ara(ev) {
        if (ev) {
            this.state.arama = ev.target.value;
        }
        const metin = this.state.arama.trim();
        this.state.sonuclar = metin.length >= 2
            ? await this.orm.call(MODEL, "ara", [metin])
            : (await this.orm.searchRead(MODEL, [["oge_mi", "=", false], ["sablon_mi", "=", false]], ["name", "simge"], { limit: 15, order: "son_duzenleme desc" }))
                  .map((m) => ({ id: m.id, ad: m.name, simge: m.simge || "📄", yol: "" }));
    }

    tamam() {
        if (!this.state.secili) {
            return;
        }
        this.props.onSec(this.state.secili, this.state.ad);
        this.props.close();
    }
}

/** Seçilen metne yorum */
export class AtlasBilgiYorumYaz extends Component {
    static template = "atlas_bilgi.YorumYaz";
    static components = { Dialog };
    props = useProps({ close: t.function(), metin: t.string().optional(""), onKaydet: t.function() });

    setup() {
        this.state = proxy({ mesaj: "" });
    }

    kaydet() {
        if (!this.state.mesaj.trim()) {
            return;
        }
        this.props.onKaydet(this.state.mesaj);
        this.props.close();
    }
}

/** Makalenin tüm yorumları */
export class AtlasBilgiYorumlar extends Component {
    static template = "atlas_bilgi.Yorumlar";
    static components = { Dialog };
    props = useProps({ close: t.function(), makaleId: t.number() });

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = proxy({ liste: [], cozulenler: false, yanitlar: {} });
        onWillStart(() => this.yukle());
    }

    async yukle() {
        this.state.liste = await this.orm.call(MODEL, "yorumlar", [[this.props.makaleId]]);
    }

    get gorunen() {
        return this.state.liste.filter((y) => this.state.cozulenler || !y.cozuldu);
    }

    async yanitla(y) {
        const mesaj = (this.state.yanitlar[y.id] || "").trim();
        if (!mesaj) {
            return;
        }
        try {
            await this.orm.call(MODEL, "yorum_yanitla", [y.id, mesaj]);
            this.state.yanitlar[y.id] = "";
            await this.yukle();
        } catch (h) {
            this.notification.add(hataMetni(h), { type: "danger" });
        }
    }

    async coz(y, deger) {
        await this.orm.call(MODEL, "yorum_coz", [y.id, deger]);
        await this.yukle();
    }
}

/** Herhangi bir kayıttan bilgi bankası: bağlı makaleler, arama, önizleme, mesaj olarak gönderme */
export class AtlasBilgiKayit extends Component {
    static template = "atlas_bilgi.Kayit";
    static components = { Dialog };
    props = useProps({ close: t.function(), resModel: t.string(), resId: t.number() });

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = proxy({ bagli: [], arama: "", sonuclar: [], onizleme: null });
        onWillStart(() => this.yukle());
    }

    async yukle() {
        this.state.bagli = await this.orm.call(MODEL, "kayit_makaleleri", [this.props.resModel, this.props.resId]);
    }

    async ara(ev) {
        this.state.arama = ev.target.value;
        this.state.sonuclar = this.state.arama.trim().length >= 2 ? await this.orm.call(MODEL, "ara", [this.state.arama.trim()]) : [];
    }

    async goster(id) {
        const veri = await this.orm.call(MODEL, "makale_onizleme", [[id]]);
        this.state.onizleme = { ...veri, govde: markup(veri.govde) };
    }

    async islem(metot, mesaj) {
        try {
            await this.orm.call(MODEL, metot, [[this.state.onizleme.id], this.props.resModel, this.props.resId]);
            this.notification.add(mesaj, { type: "success" });
            await this.yukle();
            if (metot === "kayda_gonder") {
                this.props.close();
                await this.action.doAction({ type: "ir.actions.client", tag: "soft_reload" });
            }
        } catch (h) {
            this.notification.add(hataMetni(h), { type: "danger" });
        }
    }

    async kaldir(b) {
        await this.orm.call(MODEL, "baglanti_kaldir", [b.baglanti_id]);
        await this.yukle();
    }

    async ac() {
        const eylem = await this.orm.call(MODEL, "action_ac", [[this.state.onizleme.id]]);
        this.props.close();
        this.action.doAction(eylem);
    }

    get bagliMi() {
        return this.state.onizleme && this.state.bagli.some((b) => b.id === this.state.onizleme.id);
    }
}
