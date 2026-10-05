import { Component, xml } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";

/** Üst çubukta Studio düğmesi: açık ekranın eylemi/modeliyle Studio'yu açar ya da Studio'dan çıkar. */
export class AtlasStudioDugme extends Component {
    static template = xml`
        <div class="o_atlas_studio_systray d-flex align-items-center">
            <button type="button" class="btn btn-link px-2 o_atlas_studio_ac" title="Studio" t-on-click="() => this.ac()">
                <i class="oi fs-5" data-icon="tune"/>
            </button>
        </div>`;

    setup() {
        this.action = useService("action");
    }

    ac() {
        const denetci = this.action.currentController;
        const eylem = denetci?.action;
        if (eylem?.tag === "atlas_studio.studio") {
            return this.action.doAction(eylem.params?.donus_action_id || "home", { clearBreadcrumbs: true }).catch(() =>
                this.action.doAction({ type: "ir.actions.client", tag: "reload" })
            );
        }
        const params = {};
        if (eylem?.type === "ir.actions.act_window") {
            params.action_id = eylem.id;
            params.model = eylem.res_model;
            params.view_type = denetci.view?.type;
            params.donus_action_id = eylem.id;
        }
        return this.action.doAction({ type: "ir.actions.client", tag: "atlas_studio.studio", name: "Studio", params }, { clearBreadcrumbs: true });
    }
}

if (user.isSystem) {
    registry.category("systray").add("atlas_studio", { Component: AtlasStudioDugme }, { sequence: 2 });
}
