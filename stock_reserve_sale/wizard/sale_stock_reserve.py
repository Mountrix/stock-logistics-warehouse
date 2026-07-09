# Copyright 2013 Camptocamp SA - Guewen Baconnier
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools.translate import _


class SaleStockReserve(models.TransientModel):
    _name = "sale.stock.reserve"
    _description = "Sale Stock Reserve"

    @api.model
    def _default_location_id(self):
        domain = [
            "|",
            ("company_id", "=", self.env.company.id),
            ("company_id", "=", False),
        ]
        return self.env["stock.warehouse"].search(domain, limit=1).lot_stock_id

    @api.model
    def _default_location_dest_id(self):
        return self.env["stock.reservation"]._default_location_dest_id()

    @api.model
    def _default_date_validity(self):
        days = int(
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("stock_reserve_sale.reservation_validity_days", 2)
        )
        if days <= 0:
            return False
        return fields.Date.context_today(self) + timedelta(days=days)

    sale_order_id = fields.Many2one("sale.order", string="Sale Order")
    sale_line_ids = fields.Many2many(
        "sale.order.line", string="Sale Order Lines"
    )
    location_id = fields.Many2one(
        "stock.location", "Source Location", required=True, default=_default_location_id
    )
    location_dest_id = fields.Many2one(
        "stock.location",
        "Reservation Location",
        required=True,
        help="Location where the system will reserve the " "products.",
        default=_default_location_dest_id,
    )
    date_validity = fields.Date(
        "Validity Date",
        default=_default_date_validity,
        help="If a date is given, the reservations will be released "
        "at the end of the validity.",
    )
    note = fields.Text("Notes")
    owner_id = fields.Many2one("res.partner", "Stock Owner")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_model = self.env.context.get("active_model")
        active_ids = self.env.context.get("active_ids") or (
            [self.env.context["active_id"]]
            if self.env.context.get("active_id")
            else []
        )
        if active_model == "sale.order" and active_ids:
            res["sale_order_id"] = active_ids[0]
        elif active_model == "sale.order.line" and active_ids:
            res["sale_line_ids"] = [(6, 0, active_ids)]
        return res

    def _prepare_stock_reservation(self, line):
        self.ensure_one()

        picking_env = self.env["stock.picking"]
        reservation_env = self.env["stock.reservation"]
        picking_type_id = reservation_env.with_context(
            warehouse_id=line.order_id.warehouse_id.id
        )._default_picking_type_id()
        location_id = self.location_id.id
        if picking_type_id and not location_id:
            picking = self.env["stock.picking"].new(
                {"picking_type_id": picking_type_id}
            )
            picking._onchange_picking_type()
            location_id = picking.location_id.id
        location_dest_id = (
            self.location_dest_id.id or reservation_env._default_location_dest_id()
        )
        picking_id = picking_env.search(
            [
                ("sale_reserve_id", "=", line.order_id.id),
                ("location_id", "=", location_id),
                ("location_dest_id", "=", location_dest_id),
                ("state", "not in", ["cancel", "done"]),
            ],
            limit=1,
        )

        if not picking_id:
            picking_id = picking_env.create(
                {
                    "location_id": location_id,
                    "location_dest_id": location_dest_id,
                    "origin": line.order_id.name,
                    "sale_reserve_id": line.order_id.id,
                    "picking_type_id": picking_type_id,
                    "company_id": line.order_id.company_id.id,
                }
            )
        return {
            "product_id": line.product_id.id,
            "product_uom": line.product_uom_id.id,
            "product_uom_qty": line.product_uom_qty,
            "date_validity": self.date_validity,
            "name": f"{line.order_id.name} ({line.name})",
            "location_id": self.location_id.id,
            "location_dest_id": self.location_dest_id.id,
            "note": self.note,
            "price_unit": line.price_unit,
            "sale_line_id": line.id,
            "restrict_partner_id": self.owner_id.id,
            "picking_id": picking_id.id,
        }

    def stock_reserve(self, lines):
        self.ensure_one()

        if not isinstance(lines, models.BaseModel):
            lines = self.env["sale.order.line"].browse(lines)
        reservations = self.env["stock.reservation"]
        for line in lines:
            if not line.is_stock_reservable:
                continue
            vals = self._prepare_stock_reservation(line)
            reserv = self.env["stock.reservation"].create(vals)
            reserv.reserve()
            reservations |= reserv
        return reservations

    def _get_target_lines(self):
        """Determine which sale order lines to reserve.

        Rely on the values captured at wizard opening (``default_get``),
        falling back to the context for backward compatibility.
        """
        self.ensure_one()
        if self.sale_line_ids:
            return self.sale_line_ids
        if self.sale_order_id:
            return self.sale_order_id.order_line
        active_model = self.env.context.get("active_model")
        active_ids = self.env.context.get("active_ids")
        if active_model == "sale.order" and active_ids:
            return self.env["sale.order"].browse(active_ids).order_line
        if active_model == "sale.order.line" and active_ids:
            return self.env["sale.order.line"].browse(active_ids)
        return self.env["sale.order.line"]

    def button_reserve(self):
        self.ensure_one()
        lines = self._get_target_lines()
        if not lines:
            raise UserError(
                _(
                    "No sale order or lines were found to reserve. "
                    "Please open the wizard from a quotation."
                )
            )
        reservations = self.stock_reserve(lines)
        if not reservations:
            raise UserError(
                _(
                    "No reservation could be created. The selected lines are "
                    "not reservable (e.g. services, make to order products, "
                    "or lines that are already reserved)."
                )
            )
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "stock_reserve.action_stock_reservation_tree"
        )
        action["domain"] = [("id", "in", reservations.ids)]
        action["context"] = {}
        return action
