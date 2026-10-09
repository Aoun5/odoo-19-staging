from odoo import models, api


class ProductProduct(models.Model):
    _inherit = 'product.product'

    @api.model
    def _load_pos_data_fields(self, config_id):
        fields = super()._load_pos_data_fields(config_id)
        # qty_available -> the on-hand figure shown on the order line.
        # is_storable -> needed on the *variant* (product.product) record:
        #   core only loads it on product.template, so the POS frontend has
        #   no is_storable on product_id and the QTY display is skipped.
        for field in ('qty_available', 'is_storable'):
            if field not in fields:
                fields.append(field)
        return fields