import { Component, markup, onWillStart, proxy, t, useProps } from "@odoo/owl";
import { getEmbeddedProps } from "@html_editor/others/embedded_component_utils";
import { makeContext } from "@web/core/context";
import { Domain } from "@web/core/domain";
import { rpc } from "@web/core/network/rpc";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";
import { View } from "@web/views/view";

const MODEL = "atlas.bilgi.makale";

function hataMetni(h) {
    return h?.data?.message || h?.message || String(h);
}

// ============================================================================ gömülü görünüm (/liste, /kanban)
export class AtlasBilgiGorunum extends Component {
    static template = "atlas_bilgi.Gorunum";
    static components = { View };
    static onbellek = {};
    props = useProps({
        host: t.any().optional(),
        eylem_id: t.number(),
        tur: t.string().optional("list"),
        ad: t.string().optional(""),
        domain: t.any().optional(),
        context: t.any().optional(),
        makaleId: t.any().optional(),
        readonly: t.any().optional(),
    });

    setup() {
        this.action = useService("action");
        this.state = proxy({ tur: this.props.tur || "list", hata: false, hazir: false, modlar: [] });
        onWillStart(() => this.yukle());
    }

    async yukle() {
        let eylem = AtlasBilgiGorunum.onbellek[this.props.eylem_id];
        try {
            if (!eylem) {
                eylem = await rpc("/web/action/load", { action_id: this.props.eylem_id });
                AtlasBilgiGorunum.onbellek[this.props.eylem_id] = eylem;
            }
        } catch {
            eylem = null;
        }
        if (!eylem || !eylem.res_model) {
            this.state.hata = true;
            return;
        }
        this.eylem = eylem;
        this.state.modlar = eylem.views.map((v) => v[1]).filter((v) => ["list", "kanban"].includes(v));
        this.state.hazir = true;
    }

    get baslik() {
        return this.props.ad || this.eylem?.name || "";
    }

    get viewProps() {
        const eylem = this.eylem;
        const tur = this.state.tur;
        const gorunum = eylem.views.find((v) => v[1] === tur);
        const arama = eylem.views.find((v) => v[1] === "search");
        const form = eylem.views.find((v) => v[1] === "form");
        const alanlar = [eylem.domain || [], this.props.domain || []].map((d) => (typeof d === "string" ? new Domain(d) : new Domain(d)));
        const baglam = makeContext([eylem.context || {}, this.props.context || {}, { lang: user.context.lang }]);
        const props = {
            resModel: eylem.res_model,
            type: tur,
            views: [[gorunum ? gorunum[0] : false, tur], [arama ? arama[0] : false, "search"]],
            domain: Domain.and(alanlar).toList({ ...user.context, uid: user.userId }),
            context: baglam,
            display: { controlPanel: false },
            selectRecord: (resId) =>
                this.action.doAction({ type: "ir.actions.act_window", res_model: eylem.res_model, res_id: resId,
                                       views: [[form ? form[0] : false, "form"]] }),
            createRecord: () => this.ac(),
        };
        if (gorunum) {
            props.viewId = gorunum[0];
        }
        if (baglam.group_by) {
            props.groupBy = typeof baglam.group_by === "string" ? [baglam.group_by] : baglam.group_by;
        }
        if (tur === "list") {
            props.allowSelectors = false;
        }
        return props;
    }

    ac() {
        const eylem = this.eylem;
        return this.action.doAction({
            ...eylem,
            name: this.baslik,
            domain: Domain.and([new Domain(eylem.domain || []), new Domain(this.props.domain || [])]).toList({ ...user.context, uid: user.userId }),
            context: makeContext([eylem.context || {}, this.props.context || {}]),
            views: [[false, this.state.tur], ...eylem.views.filter((v) => v[1] !== this.state.tur)],
        });
    }
}

// ============================================================================ alt sayfalar (/alt sayfalar)
export class AtlasBilgiAltSayfalar extends Component {
    static template = "atlas_bilgi.AltSayfalar";
    props = useProps({
        host: t.any().optional(),
        makale_id: t.any().optional(),
        makaleId: t.any().optional(),
    });

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = proxy({ liste: [] });
        onWillStart(async () => {
            const id = this.props.makale_id || this.props.makaleId;
            this.state.liste = id ? await this.orm.call(MODEL, "alt_makaleler", [id]) : [];
        });
    }

    async ac(id) {
        this.action.doAction(await this.orm.call(MODEL, "action_ac", [[id]]));
    }
}

// ============================================================================ yorum işareti
export class AtlasBilgiYorumIsaret extends Component {
    static template = "atlas_bilgi.YorumIsaret";
    props = useProps({
        host: t.any().optional(),
        yorum_id: t.number(),
        makaleId: t.any().optional(),
    });

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = proxy({ yorum: null, acik: false, yanit: "" });
        onWillStart(() => this.yukle());
    }

    async yukle() {
        this.state.yorum = await this.orm.call(MODEL, "yorum_getir", [this.props.yorum_id]);
    }

    get adet() {
        return this.state.yorum ? this.state.yorum.mesajlar.length : 0;
    }

    ackapa(ev) {
        ev.stopPropagation();
        ev.preventDefault();
        this.state.acik = !this.state.acik;
    }

    async yanitla() {
        if (!this.state.yanit.trim()) {
            return;
        }
        try {
            this.state.yorum = await this.orm.call(MODEL, "yorum_yanitla", [this.props.yorum_id, this.state.yanit]);
            this.state.yanit = "";
        } catch (h) {
            this.notification.add(hataMetni(h), { type: "danger" });
        }
    }

    async coz(deger) {
        this.state.yorum = await this.orm.call(MODEL, "yorum_coz", [this.props.yorum_id, deger]);
        if (deger) {
            this.state.acik = false;
        }
    }
}

export const gomuluBilesenler = [
    { name: "atlasBilgiGorunum", Component: AtlasBilgiGorunum, getProps: (host) => ({ host, ...getEmbeddedProps(host) }) },
    { name: "atlasBilgiAltSayfalar", Component: AtlasBilgiAltSayfalar, getProps: (host) => ({ host, ...getEmbeddedProps(host) }) },
    { name: "atlasBilgiYorum", Component: AtlasBilgiYorumIsaret, getProps: (host) => ({ host, ...getEmbeddedProps(host) }) },
];

export { hataMetni, markup };
