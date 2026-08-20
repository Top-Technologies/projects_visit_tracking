{
    'name': 'Projects Visit Tracking & Planning',
    'version': '19.0.1.0.0',
    'category': 'Project',
    'summary': 'Plan project site visits, mobile check-in/out with geolocation, and track planned vs actual hours',
    'description': """
        This module allows project-oriented visit planning and mobile check-in tracking.
        Features:
        - Project Site Visit Planning (Full-day 8h/day or Custom Hours)
        - Approval workflow for visit plans
        - Mobile-friendly GPS Check-in & Check-out directly from approved plans
        - Automatic duration calculation & Planned vs Actual hours analysis
        - Interactive map dashboard for live team activity
        - Pivot and graph analysis comparing planned vs actual hours
    """,
    'author': 'Top-tech',
    'depends': ['base', 'web', 'project'],
    'data': [
        'security/ir.model.access.csv',
        'security/security.xml',
        'security/visit_plan_security.xml',
        'views/visit_plan_views.xml',
        'views/visit_tracker_views.xml',
        'views/project_project_views.xml',
        'report/visit_report_views.xml',
        'views/visit_dashboard_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'projects_visit_tracking/static/src/css/visit_map.css',
            'projects_visit_tracking/static/src/js/geolocation_button.js',
            'projects_visit_tracking/static/src/js/visit_map.js',
            'projects_visit_tracking/static/src/xml/geolocation_button.xml',
            'projects_visit_tracking/static/src/xml/visit_map.xml',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
