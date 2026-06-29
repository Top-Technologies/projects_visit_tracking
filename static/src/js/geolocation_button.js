/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component } from "@odoo/owl";
import { useState } from "@odoo/owl";
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
            startCheckIn(recordId, modelName, actionType = 'check_in') {
                const method = actionType === 'check_out' ? 'action_check_out' : 'action_check_in';
                const successMsg = actionType === 'check_out' ? "Checked out successfully!" : "Checked in successfully!";

                if (actionType === 'check_in') {
                    // Check existing check-ins only for check-in action
                    return orm.call("visit.tracker", "get_active_check_in_info", [])
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
                            // Proceed to geolocation
                            return this._performGeoCall(recordId, modelName, method, successMsg, options, notification, orm, action);
                        })
                        .catch((err) => {
                            notification.add("Error: " + formatRpcError(err), { type: "danger" });
                            // Do not reject: avoid UncaughtPromiseError in Owl for expected failures.
                            return false;
                        });
                } else {
                    // Direct check-out with geolocation
                    return this._performGeoCall(recordId, modelName, method, successMsg, options, notification, orm, action);
                }
            },

            _performGeoCall(recordId, modelName, method, successMsg, options, notification, orm, action) {
                return new Promise((resolve) => {
                    navigator.geolocation.getCurrentPosition(
                        (position) => {
                            const { latitude, longitude } = position.coords;
                            const device_info = navigator.userAgent;
                            // For record methods, Odoo expects the first positional argument to be the list of ids.
                            // So we must pass: [[recordId], ...methodArgs]
                            const args = [[recordId], latitude, longitude];
                            if (method === 'action_check_in') {
                                args.push(device_info, false);
                            }

                            orm.call(modelName, method, args)
                                .then((result) => {
                                    notification.add(successMsg, { type: "success" });
                                    if (modelName === "crm.lead" && method === "action_check_in" && Number.isInteger(result)) {
                                        openVisitForm(result);
                                    } else if (modelName === "visit.tracker") {
                                        // Reload view or close window if needed, or just let form reload
                                        action.switchView("form", { resId: recordId });
                                    } else {
                                        action.switchView("form", { resId: recordId });
                                    }
                                    resolve(result);
                                })
                                .catch((err) => {
                                    notification.add("Error: " + formatRpcError(err), { type: "danger" });
                                    // Do not reject: avoid UncaughtPromiseError in Owl for expected failures.
                                    resolve(false);
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
                            // Do not reject: avoid UncaughtPromiseError in Owl for expected failures.
                            resolve(false);
                        },
                        options
                    );
                });
            }
        };
    },
};
registry.category("services").add("visit_check_in", visitCheckInService);

    // // Helper to detect mobile devices via User Agent
    // // Disabled for testing on desktop — allows check-in from any device
    // function isMobileDevice() {
    //     const userAgent = navigator.userAgent || navigator.vendor || window.opera;
    //     const mobileRegex = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i;
    //     return mobileRegex.test(userAgent);
    // }

/**
 * Geolocation Button Widget for CRM Leads
 */
export class LeadGeolocationButton extends Component {
    static template = "projects_visit_tracking.ProjectGeolocationButton";
    static props = {
        ...standardWidgetProps,
    };

    setup() {
        this.notification = useService("notification");
        this.visitCheckIn = useService("visit_check_in");
        this.state = useState({ processing: false });
    }

    async onClickCheckIn() {
        if (this.state.processing) {
            return;
        }
        // // Disabled for testing on desktop — allows check-in from any device
        // if (!isMobileDevice()) {
        //     this.notification.add("Check-in is only allowed from mobile devices.", {
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

        this.notification.add("Getting your location...", { type: "info" });

        let leadId;
        try {
            this.state.processing = true;
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
        } finally {
            this.state.processing = false;
        }

        const actionType = this.props.record.data.has_active_visit ? "check_out" : "check_in";
        this.state.processing = true;
        try {
            await this.visitCheckIn.startCheckIn(leadId, "crm.lead", actionType);
        } finally {
            this.state.processing = false;
        }
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
    static template = "projects_visit_tracking.VisitGeolocationButton";
    static props = {
        ...standardWidgetProps,
    };

    setup() {
        this.notification = useService("notification");
        this.visitCheckIn = useService("visit_check_in");
        this.state = useState({ processing: false });
    }

    get buttonText() {
        if (this.props.record.data.state === 'done') {
            return "Check Out";
        }
        return "Check In";
    }

    get buttonClass() {
        if (this.props.record.data.state === 'done') {
            return "btn btn-primary";
        }
        return "btn btn-primary";
    }

    async onClickCheckIn() {
        if (this.state.processing) {
            return;
        }
        // // Disabled for testing on desktop — allows check-in from any device
        // if (!isMobileDevice()) {
        //     this.notification.add("Action is only allowed from mobile devices.", {
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

        const actionType = this.props.record.data.state === 'done' ? 'check_out' : 'check_in';
        this.notification.add("Getting your location...", { type: "info" });

        let resId;
        try {
            this.state.processing = true;
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
        } finally {
            this.state.processing = false;
        }

        this.state.processing = true;
        try {
            await this.visitCheckIn.startCheckIn(resId, "visit.tracker", actionType);
        } finally {
            this.state.processing = false;
        }
    }
}

registry.category("view_widgets").add("visit_geolocation_button", {
    component: VisitGeolocationButton,
});
