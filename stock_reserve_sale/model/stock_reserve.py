# Copyright 2013 Camptocamp SA - Guewen Baconnier
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import api, fields, models


class StockReservation(models.Model):
    _inherit = "stock.reservation"

    sale_line_id = fields.Many2one(
        "sale.order.line", string="Sale Order Line", ondelete="cascade", copy=False
    )
    sale_id = fields.Many2one(
        "sale.order", string="Sale Order", store=True, related="sale_line_id.order_id"
    )

    @api.model
    def _default_picking_type_id(self):
        """Outgoing operation type of the warehouse, never a foreign one.

        `stock_reserve` resolves the `stock.picking_type_out` xmlid, which is
        only an alias of the type of `stock.warehouse0` and so belongs to the
        main company: the `Stock Operation Type multi-company` rule blocks it
        for anybody working in another company. Searching keeps the record
        rules in play, so an unreadable type is never handed back.
        """
        picking_type_env = self.env["stock.picking.type"]
        domain = [("code", "=", "outgoing")]
        warehouse_id = self.env.context.get("warehouse_id")
        if warehouse_id:
            picking_type = picking_type_env.search(
                domain + [("warehouse_id", "=", warehouse_id)], limit=1
            )
            if picking_type:
                return picking_type.id
        return picking_type_env.search(
            domain + [("company_id", "=", self.env.company.id)], limit=1
        ).id

    def release_reserve(self):
        self.update({"sale_line_id": False})
        return super().release_reserve()

    def action_view_reserves_stock_picking_reservation(self):
        stock_picking = self.env["stock.picking"]
        action = self.env["ir.actions.actions"]._for_xml_id(
            "stock.action_picking_tree_all"
        )
        if self.sale_id:
            stock_picking = self.env["stock.picking"].search(
                [("sale_id", "=", self.sale_id.id), ("state", "!=", "cancel")], limit=1
            )
        if stock_picking:
            view_id = self.env.ref("stock.view_picking_form").id
            action.update(views=[(view_id, "form")], res_id=stock_picking.id)
        return action
