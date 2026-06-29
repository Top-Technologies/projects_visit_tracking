{
    'name': 'Projects Visit Tracking',
    'version': '19.0.1.0.0',
    'category': 'Project',
    'summary': 'Track projects visits with geolocation',
    'description': """
        This module allows tracking of projects visits.
        Features:
        - Check-in button on Project form with geolocation capture
        - Interactive map dashboard with route visualization
        - Pivot and graph views for visit analysis
        - Filter by team member, date, and project
    """,
    'author': 'Top-tech',
    'depends': ['base', 'web', 'project'],
    'data': [
        'security/ir.model.access.csv',
        'security/security.xml',
        'security/visit_route_security.xml',
        'views/visit_tracker_views.xml',
        'views/project_project_views.xml',
        'report/visit_report_views.xml',
        'views/visit_dashboard_views.xml',
        'views/visit_route_views.xml',
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
