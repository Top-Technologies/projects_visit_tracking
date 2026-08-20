import logging
import re
import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class VisitPlan(models.Model):
    _name = "visit.plan"
    _description = "Project Visit Plan"
    _order = "start_date desc, user_id"

    name = fields.Char(
        string="Plan Reference",
        required=True,
        default=lambda self: self._default_name(),
        tracking=True
    )
    user_id = fields.Many2one(
        "res.users",
        string="Employee / Team Member",
        required=True,
        default=lambda self: self.env.user,
        tracking=True
    )
    project_id = fields.Many2one(
        "project.project",
        string="Project",
        required=True,
        tracking=True,
        help="Project site to visit"
    )
    start_date = fields.Date(
        string="Start Date",
        required=True,
        default=fields.Date.context_today,
        tracking=True
    )
    end_date = fields.Date(
        string="End Date",
        required=True,
        default=fields.Date.context_today,
        tracking=True
    )
    planning_type = fields.Selection([
        ('full_day', 'Full Day(s) (8h/day)'),
        ('custom_hours', 'Custom Hours'),
    ], string="Duration Mode", default='full_day', required=True, tracking=True)

    custom_hours = fields.Float(
        string="Input Hours",
        default=8.0,
        help="Specific hours to plan for this site visit"
    )
    planned_hours = fields.Float(
        string="Planned Hours",
        compute="_compute_planned_hours",
        store=True,
        readonly=False,
        tracking=True,
        help="Total planned hours for this site visit"
    )
    planned_duration_minutes = fields.Float(
        string="Planned Duration (min)",
        compute="_compute_planned_duration_minutes",
        store=True
    )

    location_address = fields.Char(
        string="Site Location / Address",
        help=(
            "Paste a Google Maps link for this site - Latitude/Longitude "
            "below will be filled in automatically. You can also type a "
            "plain address/description instead."
        )
    )
    latitude = fields.Float(string="Latitude", digits=(10, 7))
    longitude = fields.Float(string="Longitude", digits=(10, 7))
    notes = fields.Text(string="Objectives / Notes")

    state = fields.Selection([
        ('draft', 'Draft'),
        ('wait_approval', 'Approval Requested'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], string="Status", default='draft', required=True, tracking=True)

    approved_by_id = fields.Many2one(
        "res.users",
        string="Approved By",
        readonly=True,
        tracking=True
    )
    approval_date = fields.Datetime(
        string="Approval Date",
        readonly=True
    )
    rejection_reason = fields.Text(
        string="Rejection Reason",
        readonly=True
    )

    line_ids = fields.One2many(
        "visit.plan.line",
        "plan_id",
        string="Sub-Sites / Stops"
    )
    stop_count = fields.Integer(
        string="Stops Count",
        compute="_compute_stop_count"
    )

    visit_tracker_ids = fields.One2many(
        "visit.tracker",
        "plan_id",
        string="Check-ins"
    )
    check_in_count = fields.Integer(
        string="Check-ins Count",
        compute="_compute_tracking_metrics"
    )
    actual_hours = fields.Float(
        string="Actual Hours Spent",
        compute="_compute_tracking_metrics",
        store=True
    )
    actual_duration_minutes = fields.Float(
        string="Actual Time (min)",
        compute="_compute_tracking_metrics",
        store=True
    )
    variance_hours = fields.Float(
        string="Variance (Hours)",
        compute="_compute_tracking_metrics",
        store=True,
        help="Actual Hours minus Planned Hours"
    )
    completion_rate = fields.Float(
        string="Completion Rate (%)",
        compute="_compute_tracking_metrics",
        store=True
    )

    has_active_check_in = fields.Boolean(
        string="Has Active Check-in",
        compute="_compute_active_check_in"
    )
    active_visit_id = fields.Many2one(
        "visit.tracker",
        compute="_compute_active_check_in"
    )

    _MAPS_SHORT_HOSTS = ('maps.app.goo.gl', 'goo.gl', 'g.co')
    _COORD_URL_PATTERNS = (
        r'!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)',
        r'[?&]q=(-?\d+\.\d+),\s*(-?\d+\.\d+)',
        r'[?&]ll=(-?\d+\.\d+),\s*(-?\d+\.\d+)',
        r'[?&]destination=(-?\d+\.\d+),\s*(-?\d+\.\d+)',
        r'[?&]daddr=(-?\d+\.\d+),\s*(-?\d+\.\d+)',
        r'@(-?\d+\.\d+),(-?\d+\.\d+)',
    )

    @api.model
    def _default_name(self):
        today_str = fields.Date.context_today(self).strftime('%Y-%m-%d')
        return _("Plan - %s") % today_str

    @api.constrains("start_date", "end_date")
    def _check_dates(self):
        for record in self:
            if record.start_date and record.end_date and record.end_date < record.start_date:
                raise ValidationError(_("End Date cannot be earlier than Start Date."))

    @api.depends("planning_type", "start_date", "end_date", "custom_hours")
    def _compute_planned_hours(self):
        for record in self:
            if record.planning_type == 'full_day':
                if record.start_date and record.end_date:
                    days = (record.end_date - record.start_date).days + 1
                    days = max(days, 1)
                    record.planned_hours = float(days) * 8.0
                else:
                    record.planned_hours = 8.0
            else:
                record.planned_hours = record.custom_hours if record.custom_hours else 0.0

    @api.depends("planned_hours")
    def _compute_planned_duration_minutes(self):
        for record in self:
            record.planned_duration_minutes = (record.planned_hours or 0.0) * 60.0

    @api.depends("line_ids")
    def _compute_stop_count(self):
        for record in self:
            record.stop_count = len(record.line_ids)

    @api.depends(
        "visit_tracker_ids.duration_hours",
        "visit_tracker_ids.duration_minutes",
        "visit_tracker_ids.state",
        "planned_hours"
    )
    def _compute_tracking_metrics(self):
        for record in self:
            valid_visits = record.visit_tracker_ids.filtered(
                lambda v: v.state in ('done', 'checked_out')
            )
            actual_hours = sum(valid_visits.mapped("duration_hours"))
            actual_minutes = sum(valid_visits.mapped("duration_minutes"))
            record.check_in_count = len(valid_visits)
            record.actual_hours = round(actual_hours, 2)
            record.actual_duration_minutes = round(actual_minutes, 2)
            record.variance_hours = round(actual_hours - (record.planned_hours or 0.0), 2)
            if record.planned_hours and record.planned_hours > 0:
                record.completion_rate = min(
                    round((actual_hours / record.planned_hours) * 100.0, 1), 100.0
                )
            else:
                record.completion_rate = 100.0 if actual_hours > 0 else 0.0

    @api.depends("visit_tracker_ids.state", "visit_tracker_ids.user_id")
    def _compute_active_check_in(self):
        for record in self:
            active_visit = record.visit_tracker_ids.filtered(
                lambda v: v.state == 'done' and v.user_id == self.env.user
            )
            active_visit = active_visit[:1]
            record.active_visit_id = active_visit.id if active_visit else False
            record.has_active_check_in = bool(active_visit)

    @api.model_create_multi
    def create(self, vals_list):
        is_manager = self.env.user.has_group('project.group_project_manager')
        for vals in vals_list:
            if not is_manager:
                vals['user_id'] = self.env.user.id
                vals['state'] = 'draft'
            elif vals.get('user_id') and vals['user_id'] != self.env.user.id:
                # Manager creating for team member auto-approves
                vals['state'] = 'approved'
                vals['approved_by_id'] = self.env.user.id
                vals['approval_date'] = fields.Datetime.now()
            self._autofill_coordinates_from_vals(vals)
        return super().create(vals_list)

    def write(self, vals):
        is_manager = self.env.user.has_group('project.group_project_manager')

        if 'user_id' in vals and not is_manager:
            raise UserError(_('Only project managers can assign visit plans to other team members.'))

        for plan in self:
            if not is_manager and plan.state not in ('draft', 'rejected'):
                # Allow editing only draft or rejected plans for non-managers
                if any(field not in ('location_address', 'latitude', 'longitude', 'notes') for field in vals):
                    raise UserError(_('You cannot edit a visit plan that is pending approval or approved.'))
            if not is_manager and plan.create_uid.id != self.env.user.id:
                raise UserError(_('You cannot edit a visit plan created by your manager.'))

        if 'location_address' in vals:
            self._autofill_coordinates_from_vals(vals)

        return super().write(vals)

    def action_request_approval(self):
        for plan in self:
            if plan.state != 'draft':
                continue
            if not plan.project_id:
                raise UserError(_('Please select a project before requesting approval.'))
            plan.state = 'wait_approval'

    def action_approve(self):
        if not self.env.user.has_group('project.group_project_manager'):
            raise UserError(_('Only project managers can approve visit plans.'))
        self.write({
            'state': 'approved',
            'approved_by_id': self.env.user.id,
            'approval_date': fields.Datetime.now(),
            'rejection_reason': False,
        })

    def action_reject(self):
        if not self.env.user.has_group('project.group_project_manager'):
            raise UserError(_('Only project managers can reject visit plans.'))
        self.write({
            'state': 'rejected',
            'approved_by_id': False,
            'approval_date': False,
        })

    def action_reset_draft(self):
        is_manager = self.env.user.has_group('project.group_project_manager')
        for plan in self:
            if not is_manager and plan.user_id != self.env.user:
                raise UserError(_('You can only reset your own visit plan to draft.'))
            plan.write({'state': 'draft'})

    def action_view_check_ins(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Check-ins: %s') % self.name,
            'res_model': 'visit.tracker',
            'view_mode': 'list,form',
            'domain': [('plan_id', '=', self.id)],
            'context': {
                'default_plan_id': self.id,
                'default_project_id': self.project_id.id,
            },
        }

    def action_check_in(self, lat, long, device_info, address=False):
        """Called from UI/mobile widget to check in to this approved plan."""
        self.ensure_one()
        if self.state != 'approved':
            raise UserError(_('You can only check in to an approved visit plan.'))
        if self.user_id != self.env.user and not self.env.user.has_group('project.group_project_manager'):
            raise UserError(_('You can only check in to your own visit plan.'))

        # Concurrency guard
        self.env.cr.execute(
            "SELECT id FROM res_users WHERE id = %s FOR UPDATE",
            (self.env.user.id,),
        )

        active_visit = self.env['visit.tracker'].search([
            ('user_id', '=', self.env.user.id),
            ('state', '=', 'done'),
        ], limit=1)
        if active_visit:
            project_name = active_visit.project_id.display_name if active_visit.project_id else _('another project')
            visit_date = active_visit.visit_date or ''
            raise UserError(
                _('You are already checked in to %(project)s since %(time)s. Please check out before starting a new visit.')
                % {'project': project_name, 'time': visit_date}
            )

        visit = self.env['visit.tracker'].create({
            'project_id': self.project_id.id,
            'plan_id': self.id,
            'user_id': self.env.user.id,
            'latitude': lat,
            'longitude': long,
            'device_info': device_info,
            'state': 'draft',
        })
        visit.action_check_in(lat, long, device_info, address)
        return visit.id

    def action_check_out(self, latitude=False, longitude=False):
        """Called from UI/mobile widget to check out from the active visit on this plan."""
        self.ensure_one()
        active_visit = self.env['visit.tracker'].search([
            ('plan_id', '=', self.id),
            ('user_id', '=', self.env.user.id),
            ('state', '=', 'done'),
        ], order='visit_date desc', limit=1)
        if not active_visit:
            raise UserError(_('You have no active check-in on this visit plan.'))
        active_visit.action_check_out(latitude=latitude, longitude=longitude)
        return True

    @api.model
    def is_project_manager(self):
        return bool(self.env.user.has_group('project.group_project_manager'))

    @api.model
    def get_current_user(self, *args, **kwargs):
        return {
            'id': self.env.user.id,
            'name': self.env.user.name,
        }

    @api.model
    def get_plan_map_data(self, user_id=False, plan_date=False):
        if not user_id:
            user_id = self.env.user.id
        if not plan_date:
            plan_date = fields.Date.context_today(self)

        plan = self.search([
            ("user_id", "=", int(user_id)),
            ("start_date", "<=", plan_date),
            ("end_date", ">=", plan_date),
            ("state", "=", "approved"),
        ], limit=1)

        if not plan:
            return {"plan": False, "stops": []}

        stops = []
        if plan.latitude or plan.longitude:
            stops.append({
                "sequence": 1,
                "project_id": plan.project_id.id,
                "project_name": plan.project_id.display_name if plan.project_id else '',
                "latitude": plan.latitude,
                "longitude": plan.longitude,
                "address": plan.location_address or False,
            })

        for idx, line in enumerate(plan.line_ids.sorted(key=lambda l: (l.sequence, l.id)), start=len(stops) + 1):
            stops.append({
                "sequence": idx,
                "project_id": line.project_id.id,
                "project_name": line.project_id.display_name if line.project_id else '',
                "latitude": line.latitude,
                "longitude": line.longitude,
                "address": line.location_address or False,
            })

        return {
            "plan": {
                "id": plan.id,
                "name": plan.name,
            },
            "stops": stops,
        }

    @staticmethod
    def _looks_like_maps_link(value):
        if not value:
            return False
        value = value.strip().lower()
        return (
            value.startswith('http://') or value.startswith('https://')
            or 'google.com/maps' in value or 'goo.gl' in value or 'g.co/maps' in value
        )

    @api.model
    def _resolve_short_maps_url(self, url):
        try:
            response = requests.get(
                url, allow_redirects=True, timeout=10,
                headers={'User-Agent': 'OdooVisitPlan/19.0 (contact@top-tech.com)'}
            )
            return response.url
        except Exception as e:
            _logger.warning("Could not resolve shortened Google Maps link %s: %s", url, e)
            return url

    @api.model
    def _extract_lat_lng_from_url(self, url):
        if not url:
            return False
        url = url.strip()
        if not url.lower().startswith(('http://', 'https://')):
            url = 'https://' + url

        if any(host in url for host in self._MAPS_SHORT_HOSTS):
            url = self._resolve_short_maps_url(url)

        for pattern in self._COORD_URL_PATTERNS:
            match = re.search(pattern, url)
            if not match:
                continue
            try:
                lat, lng = float(match.group(1)), float(match.group(2))
            except (TypeError, ValueError):
                continue
            if -90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0:
                return lat, lng
        return False

    @api.onchange('location_address')
    def _onchange_location_address(self):
        value = (self.location_address or '').strip()
        if not value or not self._looks_like_maps_link(value):
            return
        result = self._extract_lat_lng_from_url(value)
        if result:
            self.latitude, self.longitude = result
        else:
            return {
                'warning': {
                    'title': _('Could not read coordinates from link'),
                    'message': _(
                        "This looks like a Google Maps link but no recognizable "
                        "pin location was found in it. Latitude/Longitude were "
                        "left unchanged."
                    ),
                }
            }

    @api.model
    def _autofill_coordinates_from_vals(self, vals):
        url = vals.get('location_address')
        if not url or 'latitude' in vals or 'longitude' in vals:
            return
        if not self._looks_like_maps_link(url):
            return
        result = self._extract_lat_lng_from_url(url)
        if result:
            vals['latitude'], vals['longitude'] = result


class VisitPlanLine(models.Model):
    _name = "visit.plan.line"
    _description = "Project Visit Plan Sub-Site"
    _order = "sequence, id"

    plan_id = fields.Many2one("visit.plan", required=True, ondelete="cascade")
    sequence = fields.Integer(default=10)
    project_id = fields.Many2one("project.project", string="Project", required=True)
    location_address = fields.Char(string="Location / Address")
    latitude = fields.Float(string="Latitude", digits=(10, 7))
    longitude = fields.Float(string="Longitude", digits=(10, 7))
    planned_hours = fields.Float(string="Planned Hours", default=1.0)
    notes = fields.Char(string="Notes / Purpose")

    @api.onchange('location_address')
    def _onchange_location_address(self):
        value = (self.location_address or '').strip()
        if not value or not self.env['visit.plan']._looks_like_maps_link(value):
            return
        result = self.env['visit.plan']._extract_lat_lng_from_url(value)
        if result:
            self.latitude, self.longitude = result

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('location_address') and 'latitude' not in vals:
                result = self.env['visit.plan']._extract_lat_lng_from_url(vals['location_address'])
                if result:
                    vals['latitude'], vals['longitude'] = result
        return super().create(vals_list)
