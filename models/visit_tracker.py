from odoo import _, models, fields, api
from odoo.exceptions import UserError, ValidationError
import requests
import logging
import math
from psycopg2 import IntegrityError

_logger = logging.getLogger(__name__)


class VisitTracker(models.Model):
    _name = 'visit.tracker'
    _description = 'Salesperson Visit Tracker'
    _order = 'visit_date desc'

    user_id = fields.Many2one(
        'res.users', string='Salesperson',
        default=lambda self: self.env.user, required=True, readonly=True
    )
    lead_id = fields.Many2one(
        'crm.lead', string='Lead/Opportunity',
        help='The CRM lead or opportunity this visit is related to'
    )
    partner_id = fields.Many2one('res.partner', string='Customer')
    visit_date = fields.Datetime(
        string='Visit Date', default=fields.Datetime.now,
        required=True, readonly=True
    )
    check_out_date = fields.Datetime(string='Check Out', readonly=True)
    route_line_id = fields.Many2one(
        'visit.route.line', string='Planned Route Stop',
        help='Link to the planned route stop if this visit was part of a route'
    )
    planned_duration_minutes = fields.Float(
        string='Planned Duration (min)',
        related='route_line_id.estimated_duration_minutes',
        store=True, readonly=True
    )
    is_planned = fields.Boolean(
        string='Was Planned', compute='_compute_is_planned', store=True,
        help='True if this visit was linked to a planned route stop'
    )
    force_zero_duration = fields.Boolean(
        string='Force Zero Duration', default=False,
        help='If true, duration is set to 0 regardless of timestamps (e.g. check out out of range)'
    )
    duration_minutes = fields.Float(
        string='Time Spent (min)', compute='_compute_duration', store=True, readonly=True
    )
    duration_hours = fields.Float(
        string='Time Spent (hours)', compute='_compute_duration', store=True, readonly=True
    )
    latitude = fields.Float(string='Latitude', digits=(10, 7), readonly=True)
    longitude = fields.Float(string='Longitude', digits=(10, 7), readonly=True)
    check_out_latitude = fields.Float(string='Check Out Latitude', digits=(10, 7), readonly=True)
    check_out_longitude = fields.Float(string='Check Out Longitude', digits=(10, 7), readonly=True)
    check_out_location_address = fields.Char(string='Check Out Address', readonly=True)
    device_info = fields.Char(string='Device Info', readonly=True)
    location_address = fields.Char(
        string='Address', readonly=True,
        help='Address of check-in location'
    )
    notes = fields.Text(string='Visit Notes', help='Additional notes about this visit')
    maps_url = fields.Char(
        string='Map Link', compute='_compute_maps_url', store=False
    )
    check_out_maps_url = fields.Char(
        string='Check Out Map Link', compute='_compute_check_out_maps_url', store=False
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('done', 'Checked In'),
        ('checked_out', 'Checked Out'),
        ('cancellation_requested', 'Cancellation Requested'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', readonly=True)

    def init(self):
        # Enforce at DB level: a user can have only one active check-in at a time.
        # This closes race conditions (double click / multi-tab / multiple workers).
        try:
            self._cr.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS visit_tracker_one_active_per_user
                ON visit_tracker (user_id)
                WHERE state = 'done'
            """)
        except Exception:
            # If there are already duplicate active check-ins in the database, Postgres will
            # refuse to create the index. Keep the module usable, but log the issue so an
            # admin can resolve duplicates and re-run upgrade.
            _logger.exception(
                "Could not create unique index visit_tracker_one_active_per_user. "
                "There may be duplicate active check-ins (state='done') per user."
            )

    pre_cancellation_state = fields.Selection([
        ('draft', 'Draft'),
        ('done', 'Checked In'),
        ('checked_out', 'Checked Out'),
    ], string='State Before Cancellation', readonly=True)

    cancellation_reason = fields.Text(
        string='Cancellation Reason',
        help='Reason given by the salesperson for requesting cancellation'
    )
    cancellation_request_date = fields.Datetime(
        string='Cancellation Requested On', readonly=True
    )
    cancelled_by_id = fields.Many2one(
        'res.users', string='Cancelled By', readonly=True,
        help='User (manager) who approved the cancellation'
    )
    rejection_reason = fields.Text(
        string='Rejection Reason',
        help='Reason given by the manager when rejecting the cancellation request'
    )

    @api.depends('visit_date', 'check_out_date', 'force_zero_duration')
    def _compute_duration(self):
        for record in self:
            if record.force_zero_duration:
                record.duration_minutes = 0.0
                record.duration_hours = 0.0
                continue
            
            duration_minutes = 0.0
            duration_hours = 0.0
            if record.visit_date and record.check_out_date:
                start_dt = fields.Datetime.to_datetime(record.visit_date)
                end_dt = fields.Datetime.to_datetime(record.check_out_date)
                if start_dt and end_dt:
                    seconds = (end_dt - start_dt).total_seconds()
                    if seconds > 0:
                        duration_minutes = seconds / 60.0
                        duration_hours = seconds / 3600.0
            record.duration_minutes = duration_minutes
            record.duration_hours = duration_hours

    @api.depends('route_line_id')
    def _compute_is_planned(self):
        for record in self:
            record.is_planned = bool(record.route_line_id)

    @api.constrains('user_id', 'state')
    def _check_single_active_check_in(self):
        for record in self.filtered(lambda r: r.user_id and r.state == 'done'):
            domain = [
                ('id', '!=', record.id),
                ('user_id', '=', record.user_id.id),
                ('state', '=', 'done'),
            ]
            if self.search_count(domain):
                raise ValidationError(
                    _('You already have an active check-in. Please check out before checking in to another lead.')
                )

    @api.depends('latitude', 'longitude')
    def _compute_maps_url(self):
        for record in self:
            if record.latitude and record.longitude:
                record.maps_url = (
                    f'https://www.openstreetmap.org/'
                    f'?mlat={record.latitude}&mlon={record.longitude}'
                )
            else:
                record.maps_url = False

    @api.depends('check_out_latitude', 'check_out_longitude')
    def _compute_check_out_maps_url(self):
        for record in self:
            if record.check_out_latitude and record.check_out_longitude:
                record.check_out_maps_url = (
                    f'https://www.openstreetmap.org/'
                    f'?mlat={record.check_out_latitude}&mlon={record.check_out_longitude}'
                )
            else:
                record.check_out_maps_url = False

    def action_check_in(self, lat, long, device_info, address=False):
        """Method called by JS to save location"""
        for record in self:
            if record.user_id and record.user_id != self.env.user and not self.env.user.has_group('sales_team.group_sale_manager'):
                raise UserError(_('You can only check in your own visits.'))

            # Concurrency guard: lock a stable row (res_users) so two concurrent requests
            # cannot both pass the active-visit check when no active visit rows exist yet.
            self.env.cr.execute(
                "SELECT id FROM res_users WHERE id = %s FOR UPDATE",
                (record.user_id.id,),
            )

            active_visit = self.search([
                ('user_id', '=', record.user_id.id),
                ('state', '=', 'done'),
                ('id', '!=', record.id),
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

            # If no address provided, try to get it via reverse geocoding on server side
            if not address and lat and long:
                address = self._get_address_from_coordinates(lat, long)
            
            try:
                record.write({
                    'latitude': lat,
                    'longitude': long,
                    'device_info': device_info,
                    'location_address': address,
                    'visit_date': fields.Datetime.now(),
                    'check_out_date': False,
                    'state': 'done'
                })
            except IntegrityError:
                self.env.cr.rollback()
                raise UserError(_('You already have an active check-in. Please check out before checking in to another lead.'))

    @api.model
    def get_active_check_in_info(self):
        active_visit = self.search([
            ('user_id', '=', self.env.user.id),
            ('state', '=', 'done'),
        ], order='visit_date desc', limit=1)

        if not active_visit:
            return {'active': False}

        return {
            'active': True,
            'id': active_visit.id,
            'lead_name': active_visit.lead_id.display_name if active_visit.lead_id else False,
            'partner_name': active_visit.partner_id.display_name if active_visit.partner_id else False,
            'visit_date': active_visit.visit_date,
        }

    def action_check_out(self, latitude=False, longitude=False):
        for record in self:
            if record.state != 'done':
                raise UserError(_('Only active check-ins can be checked out.'))
            if record.user_id != self.env.user and not self.env.user.has_group('sales_team.group_sale_manager'):
                raise UserError(_('You can only check out your own visits.'))
            if record.check_out_date:
                raise UserError(_('This visit is already checked out.'))

            vals = {
                'check_out_date': fields.Datetime.now(),
                'state': 'checked_out',
            }

            if latitude and longitude:
                vals.update({
                    'check_out_latitude': latitude,
                    'check_out_longitude': longitude,
                    'check_out_location_address': self._get_address_from_coordinates(latitude, longitude),
                })

            # If checkout coordinates are provided, check distance
            if latitude and longitude and record.latitude and record.longitude:
                distance = self._calculate_distance(
                    record.latitude, record.longitude,
                    latitude, longitude
                )
                if distance > 100:  # Distance in meters
                    vals['force_zero_duration'] = True
                    # Optionally log a note or separate field about the out-of-range checkout
                    msg = _("Checked out more than 100m away (%.2fm). Time spent set to 0.") % distance
                    _logger.warning("visit.tracker %s: %s", record.id, msg)
                    if record.notes:
                        vals['notes'] = (record.notes + "\n" + msg)
                    else:
                        vals['notes'] = msg

            record.write(vals)

    @staticmethod
    def _calculate_distance(lat1, lon1, lat2, lon2):
        """
        Calculate the great circle distance between two points 
        on the earth (specified in decimal degrees)
        """
        # Convert decimal degrees to radians
        lon1, lat1, lon2, lat2 = map(math.radians, [lon1, lat1, lon2, lat2])

        # Haversine formula 
        dlon = lon2 - lon1 
        dlat = lat2 - lat1 
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a)) 
        r = 6371000 # Radius of earth in meters
        return c * r

    @api.model
    def _get_address_from_coordinates(self, latitude, longitude):
        """
        Perform reverse geocoding using Nominatim from the server side.
        This avoids CORS issues when calling from JavaScript.
        """
        try:
            url = (
                f'https://nominatim.openstreetmap.org/reverse'
                f'?format=json&lat={latitude}&lon={longitude}'
                f'&zoom=18&addressdetails=1'
            )
            headers = {
                'User-Agent': 'OdooVisitTracker/1.0 (your-email@example.com)'
            }
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return data.get('display_name', False)
            else:
                _logger.warning(
                    f"Nominatim returned status {response.status_code}"
                )
        except Exception as e:
            _logger.warning(f"Reverse geocoding failed: {e}")
        return False

    def action_request_cancellation(self):
        """Salesperson requests cancellation of their visit. Only the visit owner can request."""
        for record in self:
            if record.state not in ('done', 'checked_out'):
                continue
            if record.user_id != self.env.user:
                raise UserError(
                    _('Only the salesperson who recorded this visit can request its cancellation.')
                )
            record.write({
                'pre_cancellation_state': record.state,
                'state': 'cancellation_requested',
                'cancellation_request_date': fields.Datetime.now(),
            })

    def action_approve_cancellation(self):
        """Sales manager approves the cancellation request."""
        if not self.env.user.has_group('sales_team.group_sale_manager'):
            raise UserError(_('Only sales managers can approve cancellation requests.'))
        for record in self:
            if record.state != 'cancellation_requested':
                continue
            record.write({
                'state': 'cancelled',
                'cancelled_by_id': self.env.user.id,
                'pre_cancellation_state': False,
                'rejection_reason': False,
            })

    def action_reject_cancellation(self):
        """Sales manager rejects the cancellation request. Visit returns to Checked In."""
        if not self.env.user.has_group('sales_team.group_sale_manager'):
            raise UserError(_('Only sales managers can reject cancellation requests.'))
        for record in self:
            if record.state != 'cancellation_requested':
                continue
            record.write({
                'state': record.pre_cancellation_state or 'done',
                'cancelled_by_id': False,
                'cancellation_request_date': False,
                'pre_cancellation_state': False,
            })
