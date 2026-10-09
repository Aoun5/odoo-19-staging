/** @odoo-module **/
import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { Orderline } from "@point_of_sale/app/components/orderline/orderline";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { _t } from "@web/core/l10n/translation";

// ---------- shared helpers ----------
function getLineProduct(line) {
    return line?.product_id || line?.get_product?.() || null;
}

function getLineQty(line) {
    return line?.qty ?? line?.quantity ?? line?.get_quantity?.() ?? 0;
}

// Returns the first line that violates stock rules, or null.
// Only enforces if restrict_low_stock is enabled on the POS config.
function findBlockingLine(cfg, lines) {
    if (!cfg?.restrict_low_stock) return null;
    const threshold = cfg.low_stock_threshold ?? 0;
    for (const line of lines || []) {
        const product = getLineProduct(line);
        if (!product?.is_storable) continue;
        const onHand = product.qty_available ?? 0;
        const ordered = getLineQty(line);
        const remaining = onHand - ordered;
        if (remaining <= threshold) {
            return { product, onHand, remaining, threshold };
        }
    }
    return null;
}

// ---------- Block payment when stock rule violated ----------
patch(PosStore.prototype, {
    async pay() {
        const blocking = findBlockingLine(this.config, this.getOrder()?.lines);
        if (blocking) {
            this.dialog.add(AlertDialog, {
                title: _t("Cannot Process Payment"),
                body: _t("%(name)s is out of stock.", {
                    name: blocking.product.display_name,
                }),
            });
            return;
        }
        return super.pay(...arguments);
    },
});

// ---------- Disable the Payment button visually ----------
patch(PosOrder.prototype, {
    canBeValidated() {
        if (!super.canBeValidated()) return false;
        return !findBlockingLine(this.config, this.lines);
    },
});

// ---------- Inline stock info on the orderline ----------
patch(Orderline.prototype, {
    setup() {
        super.setup();
        this.pos = usePos();
    },
    get availableQty() {
        const cfg = this.pos?.config;
        if (!cfg?.pos_display_stock) return null;

        const line = this.props.line;
        const product = getLineProduct(line);
        if (!product?.is_storable) return null;

        const onHand = product.qty_available ?? 0;
        const ordered = getLineQty(line);
        const remaining = onHand - ordered;
        const threshold = cfg.low_stock_threshold ?? 0;

        return {
            onHand,
            ordered,
            remaining,
            threshold,
            isOut: remaining < 0,
            isLow: remaining >= 0 && remaining <= threshold,
            displayOnHand: onHand > 999 ? "999+" : onHand,
            displayRemaining: remaining > 999 ? "999+" : remaining,
        };
    },
});