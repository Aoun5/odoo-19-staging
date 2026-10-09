from odoo import fields, models

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    pos_pos_display_stock = fields.Boolean(
        related='pos_config_id.pos_display_stock', readonly=False)
    pos_stock_location_id = fields.Many2one(
        related='pos_config_id.stock_location_id', readonly=False)
    pos_restrict_low_stock = fields.Boolean(
        related='pos_config_id.restrict_low_stock', readonly=False)
    pos_low_stock_threshold = fields.Float(
        related='pos_config_id.low_stock_threshold', readonly=False)