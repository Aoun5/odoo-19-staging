from odoo import fields, models, api

class PosConfig(models.Model):
    _inherit = 'pos.config'

    pos_display_stock = fields.Boolean(
        string='Display Stock in POS',
        default=True,
        store=True,
    )
    stock_location_id = fields.Many2one(
        'stock.location',
        string='POS Stock Location',
        domain=[('usage', '=', 'internal')],
        help='Stock from this location is shown on this POS terminal.',
        store=True,
    )
    restrict_low_stock = fields.Boolean(
        string='Restrict Low Stock Orders',
        default=False,
        help='Block adding a product when on-hand qty is at or below the threshold.',
        store=True,
    )
    low_stock_threshold = fields.Float(
        string='Low Stock Threshold',
        default=0.0,
        store=True,
    )