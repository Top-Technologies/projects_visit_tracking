{
    'name': 'Sales Visit Tracking',
    'version': '18.0.1.0.0',
    'category': 'Sales',
    'summary': 'Track salesperson visits with geolocation',
    'description': """
        This module allows tracking of salesperson visits to partners.
        It uses geolocation to verify the visit location and enforces
        mobile device usage for check-ins.
    """,
    'author': 'Top-tech',
    'depends': ['base', 'web', 'sale', 'base_geolocalize', 'web_map'],
    'data': [
        'security/ir.model.access.csv',
        'views/visit_tracker_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'sales_visit_tracking/static/src/js/geolocation_button.js',
            'sales_visit_tracking/static/src/xml/geolocation_button.xml',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
