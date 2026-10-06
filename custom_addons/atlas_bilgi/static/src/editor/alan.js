import { registry } from "@web/core/registry";
import { HtmlField, htmlField } from "@html_editor/fields/html_field";
import { gomuluBilesenler } from "./gomulu";
import { AtlasBilgiPlugin } from "./eklenti";

/** Bilgi Bankası makale gövdesi: standart HTML alanı + gömülü görünümler, alt sayfalar, yorumlar. */
export class AtlasBilgiHtmlField extends HtmlField {
    getConfig() {
        const config = super.getConfig();
        config.Plugins = [...config.Plugins, AtlasBilgiPlugin];
        if (config.resources?.embedded_components) {
            config.resources.embedded_components = [...config.resources.embedded_components, ...gomuluBilesenler];
        }
        return config;
    }

    getReadonlyConfig() {
        const config = super.getReadonlyConfig();
        config.embeddedComponents = [...(config.embeddedComponents || []), ...gomuluBilesenler];
        return config;
    }
}

registry.category("fields").add("atlas_bilgi_html", { ...htmlField, component: AtlasBilgiHtmlField });
