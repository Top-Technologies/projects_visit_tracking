/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component } from "@odoo/owl";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";

// Service that runs geolocation + RPC outside any form component.
// Used so the browser's geolocation callback is not tied to a component that may be destroyed on mobile.
const visitCheckInService = {
    dependencies: ["orm", "notification", "action"],
    start(env, { orm, notification, action }) {
        const options = { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 };

        function formatRpcError(err) {
            return (
                err?.data?.message ||
                err?.message ||
                "Unknown error"
            );
        }

        function buildActiveVisitMessage(info) {
            const leadName = info?.lead_name || "";
            const partnerName = info?.partner_name || "";
            let place = leadName || partnerName || "another lead";
            if (leadName && partnerName && partnerName !== leadName) {
                place = `${leadName} (${partnerName})`;
            }
            const since = info?.visit_date ? String(info.visit_date) : "";
            return since
                ? `You already have an active check-in at ${place} since ${since}.`
                : `You already have an active check-in at ${place}.`;
        }

        function openVisitForm(visitId) {
            if (!visitId) return;
            action.doAction({
                type: "ir.actions.act_window",
                res_model: "visit.tracker",
                res_id: visitId,
                views: [[false, "form"]],
                target: "current",
            });
        }

        return {
            startCheckIn(recordId, modelName) {
                orm.call("visit.tracker", "get_active_check_in_info", [[]])
                    .then((info) => {
                        if (info?.active) {
                            const msg = buildActiveVisitMessage(info);
                            notification.add(msg + " Opening your active visit...", {
                                type: "warning",
                                sticky: true,
                            });
                            openVisitForm(info.id);
                            return;
                        }

                        navigator.geolocation.getCurrentPosition(
                            (position) => {
                                const { latitude, longitude } = position.coords;
                                const device_info = navigator.userAgent;
                                orm.call(modelName, "action_check_in", [[recordId], latitude, longitude, device_info, false])
                                    .then((result) => {
                                        notification.add("Checked in successfully!", { type: "success" });
                                        if (modelName === "crm.lead" && result) {
                                            openVisitForm(result);
                                        }
                                    })
                                    .catch((err) => {
                                        notification.add("Error during check-in: " + formatRpcError(err), { type: "danger" });
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
                    })
                    .catch(() => {
                        navigator.geolocation.getCurrentPosition(
                            (position) => {
                                const { latitude, longitude } = position.coords;
                                const device_info = navigator.userAgent;
                                orm.call(modelName, "action_check_in", [[recordId], latitude, longitude, device_info, false])
                                    .then((result) => {
                                        notification.add("Checked in successfully!", { type: "success" });
                                        if (modelName === "crm.lead" && result) {
                                            openVisitForm(result);
                                        }
                                    })
                                    .catch((err) => {
                                        notification.add("Error during check-in: " + formatRpcError(err), { type: "danger" });
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
                    });
            },
        };
    },
};
registry.category("services").add("visit_check_in", visitCheckInService);

// Helper to detect mobile devices via User Agent
function isMobileDevice() {
    const userAgent = navigator.userAgent || navigator.vendor || window.opera;
    const mobileRegex = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i;
    return mobileRegex.test(userAgent);
}

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
        if (!isMobileDevice()) {
            this.notification.add("Check-in is only allowed from mobile devices.", {
                type: "danger",
            });
            return;
        }

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
        if (!isMobileDevice()) {
            this.notification.add("Check-in is only allowed from mobile devices.", {
                type: "danger",
            });
            return;
        }

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
