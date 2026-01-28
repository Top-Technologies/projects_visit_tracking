/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component } from "@odoo/owl";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";

/**
 * Geolocation Button Widget for CRM Leads
 * This widget captures the user's location and creates a visit record
 * linked to the current lead/opportunity.
 */
export class LeadGeolocationButton extends Component {
    static template = "sales_visit_tracking.LeadGeolocationButton";
    static props = {
        ...standardWidgetProps,
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.action = useService("action");
    }

    async onClickCheckIn() {
        // if (!this.isMobileDevice()) {
        //     this.notification.add("Please use a mobile device to check in.", {
        //         type: "danger",
        //     });
        //     return;
        // }

        if (!navigator.geolocation) {
            this.notification.add("Geolocation is not supported by your browser.", {
                type: "danger",
            });
            return;
        }

        this.notification.add("Getting your location...", {
            type: "info",
        });

        navigator.geolocation.getCurrentPosition(
            (position) => this.onPositionSuccess(position),
            (error) => this.onPositionError(error),
            { enableHighAccuracy: true }
        );
    }

    isMobileDevice() {
        const ua = navigator.userAgent;
        return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(ua);
    }

    async onPositionSuccess(position) {
        const { latitude, longitude } = position.coords;
        const device_info = navigator.userAgent;

        // Try to get address via reverse geocoding (Nominatim/OpenStreetMap)
        let address = false;
        try {
            const response = await fetch(
                `https://nominatim.openstreetmap.org/reverse?format=json&lat=${latitude}&lon=${longitude}&zoom=18&addressdetails=1`,
                { headers: { 'User-Agent': 'OdooVisitTracker/1.0' } }
            );
            if (response.ok) {
                const data = await response.json();
                address = data.display_name || false;
            }
        } catch (e) {
            console.warn('Reverse geocoding failed:', e);
        }

        // Save the lead record first if it's new or unsaved
        try {
            const saved = await this.props.record.save();
            if (!saved) {
                this.notification.add("Failed to save the lead. Please check required fields.", {
                    type: "danger",
                });
                return;
            }
        } catch (error) {
            this.notification.add("Error saving lead: " + error.message, {
                type: "danger",
            });
            return;
        }

        // Call the check-in method on crm.lead to create a visit record
        try {
            await this.orm.call(
                "crm.lead",
                "action_check_in",
                [[this.props.record.resId], latitude, longitude, device_info, address]
            );

            this.notification.add("Checked in successfully!", {
                type: "success",
            });

            // Reload the view to show updated data
            await this.props.record.load();
        } catch (error) {
            this.notification.add("Error during check-in: " + error.message, {
                type: "danger",
            });
        }
    }

    onPositionError(error) {
        let msg = "Error getting location.";
        switch (error.code) {
            case error.PERMISSION_DENIED:
                msg = "User denied the request for Geolocation.";
                break;
            case error.POSITION_UNAVAILABLE:
                msg = "Location information is unavailable.";
                break;
            case error.TIMEOUT:
                msg = "The request to get user location timed out.";
                break;
            case error.UNKNOWN_ERROR:
                msg = "An unknown error occurred.";
                break;
        }
        this.notification.add(msg, {
            type: "danger",
        });
    }
}

// Register the widget for CRM lead forms
registry.category("view_widgets").add("lead_geolocation_button", {
    component: LeadGeolocationButton,
});


/**
 * Original Visit Tracker Geolocation Button (for visit.tracker form view)
 * Kept for backward compatibility if visit tracker form is still used directly
 */
export class VisitGeolocationButton extends Component {
    static template = "sales_visit_tracking.VisitGeolocationButton";
    static props = {
        ...standardWidgetProps,
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.action = useService("action");
    }

    async onClickCheckIn() {
        if (!navigator.geolocation) {
            this.notification.add("Geolocation is not supported by your browser.", {
                type: "danger",
            });
            return;
        }

        navigator.geolocation.getCurrentPosition(
            (position) => this.onPositionSuccess(position),
            (error) => this.onPositionError(error),
            { enableHighAccuracy: true }
        );
    }

    isMobileDevice() {
        const ua = navigator.userAgent;
        return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(ua);
    }

    async onPositionSuccess(position) {
        const { latitude, longitude } = position.coords;
        const device_info = navigator.userAgent;

        let address = false;
        try {
            const response = await fetch(
                `https://nominatim.openstreetmap.org/reverse?format=json&lat=${latitude}&lon=${longitude}&zoom=18&addressdetails=1`,
                { headers: { 'User-Agent': 'OdooVisitTracker/1.0' } }
            );
            if (response.ok) {
                const data = await response.json();
                address = data.display_name || false;
            }
        } catch (e) {
            console.warn('Reverse geocoding failed:', e);
        }

        try {
            const saved = await this.props.record.save();
            if (!saved) {
                this.notification.add("Failed to save the record. Please check required fields.", {
                    type: "danger",
                });
                return;
            }
        } catch (error) {
            this.notification.add("Error saving record: " + error.message, {
                type: "danger",
            });
            return;
        }

        try {
            await this.orm.call(
                "visit.tracker",
                "action_check_in",
                [[this.props.record.resId], latitude, longitude, device_info, address]
            );

            this.notification.add("Checked in successfully!", {
                type: "success",
            });

            await this.props.record.load();
        } catch (error) {
            this.notification.add("Error during check-in: " + error.message, {
                type: "danger",
            });
        }
    }

    onPositionError(error) {
        let msg = "Error getting location.";
        switch (error.code) {
            case error.PERMISSION_DENIED:
                msg = "User denied the request for Geolocation.";
                break;
            case error.POSITION_UNAVAILABLE:
                msg = "Location information is unavailable.";
                break;
            case error.TIMEOUT:
                msg = "The request to get user location timed out.";
                break;
            case error.UNKNOWN_ERROR:
                msg = "An unknown error occurred.";
                break;
        }
        this.notification.add(msg, {
            type: "danger",
        });
    }
}

registry.category("view_widgets").add("visit_geolocation_button", {
    component: VisitGeolocationButton,
});