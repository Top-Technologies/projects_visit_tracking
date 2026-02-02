/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component } from "@odoo/owl";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";

// Service that runs geolocation + RPC outside any form component.
// Used so the browser's geolocation callback is not tied to a component that may be destroyed on mobile.
const visitCheckInService = {
    dependencies: ["orm", "notification"],
    start(env, { orm, notification }) {
        const options = { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 };
        return {
            startCheckIn(recordId, modelName) {
                navigator.geolocation.getCurrentPosition(
                    (position) => {
                        const { latitude, longitude } = position.coords;
                        const device_info = navigator.userAgent;
                        orm.call(modelName, "action_check_in", [[recordId], latitude, longitude, device_info, false])
                            .then(() => {
                                notification.add("Checked in successfully!", { type: "success" });
                            })
                            .catch((err) => {
                                notification.add("Error during check-in: " + err.message, { type: "danger" });
                            });
                    },
                    (error) => {
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
                        notification.add(msg, { type: "danger" });
                    },
                    options
                );
            },
        };
    },
};
registry.category("services").add("visit_check_in", visitCheckInService);

/**
 * Geolocation Button Widget for CRM Leads
 */
export class LeadGeolocationButton extends Component {
    static template = "sales_visit_tracking.LeadGeolocationButton";
    static props = {
        ...standardWidgetProps,
    };

    setup() {
        this.notification = useService("notification");
        this.visitCheckIn = useService("visit_check_in");
    }

    async onClickCheckIn() {
        if (!navigator.geolocation) {
            this.notification.add("Geolocation is not supported by your browser.", {
                type: "danger",
            });
            return;
        }

        this.notification.add("Getting your location...", { type: "info" });

        let leadId;
        try {
            const saved = await this.props.record.save();
            if (!saved) {
                this.notification.add("Failed to save the lead. Please check required fields.", {
                    type: "danger",
                });
                return;
            }
            leadId = this.props.record.resId;
        } catch (error) {
            this.notification.add("Error saving lead: " + error.message, { type: "danger" });
            return;
        }

        this.visitCheckIn.startCheckIn(leadId, "crm.lead");
    }
}

// Register the widget for CRM lead forms
registry.category("view_widgets").add("lead_geolocation_button", {
    component: LeadGeolocationButton,
});


/**
 * Visit Tracker Geolocation Button (for visit.tracker form view)
 */
export class VisitGeolocationButton extends Component {
    static template = "sales_visit_tracking.VisitGeolocationButton";
    static props = {
        ...standardWidgetProps,
    };

    setup() {
        this.notification = useService("notification");
        this.visitCheckIn = useService("visit_check_in");
    }

    async onClickCheckIn() {
        if (!navigator.geolocation) {
            this.notification.add("Geolocation is not supported by your browser.", {
                type: "danger",
            });
            return;
        }

        this.notification.add("Getting your location...", { type: "info" });

        let resId;
        try {
            const saved = await this.props.record.save();
            if (!saved) {
                this.notification.add("Failed to save the record. Please check required fields.", {
                    type: "danger",
                });
                return;
            }
            resId = this.props.record.resId;
        } catch (error) {
            this.notification.add("Error saving record: " + error.message, { type: "danger" });
            return;
        }

        this.visitCheckIn.startCheckIn(resId, "visit.tracker");
    }
}

registry.category("view_widgets").add("visit_geolocation_button", {
    component: VisitGeolocationButton,
});
