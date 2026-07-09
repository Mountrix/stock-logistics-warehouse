# Copyright 2013 Camptocamp SA - Guewen Baconnier
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    stock_reservation_validity_days = fields.Integer(
        string="Reservation Validity (days)",
        default=2,
        config_parameter="stock_reserve_sale.reservation_validity_days",
        help="Default number of days added to today used as the "
        "validity date when reserving stock from a quotation.",
    )
