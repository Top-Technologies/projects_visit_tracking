from odoo import api, fields, models, tools


class VisitReport(models.Model):
    _name = 'visit.report'
    _description = 'Field Visit Analysis - Planned vs Actual'
    _auto = False
    _order = 'report_date desc, user_id'

    # Dimensions
    user_id = fields.Many2one('res.users', string='Team Member', readonly=True)
    report_date = fields.Date(string='Date', readonly=True)
    project_id = fields.Many2one('project.project', string='Project', readonly=True)

    # Planned metrics (from route)
    planned_visits = fields.Integer(string='Planned Visits', readonly=True)
    planned_duration = fields.Float(string='Planned Duration (min)', readonly=True)

    # Actual metrics (from visit.tracker)
    actual_visits = fields.Integer(string='Actual Check-ins', readonly=True)
    actual_duration = fields.Float(string='Actual Duration (min)', readonly=True)

    # Variance metrics
    visit_variance = fields.Integer(string='Visit Variance', readonly=True)
    duration_variance = fields.Float(string='Duration Variance (min)', readonly=True)
    visit_completion_rate = fields.Float(string='Completion Rate (%)', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                WITH field_users AS (
                    SELECT DISTINCT su.user_id
                    FROM (
                        SELECT user_id FROM visit_route
                        UNION
                        SELECT user_id FROM visit_tracker
                    ) AS su
                    INNER JOIN res_users ru ON ru.id = su.user_id
                    WHERE ru.active = TRUE
                    UNION SELECT NULL
                ),
                combined_raw AS (
                    -- PLANNED VISITS (from Routes)
                    SELECT
                        vr.user_id,
                        vr.route_date AS report_date,
                        vrl.project_id,
                        1 AS planned_visits,
                        COALESCE(vrl.estimated_duration_minutes, 0) AS planned_duration,
                        0 AS actual_visits,
                        0 AS actual_duration
                    FROM visit_route_line vrl
                    JOIN visit_route vr ON vr.id = vrl.route_id

                    UNION ALL

                    -- ACTUAL VISITS (from Tracker)
                    SELECT
                        vt.user_id,
                        DATE(vt.visit_date AT TIME ZONE 'UTC') AS report_date,
                        vt.project_id,
                        0 AS planned_visits,
                        0 AS planned_duration,
                        1 AS actual_visits,
                        COALESCE(vt.duration_minutes, 0) AS actual_duration
                    FROM visit_tracker vt
                    WHERE vt.state NOT IN ('draft', 'cancelled')
                ),
                all_dates AS (
                    SELECT DISTINCT report_date FROM combined_raw
                    UNION
                    SELECT CURRENT_DATE
                ),
                user_dates AS (
                    SELECT u.user_id, d.report_date
                    FROM field_users u
                    CROSS JOIN all_dates d
                ),
                grouped AS (
                    SELECT
                        cr.user_id,
                        cr.report_date,
                        NULL::integer AS project_id,
                        SUM(cr.planned_visits) AS planned_visits,
                        SUM(cr.planned_duration) AS planned_duration,
                        SUM(cr.actual_visits) AS actual_visits,
                        SUM(cr.actual_duration) AS actual_duration,
                        SUM(cr.actual_visits) - SUM(cr.planned_visits) AS visit_variance,
                        SUM(cr.actual_duration) - SUM(cr.planned_duration) AS duration_variance,
                        CASE
                            WHEN SUM(cr.planned_visits) > 0
                            THEN ROUND((SUM(cr.actual_visits)::numeric / SUM(cr.planned_visits)::numeric) * 100, 2)
                            ELSE 0
                        END AS visit_completion_rate
                    FROM combined_raw cr
                    GROUP BY cr.user_id, cr.report_date
                ),
                existing_user_dates AS (
                    SELECT DISTINCT user_id, report_date FROM grouped
                ),
                missing_user_dates AS (
                    SELECT user_id, report_date FROM user_dates
                    EXCEPT
                    SELECT user_id, report_date FROM existing_user_dates
                ),
                dummy_rows AS (
                    SELECT
                        m.user_id,
                        m.report_date,
                        NULL::integer AS project_id,
                        0 AS planned_visits,
                        0::float AS planned_duration,
                        0 AS actual_visits,
                        0::float AS actual_duration,
                        0 AS visit_variance,
                        0::float AS duration_variance,
                        0 AS visit_completion_rate
                    FROM missing_user_dates m
                ),
                all_rows AS (
                    SELECT * FROM grouped
                    UNION ALL
                    SELECT * FROM dummy_rows
                )
                SELECT
                    ROW_NUMBER() OVER () AS id,
                    user_id,
                    report_date,
                    project_id,
                    planned_visits,
                    planned_duration,
                    actual_visits,
                    actual_duration,
                    visit_variance,
                    duration_variance,
                    visit_completion_rate
                FROM all_rows
            )
        """ % self._table)