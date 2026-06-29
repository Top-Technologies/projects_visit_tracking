import logging
import re

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class VisitRoute(models.Model):
    _name = "visit.route"
    _description = "Field Visit Route Assignment"
    _order = "route_date desc, user_id"

    name = fields.Char(required=True, default=lambda self: self._default_name())
    user_id = fields.Many2one(
        "res.users", string="Team Member", required=True,
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

    _route_user_date_unique = models.Constraint(
        'unique(user_id, route_date)',
        'A team member can only have one route per day.'
    )

    @api.model
    def _default_name(self):
        return _("Route")

    @api.model
    def is_project_manager(self):
        return bool(self.env.user.has_group('project.group_project_manager'))

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
        is_manager = self.env.user.has_group('project.group_project_manager')
        for vals in vals_list:
            if not is_manager:
                vals['user_id'] = self.env.user.id
                vals['state'] = 'draft'
            elif vals.get('user_id') and vals['user_id'] != self.env.user.id:
                # Manager creating for someone else → Auto-approve
                vals['state'] = 'confirmed'
        return super().create(vals_list)

    def write(self, vals):
        is_manager = self.env.user.has_group('project.group_project_manager')

        if 'user_id' in vals and not is_manager:
            raise UserError(_('Only project managers can assign routes to other team members.'))

        for route in self:
            if not is_manager and route.state != 'draft':
                raise UserError(_('You cannot edit a route that is pending approval or already approved.'))
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
        if not self.env.user.has_group('project.group_project_manager'):
            raise UserError(_('Only project managers can approve routes.'))
        self.write({'state': 'confirmed'})

    def action_reset_draft(self):
        if not self.env.user.has_group('project.group_project_manager'):
            raise UserError(_('Only project managers can reset routes to draft.'))
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

        stops = []
        for idx, line in enumerate(lines, start=1):
            project = line.project_id

            latitude = line.latitude
            longitude = line.longitude

            stops.append({
                "sequence": idx,
                "route_line_id": line.id,
                "project_id": project.id,
                "project_name": project.display_name if project else '',
                "latitude": latitude,
                "longitude": longitude,
                "address": line.location_address or False,
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
    _description = "Field Visit Route Stop"
    _order = "sequence, id"

    route_id = fields.Many2one("visit.route", required=True, ondelete="cascade")
    sequence = fields.Integer(default=10)
    project_id = fields.Many2one("project.project", string="Project", required=True)
    location_address = fields.Char(
        string="Location / Address",
        help=(
            "Paste a Google Maps link for this stop - Latitude/Longitude "
            "below will be filled in automatically. You can also type a "
            "plain address/description instead; in that case set the "
            "coordinates manually."
        )
    )
    latitude = fields.Float(string="Latitude", digits=(10, 7))
    longitude = fields.Float(string="Longitude", digits=(10, 7))
    estimated_duration_minutes = fields.Float(
        string="Planned Duration (min)",
        default=30.0,
        help="Estimated time to spend at this stop (in minutes)"
    )

    _route_project_unique = models.Constraint(
        "unique(route_id, project_id)",
        "This project is already on the route."
    )

    # Shortened Google Maps links carry no coordinates of their own - the
    # actual link only appears after the browser follows the redirect.
    _MAPS_SHORT_HOSTS = ('maps.app.goo.gl', 'goo.gl', 'g.co')

    # Checked in order of accuracy. The "!3d..!4d.." pair is the exact pin
    # location Google embeds in /maps/place/.../data=... links - prefer it
    # over "@lat,lng", which is just the viewport center and can be off if
    # the map was panned/zoomed before the link was copied.
    _COORD_URL_PATTERNS = (
        r'!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)',
        r'[?&]q=(-?\d+\.\d+),\s*(-?\d+\.\d+)',
        r'[?&]ll=(-?\d+\.\d+),\s*(-?\d+\.\d+)',
        r'[?&]destination=(-?\d+\.\d+),\s*(-?\d+\.\d+)',
        r'[?&]daddr=(-?\d+\.\d+),\s*(-?\d+\.\d+)',
        r'@(-?\d+\.\d+),(-?\d+\.\d+)',
    )

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
        """Follow the redirect for shortened links (maps.app.goo.gl, goo.gl/maps,
        g.co/maps) to get the real URL that actually contains coordinates."""
        try:
            response = requests.get(
                url, allow_redirects=True, timeout=10,
                headers={'User-Agent': 'OdooFieldRoute/19.0 (contact@top-tech.com)'}
            )
            return response.url
        except Exception as e:
            _logger.warning("Could not resolve shortened Google Maps link %s: %s", url, e)
            return url

    @api.model
    def _extract_lat_lng_from_url(self, url):
        """Try to pull (lat, lng) floats out of a Google Maps link. Returns False if none found."""
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
                        "left unchanged - please double check the link or enter "
                        "the coordinates manually."
                    ),
                }
            }

    @api.model
    def _autofill_coordinates_from_vals(self, vals):
        """Server-side fallback for records created/updated outside the form
        view (API calls, imports, etc.), where the onchange above never runs."""
        url = vals.get('location_address')
        if not url or 'latitude' in vals or 'longitude' in vals:
            return
        if not self._looks_like_maps_link(url):
            return
        result = self._extract_lat_lng_from_url(url)
        if result:
            vals['latitude'], vals['longitude'] = result

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._autofill_coordinates_from_vals(vals)
        return super().create(vals_list)

    def write(self, vals):
        if 'location_address' in vals:
            self._autofill_coordinates_from_vals(vals)
        return super().write(vals)

    @api.constrains("latitude", "longitude")
    def _check_coordinates_required(self):
        for line in self:
            if not line.latitude and not line.longitude:
                # Allow 0,0 only if both are explicitly zero (unlikely for a real site)
                # but allow empty (not set) without error — address-only stops are valid
                continue
            if line.latitude < -90.0 or line.latitude > 90.0:
                raise ValidationError(_("Latitude must be between -90 and 90."))
            if line.longitude < -180.0 or line.longitude > 180.0:
                raise ValidationError(_("Longitude must be between -180 and 180."))