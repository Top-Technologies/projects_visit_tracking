from odoo import _, models, fields, api
from odoo.exceptions import UserError, ValidationError
import logging
import requests
from psycopg2 import IntegrityError


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    visit_tracker_ids = fields.One2many(
        'visit.tracker', 'lead_id', string='Visit Trackers'
    )
    visit_count = fields.Integer(
        string='Visits', compute='_compute_visit_count'
    )

    active_visit_id = fields.Many2one(
        'visit.tracker', compute='_compute_active_visit', readonly=True
    )
    has_active_visit = fields.Boolean(
        compute='_compute_active_visit', readonly=True
    )

    manual_latitude = fields.Float(string='Manual Latitude', digits=(10, 7))
    manual_longitude = fields.Float(string='Manual Longitude', digits=(10, 7))
    manual_location_address = fields.Char(
        string='Manual Location / Address',
        help='For leads without captured GPS data, a manager can provide a general address/description or coordinates.'
    )
    manual_location_is_approx = fields.Boolean(
        string='Approximate Location',
        help='If enabled, the pin will be shown as an approximate location (different marker style).'
    )

    @api.constrains('manual_latitude', 'manual_longitude')
    def _check_manual_coordinates_range(self):
        for record in self:
            if record.manual_latitude is not False and (record.manual_latitude < -90.0 or record.manual_latitude > 90.0):
                raise ValidationError(_('Latitude must be between -90 and 90.'))
            if record.manual_longitude is not False and (record.manual_longitude < -180.0 or record.manual_longitude > 180.0):
                raise ValidationError(_('Longitude must be between -180 and 180.'))

    _manual_location_fields = {
        'manual_latitude',
        'manual_longitude',
        'manual_location_address',
        'manual_location_is_approx',
    }

    def _check_manual_location_write_rights(self, vals):
        # Permission check removed - all users can now set manual location fields
        pass

    @api.model
    def _geocode_address(self, address):
        if not address:
            return (False, False)
        try:
            url = 'https://nominatim.openstreetmap.org/search'
            headers = {
                'User-Agent': 'OdooVisitTracker/1.0 (your-email@example.com)'
            }
            response = requests.get(
                url,
                headers=headers,
                params={'format': 'json', 'q': address, 'limit': 1},
                timeout=10,
            )
            if response.status_code != 200:
                return (False, False)
            data = response.json() or []
            if not data:
                return (False, False)
            lat = float(data[0].get('lat')) if data[0].get('lat') else False
            lon = float(data[0].get('lon')) if data[0].get('lon') else False
            return (lat, lon)
        except Exception:
            return (False, False)

    def _enrich_manual_location_vals(self, vals):
        if not vals:
            return vals

        address = vals.get('manual_location_address')
        if address and not vals.get('manual_latitude') and not vals.get('manual_longitude'):
            lat, lon = self._geocode_address(address)
            if lat and lon:
                vals = dict(vals)
                vals.setdefault('manual_latitude', lat)
                vals.setdefault('manual_longitude', lon)
                vals.setdefault('manual_location_is_approx', True)
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        enriched_vals_list = []
        for vals in vals_list:
            self._check_manual_location_write_rights(vals)
            enriched_vals_list.append(self._enrich_manual_location_vals(vals))
        return super().create(enriched_vals_list)

    def write(self, vals):
        self._check_manual_location_write_rights(vals)
        vals = self._enrich_manual_location_vals(vals)
        return super().write(vals)

    @api.depends('visit_tracker_ids')
    def _compute_visit_count(self):
        for record in self:
            record.visit_count = len(record.visit_tracker_ids)

    @api.depends('visit_tracker_ids.state', 'visit_tracker_ids.user_id')
    def _compute_active_visit(self):
        for record in self:
            active_visit = record.visit_tracker_ids.filtered(
                lambda v: v.state == 'done' and v.user_id == self.env.user
            )
            active_visit = active_visit[:1]
            record.active_visit_id = active_visit.id if active_visit else False
            record.has_active_visit = bool(active_visit)

    def action_view_visits(self):
        """Open visit tracker records for this lead"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Visits',
            'res_model': 'visit.tracker',
            'view_mode': 'list,form',
            'domain': [('lead_id', '=', self.id)],
            'context': {'default_lead_id': self.id},
        }

    def action_check_in(self, lat, long, device_info, address=False):
        """Create a visit tracker record and mark it as checked in"""
        self.ensure_one()

        # Concurrency guard: lock a stable row (res_users) so two concurrent requests
        # cannot both pass the active-visit check when no active visit rows exist yet.
        self.env.cr.execute(
            "SELECT id FROM res_users WHERE id = %s FOR UPDATE",
            (self.env.user.id,),
        )

        active_visit = self.env['visit.tracker'].search([
            ('user_id', '=', self.env.user.id),
            ('state', '=', 'done'),
        ], limit=1)
        if active_visit:
            lead_name = active_visit.lead_id.display_name if active_visit.lead_id else ''
            partner_name = active_visit.partner_id.display_name if active_visit.partner_id else ''
            visit_date = active_visit.visit_date or ''
            if lead_name or partner_name:
                place = lead_name or partner_name
                if lead_name and partner_name and partner_name != lead_name:
                    place = f'{lead_name} ({partner_name})'
                raise UserError(
                    _('You are already checked in to %(place)s since %(time)s. Please check out before starting a new visit.')
                    % {'place': place, 'time': visit_date}
                )
            raise UserError(
                _('You are already checked in to another lead. Please check out before starting a new visit.')
            )
        
        # Create the visit record first (in draft state)
        try:
            visit = self.env['visit.tracker'].create({
                'lead_id': self.id,
                'partner_id': self.partner_id.id if self.partner_id else False,
                'latitude': lat,
                'longitude': long,
                'device_info': device_info,
                'state': 'draft',
            })
        except IntegrityError:
            self.env.cr.rollback()
            raise UserError(_('You already have an active check-in. Please check out before checking in to another lead.'))
        
        # Call the visit tracker's action_check_in to handle address lookup
        # This ensures the server-side geocoding is used
        try:
            visit.action_check_in(lat, long, device_info, address)
        except IntegrityError:
            self.env.cr.rollback()
            raise UserError(_('You already have an active check-in. Please check out before checking in to another lead.'))
        
        # Auto-fill manual coordinates on the lead if they are not already set
        # This allows route planning to use the captured GPS location
        if lat and long and not self.manual_latitude and not self.manual_longitude:
            # Use sudo() to bypass the manager permission check since we're 
            # recording actual GPS data captured during the salesperson's check-in
            self.sudo().write({
                'manual_latitude': lat,
                'manual_longitude': long,
            })
        
        return visit.id

    def action_check_out(self, latitude=False, longitude=False):
        self.ensure_one()
        active_visit = self.env['visit.tracker'].search([
            ('lead_id', '=', self.id),
            ('user_id', '=', self.env.user.id),
            ('state', '=', 'done'),
        ], order='visit_date desc', limit=1)
        if not active_visit:
            raise UserError(_('You have no active check-in on this lead.'))
        active_visit.action_check_out(latitude=latitude, longitude=longitude)
        return True
