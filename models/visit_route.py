from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class VisitRoute(models.Model):
    _name = "visit.route"
    _description = "Visit Route Assignment"
    _order = "route_date desc, user_id"

    name = fields.Char(required=True, default=lambda self: self._default_name())
    user_id = fields.Many2one(
        "res.users", string="Salesperson", required=True,
        default=lambda self: self.env.user
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('wait_approval', 'Approval Requested'),
        ('confirmed', 'Approved'),
    ], string="Status", default='draft', required=True, tracking=True)

    route_date = fields.Date(string="Route Date", required=True, default=fields.Date.context_today)
    line_ids = fields.One2many("visit.route.line", "route_id", string="Stops")
    stop_count = fields.Integer(compute="_compute_stop_count")
    total_estimated_duration = fields.Float(
        string="Total Estimated Duration (min)",
        compute="_compute_total_estimated_duration",
        store=True,
        help="Sum of estimated duration for all stops"
    )

    _sql_constraints = [
        (
            'route_user_date_unique',
            'unique(user_id, route_date)',
            'A salesperson can only have one route per day.'
        ),
    ]

    @api.model
    def _default_name(self):
        return _("Route")

    @api.model
    def is_sales_manager(self):
        return bool(self.env.user.has_group('sales_team.group_sale_manager'))

    @api.model
    def get_current_user(self, *args, **kwargs):
        return {
            'id': self.env.user.id,
            'name': self.env.user.name,
        }

    @api.depends("line_ids")
    def _compute_stop_count(self):
        for record in self:
            record.stop_count = len(record.line_ids)

    @api.depends("line_ids.estimated_duration_minutes")
    def _compute_total_estimated_duration(self):
        for record in self:
            record.total_estimated_duration = sum(
                record.line_ids.mapped("estimated_duration_minutes")
            )

    @api.model_create_multi
    def create(self, vals_list):
        # Manager created routes are auto-confirmed (approved) if assigned to others
        is_manager = self.env.user.has_group('sales_team.group_sale_manager')
        for vals in vals_list:
            if not is_manager:
                vals['user_id'] = self.env.user.id
                vals['state'] = 'draft' # Salespeople always start in draft
            elif vals.get('user_id') and vals['user_id'] != self.env.user.id:
                 # Manager creating for someone else -> Auto-approve
                 vals['state'] = 'confirmed'
        return super().create(vals_list)

    def write(self, vals):
        is_manager = self.env.user.has_group('sales_team.group_sale_manager')
        
        # Non-managers cannot change user_id
        if 'user_id' in vals and not is_manager:
            raise UserError(_('Only managers can assign routes to other users.'))
            
        for route in self:
            # Prevent salespeople from editing if not in draft
            if not is_manager and route.state != 'draft':
                 raise UserError(_('You cannot edit a route that is pending approval or already approved.'))
            
            # Prevent salespeople from editing manager-created routes even in draft (if that happens)
            if not is_manager and route.create_uid.id != self.env.user.id:
                 raise UserError(_('You cannot edit a route created by your manager.'))

        return super().write(vals)

    def action_request_approval(self):
        for route in self:
            if route.state != 'draft':
                continue
            if not route.line_ids:
                raise UserError(_('You cannot request approval for an empty route.'))
            route.state = 'wait_approval'

    def action_approve(self):
        if not self.env.user.has_group('sales_team.group_sale_manager'):
            raise UserError(_('Only managers can approve routes.'))
        self.write({'state': 'confirmed'})

    def action_reset_draft(self):
        if not self.env.user.has_group('sales_team.group_sale_manager'):
            raise UserError(_('Only managers can reset routes to draft.'))
        self.write({'state': 'draft'})

    @api.model
    def get_route_map_data(self, user_id=False, route_date=False):
        if not user_id:
            user_id = self.env.user.id
        if not route_date:
            route_date = fields.Date.context_today(self)

        route = self.search([
            ("user_id", "=", int(user_id)),
            ("route_date", "=", route_date),
        ], limit=1)

        if not route:
            return {
                "route": False,
                "stops": [],
            }

        lines = route.line_ids.sorted(key=lambda l: (l.sequence, l.id))
        lead_ids = lines.mapped("lead_id").ids

        stops = []
        for idx, line in enumerate(lines, start=1):
            lead = line.lead_id

            partner_lat = False
            partner_lon = False
            if lead.partner_id and "partner_latitude" in lead.partner_id._fields and "partner_longitude" in lead.partner_id._fields:
                partner_lat = lead.partner_id.partner_latitude
                partner_lon = lead.partner_id.partner_longitude

            latitude = line.latitude
            longitude = line.longitude

            if lead.manual_location_is_approx:
                pin_type = "manual_approx"
            else:
                eps = 0.000001
                is_partner_coord = bool(
                    partner_lat is not False and partner_lon is not False and
                    abs(latitude - partner_lat) <= eps and
                    abs(longitude - partner_lon) <= eps
                )
                pin_type = "known" if is_partner_coord else "manual_exact"

            address = lead.manual_location_address or False

            stops.append({
                "sequence": idx,
                "route_line_id": line.id,
                "lead_id": lead.id,
                "lead_name": lead.display_name,
                "partner_name": lead.partner_id.display_name if lead.partner_id else False,
                "latitude": latitude,
                "longitude": longitude,
                "pin_type": pin_type,
                "address": address,
            })

        return {
            "route": {
                "id": route.id,
                "name": route.name,
            },
            "stops": stops,
        }


