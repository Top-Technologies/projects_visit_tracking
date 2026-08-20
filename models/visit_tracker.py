import logging
import math
import requests
from psycopg2 import IntegrityError

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class VisitTracker(models.Model):
    _name = 'visit.tracker'
    _description = 'Project Field Check-in'
    _order = 'visit_date desc'

    user_id = fields.Many2one(
        'res.users', string='Employee / Team Member',
        default=lambda self: self.env.user, required=True, readonly=True
    )
    project_id = fields.Many2one(
        'project.project', string='Project',
        required=True,
        help='The project this field visit is related to'
    )
    plan_id = fields.Many2one(
        'visit.plan', string='Visit Plan',
        help='Link to the approved visit plan if this visit was planned'
    )
    plan_line_id = fields.Many2one(
        'visit.plan.line', string='Plan Stop / Sub-Site',
        help='Link to the specific planned site stop if part of a multi-stop plan'
    )
    visit_date = fields.Datetime(
        string='Check-in Date', default=fields.Datetime.now,
        required=True, readonly=True
    )
    check_out_date = fields.Datetime(string='Check-out Date', readonly=True)

    planned_hours = fields.Float(
        string='Planned Hours',
        compute='_compute_planned_metrics',
        store=True, readonly=True
    )
    planned_duration_minutes = fields.Float(
        string='Planned Duration (min)',
        compute='_compute_planned_metrics',
        store=True, readonly=True
    )
    is_planned = fields.Boolean(
        string='Was Planned', compute='_compute_is_planned', store=True,
        help='True if this visit was linked to an approved visit plan'
    )
    force_zero_duration = fields.Boolean(
        string='Force Zero Duration', default=False,
        help='If true, duration is set to 0 regardless of timestamps (e.g. check-out out of range)'
    )
    duration_minutes = fields.Float(
        string='Time Spent (min)', compute='_compute_duration', store=True, readonly=True
    )
    duration_hours = fields.Float(
        string='Time Spent (hours)', compute='_compute_duration', store=True, readonly=True
    )
    latitude = fields.Float(string='Latitude', digits=(10, 7), readonly=True)
    longitude = fields.Float(string='Longitude', digits=(10, 7), readonly=True)
    check_out_latitude = fields.Float(string='Check-out Latitude', digits=(10, 7), readonly=True)
    check_out_longitude = fields.Float(string='Check-out Longitude', digits=(10, 7), readonly=True)
    check_out_location_address = fields.Char(string='Check-out Address', readonly=True)
    device_info = fields.Char(string='Device Info', readonly=True)
    location_address = fields.Char(
        string='Check-in Address', readonly=True,
        help='Address of check-in location'
    )
    notes = fields.Text(string='Visit Notes', help='Additional notes about this field visit')
    maps_url = fields.Char(
        string='Map Link', compute='_compute_maps_url', store=False
    )
    check_out_maps_url = fields.Char(
        string='Check-out Map Link', compute='_compute_check_out_maps_url', store=False
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('done', 'Checked In'),
        ('checked_out', 'Checked Out'),
        ('cancellation_requested', 'Cancellation Requested'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', readonly=True)

    pre_cancellation_state = fields.Selection([
        ('draft', 'Draft'),
        ('done', 'Checked In'),
        ('checked_out', 'Checked Out'),
    ], string='State Before Cancellation', readonly=True)

    cancellation_reason = fields.Text(
        string='Cancellation Reason',
        help='Reason given by the team member for requesting cancellation'
    )
    cancellation_request_date = fields.Datetime(
        string='Cancellation Requested On', readonly=True
    )
    cancelled_by_id = fields.Many2one(
        'res.users', string='Cancelled By', readonly=True,
        help='Project manager who approved the cancellation'
    )
    rejection_reason = fields.Text(
        string='Rejection Reason',
        help='Reason given by the manager when rejecting the cancellation request'
    )

    def init(self):
        # Enforce at DB level: a user can have only one active check-in at a time.
        try:
            self._cr.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS visit_tracker_one_active_per_user
                ON visit_tracker (user_id)
                WHERE state = 'done'
            """)
        except Exception:
            _logger.exception(
                "Could not create unique index visit_tracker_one_active_per_user. "
                "There may be duplicate active check-ins (state='done') per user."
            )

    @api.depends('plan_id', 'plan_line_id', 'plan_id.planned_hours', 'plan_line_id.planned_hours')
    def _compute_planned_metrics(self):
        for record in self:
            if record.plan_line_id:
                record.planned_hours = record.plan_line_id.planned_hours
                record.planned_duration_minutes = record.plan_line_id.planned_hours * 60.0
            elif record.plan_id:
                record.planned_hours = record.plan_id.planned_hours
                record.planned_duration_minutes = (record.plan_id.planned_hours or 0.0) * 60.0
            else:
                record.planned_hours = 0.0
                record.planned_duration_minutes = 0.0

    @api.depends('plan_id', 'plan_line_id')
    def _compute_is_planned(self):
        for record in self:
            record.is_planned = bool(record.plan_id or record.plan_line_id)

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
                        duration_minutes = round(seconds / 60.0, 2)
                        duration_hours = round(seconds / 3600.0, 2)
            record.duration_minutes = duration_minutes
            record.duration_hours = duration_hours

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
                    _('You already have an active check-in. Please check out before checking in to another project.')
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
        """Method called by JS to save check-in location."""
        for record in self:
            if record.user_id and record.user_id != self.env.user and not self.env.user.has_group('project.group_project_manager'):
                raise UserError(_('You can only check in your own visits.'))

            # Concurrency guard
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
                project_name = active_visit.project_id.display_name if active_visit.project_id else _('another project')
                visit_date = active_visit.visit_date or ''
                raise UserError(
                    _('You are already checked in to %(project)s since %(time)s. Please check out before starting a new visit.')
                    % {'project': project_name, 'time': visit_date}
                )

            # Auto-link approved plan for this user & project if not already linked
            vals = {
                'latitude': lat,
                'longitude': long,
                'device_info': device_info,
                'visit_date': fields.Datetime.now(),
                'check_out_date': False,
                'state': 'done'
            }

            if not record.plan_id and record.project_id:
                today = fields.Date.context_today(self)
                approved_plan = self.env['visit.plan'].search([
                    ('user_id', '=', record.user_id.id),
                    ('project_id', '=', record.project_id.id),
                    ('start_date', '<=', today),
                    ('end_date', '>=', today),
                    ('state', '=', 'approved'),
                ], limit=1)
                if approved_plan:
                    vals['plan_id'] = approved_plan.id

            if not address and lat and long:
                address = self._get_address_from_coordinates(lat, long)
            if address:
                vals['location_address'] = address

            try:
                record.write(vals)
            except IntegrityError:
                self.env.cr.rollback()
                raise UserError(_('You already have an active check-in. Please check out before checking in to another project.'))

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
            'project_name': active_visit.project_id.display_name if active_visit.project_id else False,
            'plan_id': active_visit.plan_id.id if active_visit.plan_id else False,
            'plan_name': active_visit.plan_id.name if active_visit.plan_id else False,
            'visit_date': active_visit.visit_date,
        }

    def action_check_out(self, latitude=False, longitude=False):
        for record in self:
            if record.state != 'done':
                raise UserError(_('Only active check-ins can be checked out.'))
            if record.user_id != self.env.user and not self.env.user.has_group('project.group_project_manager'):
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

            if latitude and longitude and record.latitude and record.longitude:
                distance = self._calculate_distance(
                    record.latitude, record.longitude,
                    latitude, longitude
                )
                if distance > 100:
                    vals['force_zero_duration'] = True
                    msg = _("Checked out more than 100m away (%.2fm). Time spent set to 0.") % distance
                    _logger.warning("visit.tracker %s: %s", record.id, msg)
                    vals['notes'] = (record.notes + "\n" + msg) if record.notes else msg

            record.write(vals)

    @staticmethod
    def _calculate_distance(lat1, lon1, lat2, lon2):
        """Haversine distance in meters between two GPS coordinates."""
        lon1, lat1, lon2, lat2 = map(math.radians, [lon1, lat1, lon2, lat2])
        dlon = lon2 - lon1
        dlat = lat2 - lat1
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        c = 2 * math.asin(math.sqrt(a))
        r = 6371000  # Radius of earth in meters
        return c * r

    @api.model
    def _get_address_from_coordinates(self, latitude, longitude):
        """Reverse geocoding via Nominatim (server-side to avoid CORS)."""
        try:
            url = (
                f'https://nominatim.openstreetmap.org/reverse'
                f'?format=json&lat={latitude}&lon={longitude}'
                f'&zoom=18&addressdetails=1'
            )
            headers = {'User-Agent': 'OdooFieldTracker/19.0 (contact@top-tech.com)'}
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return data.get('display_name', False)
            else:
                _logger.warning(f"Nominatim returned status {response.status_code}")
        except Exception as e:
            _logger.warning(f"Reverse geocoding failed: {e}")
        return False

    def action_request_cancellation(self):
        """Team member requests cancellation of their check-in."""
        for record in self:
            if record.state not in ('done', 'checked_out'):
                continue
            if record.user_id != self.env.user:
                raise UserError(
                    _('Only the team member who recorded this check-in can request its cancellation.')
                )
            record.write({
                'pre_cancellation_state': record.state,
                'state': 'cancellation_requested',
                'cancellation_request_date': fields.Datetime.now(),
            })

    def action_approve_cancellation(self):
        """Project manager approves the cancellation request."""
        if not self.env.user.has_group('project.group_project_manager'):
            raise UserError(_('Only project managers can approve cancellation requests.'))
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
        """Project manager rejects the cancellation request."""
        if not self.env.user.has_group('project.group_project_manager'):
            raise UserError(_('Only project managers can reject cancellation requests.'))
        for record in self:
            if record.state != 'cancellation_requested':
                continue
            record.write({
                'state': record.pre_cancellation_state or 'done',
                'cancelled_by_id': False,
                'cancellation_request_date': False,
                'pre_cancellation_state': False,
            })
