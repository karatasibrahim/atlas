import { Component, onWillDestroy, onWillStart, proxy } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { useBus, useService } from "@web/core/utils/hooks";

const { DateTime } = luxon;

/** Çalışan zaman sayacını üst çubukta gösterir. */
export class AtlasZamanSystray extends Component {
    static template = "atlas_zaman.Systray";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = proxy({ sayac: false, simdi: Date.now(), yetkili: false });
        this.zamanlayici = browser.setInterval(() => (this.state.simdi = Date.now()), 1000);
        onWillDestroy(() => browser.clearInterval(this.zamanlayici));
        useBus(this.env.bus, "atlas_zaman:sayac", () => this.yukle());
        onWillStart(async () => {
            this.state.yetkili = await user.hasGroup("hr_timesheet.group_hr_timesheet_user");
            await this.yukle();
        });
    }

    async yukle() {
        if (!this.state.yetkili) {
            return;
        }
        try {
            this.state.sayac = await this.orm.call("atlas.zaman.sayac", "atlas_durum", []);
        } catch {
            this.state.sayac = false;
        }
    }

    get sure() {
        if (!this.state.sayac) {
            return "";
        }
        const bas = DateTime.fromSQL(this.state.sayac.baslangic, { zone: "utc" });
        const sn = Math.max(0, Math.floor((this.state.simdi - bas.toMillis()) / 1000));
        const s = Math.floor(sn / 3600);
        const d = Math.floor((sn % 3600) / 60);
        return `${s}:${String(d).padStart(2, "0")}:${String(sn % 60).padStart(2, "0")}`;
    }

    get ipucu() {
        const s = this.state.sayac;
        return s ? `${s.project_ad}${s.task_ad ? " / " + s.task_ad : ""}` : "";
    }

    ac() {
        this.action.doAction("atlas_zaman.action_atlas_zaman_haftalik");
    }

    async durdur() {
        const sonuc = await this.orm.call("atlas.zaman.sayac", "atlas_durdur", [[this.state.sayac.id]]);
        const saat = sonuc[0]?.saat || 0;
        this.notification.add(_t("%s saat zaman kaydına yazıldı.", saat.toFixed(2)), { type: "success" });
        this.state.sayac = false;
        this.env.bus.trigger("atlas_zaman:sayac");
    }
}

registry.category("systray").add("atlas_zaman.Systray", { Component: AtlasZamanSystray }, { sequence: 90 });
