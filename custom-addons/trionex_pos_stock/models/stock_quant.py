import logging
from odoo import api, models

_logger = logging.getLogger(__name__)


class StockQuant(models.Model):
    _inherit = 'stock.quant'

    # ------------------------------------------------------------------
    # Live POS stock sync
    #
    # Whenever on-hand quantity actually changes (POS sale, delivery,
    # receipt, manual inventory adjustment, ...) we push the new on-hand
    # of the affected products to every OPEN POS session whose till has
    # stock display enabled. The POS frontend updates the figure in place
    # over the bus -- no "Reload Data" / full dataset refetch needed.
    #
    # The whole thing short-circuits with a single indexed search when no
    # relevant POS session is open, so it is essentially free at rest.
    # ------------------------------------------------------------------
    def _trionex_notify_pos_stock(self):
        quants = self.filtered(lambda q: q.location_id.usage == 'internal')
        if not quants:
            return

        open_sessions = self.env['pos.session'].sudo().search([
            ('state', 'in', ('opening_control', 'opened')),
        ])
        configs = open_sessions.config_id.filtered(
            lambda c: c.pos_display_stock and c.stock_location_id
        )
        if not configs:
            return

        product_ids = quants.product_id.ids
        Quant = self.env['stock.quant'].sudo()
        for config in configs:
            location = config.stock_location_id
            grouped = Quant._read_group(
                domain=[
                    ('product_id', 'in', product_ids),
                    ('location_id', 'child_of', location.id),
                    ('location_id.usage', '=', 'internal'),
                ],
                groupby=['product_id'],
                aggregates=['quantity:sum'],
            )
            qty_map = {product.id: qty for product, qty in grouped}
            payload = {
                'data': [
                    {
                        'product_id': pid,
                        'qty_available': qty_map.get(pid, 0.0),
                    }
                    for pid in product_ids
                ],
            }
            channel = 'pos_stock_update_%s' % config.id
            _logger.debug(
                "Trionex POS stock: pushing to channel %s -> %s",
                channel, payload['data'],
            )
            self.env['bus.bus']._sendone(channel, 'POS_STOCK_UPDATE', payload)

    @api.model_create_multi
    def create(self, vals_list):
        quants = super().create(vals_list)
        quants._trionex_notify_pos_stock()
        return quants

    def write(self, vals):
        res = super().write(vals)
        # qty_available is the on-hand sum, i.e. the `quantity` field.
        if 'quantity' in vals:
            self._trionex_notify_pos_stock()
        return res