class VisitRouteLine(models.Model):
    _name = "visit.route.line"
    _description = "Visit Route Stop"
    _order = "sequence, id"

    route_id = fields.Many2one("visit.route", required=True, ondelete="cascade")
    sequence = fields.Integer(default=10)
    lead_id = fields.Many2one("crm.lead", string="Lead/Opportunity", required=True)
    partner_id = fields.Many2one("res.partner", related="lead_id.partner_id", readonly=True)
    latitude = fields.Float(string="Latitude", digits=(10, 7))
    longitude = fields.Float(string="Longitude", digits=(10, 7))
    estimated_duration_minutes = fields.Float(
        string="Planned Duration",
        default=30.0,
        help="Estimated time to spend at this stop (in minutes)"
    )

    _sql_constraints = [
        ("route_lead_unique", "unique(route_id, lead_id)", "This lead is already on the route."),
    ]

    @api.onchange("lead_id")
    def _onchange_lead_id_set_coordinates(self):
        for line in self:
            if not line.lead_id:
                continue
            lat, lon = line._get_default_coordinates_from_lead(line.lead_id)
            if lat is not False and lon is not False:
                line.latitude = lat
                line.longitude = lon

    def _get_partner_coordinates(self, partner):
        if not partner:
            return (False, False)
        if "partner_latitude" not in partner._fields or "partner_longitude" not in partner._fields:
            return (False, False)
        lat = partner.partner_latitude
        lon = partner.partner_longitude
        if lat is False or lon is False:
            return (False, False)
        return (lat, lon)

    def _get_default_coordinates_from_lead(self, lead):
        if not lead:
            return (False, False)
        lat, lon = self._get_partner_coordinates(lead.partner_id)
        if lat is not False and lon is not False:
            return (lat, lon)
        if lead.manual_latitude is not False and lead.manual_longitude is not False:
            return (lead.manual_latitude, lead.manual_longitude)
        return (False, False)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("lead_id") and ("latitude" not in vals or "longitude" not in vals):
                lead = self.env["crm.lead"].browse(vals["lead_id"])
                lat, lon = self._get_default_coordinates_from_lead(lead)
                if lat is not False and lon is not False:
                    vals.setdefault("latitude", lat)
                    vals.setdefault("longitude", lon)
        records = super().create(vals_list)
        records._check_coordinates_required()
        return records

    def write(self, vals):
        res = super().write(vals)
        self._check_coordinates_required()
        return res

    @api.constrains("latitude", "longitude")
    def _check_coordinates_required(self):
        for line in self:
            if line.latitude is False or line.longitude is False:
                raise ValidationError(_("Latitude and Longitude are required for each route stop."))
            if line.latitude < -90.0 or line.latitude > 90.0:
                raise ValidationError(_("Latitude must be between -90 and 90."))
            if line.longitude < -180.0 or line.longitude > 180.0:
                raise ValidationError(_("Longitude must be between -180 and 180."))
