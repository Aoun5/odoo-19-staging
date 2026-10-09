import logging
from odoo import models, api

_logger = logging.getLogger(__name__)


class PosSession(models.Model):
    _inherit = 'pos.session'

    @api.model
    def _load_pos_data_models(self, config_id):
        models_list = super()._load_pos_data_models(config_id)
        return models_list + ['product.product']

    def load_data(self, models_to_load):
        result = super().load_data(models_to_load)

        if 'product.product' not in result:
            return result

        config = self.config_id

        # Skip entirely if stock display is disabled on this till
        if not config.pos_display_stock:
            return result

        # Priority: explicit POS location > picking type's source location
        location = config.stock_location_id
        if not location:
            _logger.warning(
                "Trionex POS stock: till '%s' has 'Display Stock in POS' ON but "
                "NO Stock Location set -> product cards will show GLOBAL on-hand "
                "and will NOT live-update. Set a Stock Location on this till.",
                config.name,
            )
            return result

        product_block = result['product.product']
        if isinstance(product_block, list):
            products_data = product_block
        elif isinstance(product_block, dict):
            products_data = product_block.get('data', [])
        else:
            _logger.warning("Unexpected product.product shape: %s", type(product_block))
            return result

        if not products_data:
            return result

        product_ids = [r['id'] for r in products_data]

        quants = self.env['stock.quant']._read_group(
            domain=[
                ('product_id', 'in', product_ids),
                ('location_id', 'child_of', location.id),
                ('location_id.usage', '=', 'internal'),
            ],
            groupby=['product_id'],
            aggregates=['quantity:sum'],
        )
        qty_map = {product.id: qty for product, qty in quants}

        for record in products_data:
            record['qty_available'] = qty_map.get(record['id'], 0.0)

        _logger.info(
            "Trionex POS stock loaded for till '%s' from location '%s' (%d products)",
            config.name, location.complete_name, len(products_data),
        )

        return result