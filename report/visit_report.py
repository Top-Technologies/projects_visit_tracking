from odoo import api, fields, models, tools


class VisitReport(models.Model):
    _name = 'visit.report'
    _description = 'Project Visit Analysis - Planned vs Actual'
    _auto = False
    _order = 'report_date desc, user_id'

    # Dimensions
    user_id = fields.Many2one('res.users', string='Employee / Team Member', readonly=True)
    report_date = fields.Date(string='Date', readonly=True)
    project_id = fields.Many2one('project.project', string='Project', readonly=True)

    # Planned metrics (from visit.plan)
    planned_visits = fields.Integer(string='Planned Visits', readonly=True)
    planned_hours = fields.Float(string='Planned Hours', readonly=True)

    # Actual metrics (from visit.tracker)
    actual_visits = fields.Integer(string='Actual Check-ins', readonly=True)
    actual_hours = fields.Float(string='Actual Hours Spent', readonly=True)

    # Variance metrics
    visit_variance = fields.Integer(string='Visit Variance', readonly=True)
    duration_variance = fields.Float(string='Variance (Hours)', readonly=True)
    visit_completion_rate = fields.Float(string='Completion Rate (%)', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                WITH combined_raw AS (
                    -- PLANNED VISITS (from Visit Plan expanded per day)
                    SELECT
                        vp.user_id,
                        d::date AS report_date,
                        vp.project_id,
                        1 AS planned_visits,
                        CASE 
                            WHEN (vp.end_date - vp.start_date + 1) > 0 
                            THEN (COALESCE(vp.planned_hours, 0) / (vp.end_date - vp.start_date + 1)::float)
                            ELSE COALESCE(vp.planned_hours, 0)
                        END AS planned_hours,
                        0 AS actual_visits,
                        0::float AS actual_hours
                    FROM visit_plan vp
                    CROSS JOIN LATERAL generate_series(vp.start_date, vp.end_date, '1 day'::interval) AS d
                    WHERE vp.state = 'approved'

                    UNION ALL

                    -- ACTUAL VISITS (from Visit Tracker)
                    SELECT
                        vt.user_id,
                        DATE(vt.visit_date AT TIME ZONE 'UTC') AS report_date,
                        vt.project_id,
                        0 AS planned_visits,
                        0::float AS planned_hours,
                        1 AS actual_visits,
                        COALESCE(vt.duration_hours, 0)::float AS actual_hours
                    FROM visit_tracker vt
                    WHERE vt.state NOT IN ('draft', 'cancelled')
                ),
                grouped AS (
                    SELECT
                        cr.user_id,
                        cr.report_date,
                        cr.project_id,
                        SUM(cr.planned_visits)::integer AS planned_visits,
                        ROUND(SUM(cr.planned_hours)::numeric, 2)::float AS planned_hours,
                        SUM(cr.actual_visits)::integer AS actual_visits,
                        ROUND(SUM(cr.actual_hours)::numeric, 2)::float AS actual_hours,
                        (SUM(cr.actual_visits) - SUM(cr.planned_visits))::integer AS visit_variance,
                        ROUND((SUM(cr.actual_hours) - SUM(cr.planned_hours))::numeric, 2)::float AS duration_variance,
                        CASE
                            WHEN SUM(cr.planned_hours) > 0
                            THEN ROUND(((SUM(cr.actual_hours)::numeric / SUM(cr.planned_hours)::numeric) * 100)::numeric, 2)::float
                            WHEN SUM(cr.planned_visits) > 0
                            THEN ROUND(((SUM(cr.actual_visits)::numeric / SUM(cr.planned_visits)::numeric) * 100)::numeric, 2)::float
                            ELSE 0::float
                        END AS visit_completion_rate
                    FROM combined_raw cr
                    GROUP BY cr.user_id, cr.report_date, cr.project_id
                )
                SELECT
                    ROW_NUMBER() OVER () AS id,
                    user_id,
                    report_date,
                    project_id,
                    planned_visits,
                    planned_hours,
                    actual_visits,
                    actual_hours,
                    visit_variance,
                    duration_variance,
                    visit_completion_rate
                FROM grouped
            )
        """ % self._table)