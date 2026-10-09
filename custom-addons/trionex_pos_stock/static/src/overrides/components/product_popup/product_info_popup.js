/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ProductInfoBanner } from "@point_of_sale/app/components/product_info_banner/product_info_banner";
import { useEffect } from "@odoo/owl";

patch(ProductInfoBanner.prototype, {
    setup() {
        super.setup(...arguments);

        useEffect(
            () => {
                const productId =
                    this.props.product?.id ||
                    this.props.productTemplate?.product_variant_id?.[0];

                const products = this.pos.models["product.product"];

                const product = products.find((p) => p.id === productId);

                if (product) {
                    this.state.free_qty = product.qty_available || 0;
                    this.state.available_quantity = product.qty_available || 0;
                }
            },
            () => [this.state.free_qty]
        );
    },
});