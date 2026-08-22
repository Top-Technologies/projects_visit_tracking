/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, useState } from "@odoo/owl";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";

// Service that runs geolocation + RPC outside any form component.
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
            const name = info?.plan_name || info?.project_name || "another project";
            const since = info?.visit_date ? String(info.visit_date) : "";
            return since
                ? `You already have an active check-in at ${name} since ${since}.`
                : `You already have an active check-in at ${name}.`;
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
            async startCheckIn(recordId, modelName, actionType = 'check_in') {
                const method = actionType === 'check_out' ? 'action_check_out' : 'action_check_in';
                const successMsg = actionType === 'check_out' ? "Checked out successfully!" : "Checked in successfully!";

                if (actionType === 'check_in') {
                    // Check existing check-ins only for check-in action
                    try {
                        const info = await orm.call("visit.tracker", "get_active_check_in_info", []);
                        if (info?.active) {
                            const msg = buildActiveVisitMessage(info);
                            notification.add(msg + " Opening your active visit...", {
                                type: "warning",
                                sticky: true,
                            });
                            openVisitForm(info.id);
                            return false;
                        }
                    } catch (err) {
                        notification.add("Error checking active visits: " + formatRpcError(err), { type: "danger" });
                        return false;
                    }
                }

                // Proceed to geolocation call
                return this._performGeoCall(recordId, modelName, method, successMsg, options, notification, orm);
            },

            _performGeoCall(recordId, modelName, method, successMsg, options, notification, orm) {
                return new Promise((resolve) => {
                    navigator.geolocation.getCurrentPosition(
                        async (position) => {
                            try {
                                const { latitude, longitude } = position.coords;
                                const device_info = navigator.userAgent;
                                // For record methods: [[recordId], ...methodArgs]
                                const args = [[recordId], latitude, longitude];
                                if (method === 'action_check_in') {
                                    args.push(device_info, false);
                                }

                                const result = await orm.call(modelName, method, args);
                                notification.add(successMsg, { type: "success" });
                                resolve(result !== undefined ? result : true);
                            } catch (err) {
                                notification.add("Error: " + formatRpcError(err), { type: "danger" });
                                resolve(false);
                            }
                        },
                        (error) => {
                            let msg = "Error getting location.";
                            switch (error.code) {
                                case error.PERMISSION_DENIED:
                                    msg = "Location permission was denied. Please allow location access in your browser settings.";
                                    break;
                                case error.POSITION_UNAVAILABLE:
                                    msg = "Location information is unavailable. Please check your device location settings.";
                                    break;
                                case error.TIMEOUT:
                                    msg = "Location request timed out. Please try again.";
                                    break;
                                case error.UNKNOWN_ERROR:
                                    msg = "An unknown error occurred while retrieving location.";
                                    break;
                            }
                            notification.add(msg, { type: "danger" });
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

/**
 * Geolocation Button Widget for Visit Plan Form
 */
export class PlanGeolocationButton extends Component {
    static template = "projects_visit_tracking.PlanGeolocationButton";
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

        if (!navigator.geolocation) {
            this.notification.add("Geolocation is not supported by your browser.", {
                type: "danger",
            });
            return;
        }

        const planId = this.props.record.resId;
        if (!planId) {
            this.notification.add("Please save the visit plan first.", {
                type: "warning",
            });
            return;
        }

        const isCheckedIn = Boolean(this.props.record.data.has_active_check_in);
        const actionType = isCheckedIn ? "check_out" : "check_in";

        this.notification.add(
            isCheckedIn ? "Capturing check-out location..." : "Capturing check-in location...",
            { type: "info" }
        );

        this.state.processing = true;
        try {
            const res = await this.visitCheckIn.startCheckIn(planId, "visit.plan", actionType);
            if (res && this.props.record.load) {
                await this.props.record.load();
            }
        } finally {
            this.state.processing = false;
        }
    }
}

registry.category("view_widgets").add("plan_geolocation_button", {
    component: PlanGeolocationButton,
});

/**
 * Geolocation Button Widget for Project Forms
 */
export class ProjectGeolocationButton extends Component {
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

        if (!navigator.geolocation) {
            this.notification.add("Geolocation is not supported by your browser.", {
                type: "danger",
            });
            return;
        }

        this.notification.add("Getting your location...", { type: "info" });

        let projectId;
        try {
            this.state.processing = true;
            if (this.props.record.isDirty) {
                const saved = await this.props.record.save();
                if (!saved) {
                    this.notification.add("Failed to save the project. Please check required fields.", {
                        type: "danger",
                    });
                    return;
                }
            }
            projectId = this.props.record.resId;
        } catch (error) {
            this.notification.add("Error saving project: " + error.message, { type: "danger" });
            return;
        } finally {
            this.state.processing = false;
        }

        const actionType = this.props.record.data.has_active_visit ? "check_out" : "check_in";
        this.state.processing = true;
        try {
            const res = await this.visitCheckIn.startCheckIn(projectId, "project.project", actionType);
            if (res && this.props.record.load) {
                await this.props.record.load();
            }
        } finally {
            this.state.processing = false;
        }
    }
}

registry.category("view_widgets").add("project_geolocation_button", {
    component: ProjectGeolocationButton,
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

    async onClickCheckIn() {
        if (this.state.processing) {
            return;
        }

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
            if (this.props.record.isDirty) {
                const saved = await this.props.record.save();
                if (!saved) {
                    this.notification.add("Failed to save the record. Please check required fields.", {
                        type: "danger",
                    });
                    return;
                }
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
            const res = await this.visitCheckIn.startCheckIn(resId, "visit.tracker", actionType);
            if (res && this.props.record.load) {
                await this.props.record.load();
            }
        } finally {
            this.state.processing = false;
        }
    }
}

registry.category("view_widgets").add("visit_geolocation_button", {
    component: VisitGeolocationButton,
});
