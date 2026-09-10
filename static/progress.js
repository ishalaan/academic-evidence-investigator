"use strict";

const form = document.getElementById("research-form");
const submitButton = document.getElementById("submit-button");
const loadingOverlay = document.getElementById("loading-overlay");
const progressStatus = document.getElementById("progress-status");
const progressError = document.getElementById("progress-error");
const activityList = document.getElementById("activity-list");
const activityEmpty = document.getElementById("activity-empty");
const activityIds = new Set();
const activeSteps = new Map();

function renderActivity(events) {
    const followLatest = activityList.scrollHeight - activityList.scrollTop - activityList.clientHeight < 60;
    for (const event of events) {
        if (activityIds.has(event.id)) continue;
        activityIds.add(event.id);
        const previous = activeSteps.get(event.component);
        if (previous && (event.action === "completed" || event.action === "failed")) {
            previous.row.className = "activity-step finished";
            previous.badge.textContent = event.action === "failed" ? "Stopped" : "Finished";
            activeSteps.delete(event.component);
        }
        const row = document.createElement("li");
        row.className = `activity-step ${event.action}`;
        const heading = document.createElement("div");
        heading.className = "activity-step-heading";
        const component = document.createElement("strong");
        component.textContent = event.component + (event.cycle ? ` · Cycle ${event.cycle}` : "");
        const badge = document.createElement("span");
        badge.className = "activity-badge";
        badge.textContent = {started: "In progress", completed: "Completed", failed: "Failed", provider_failed: "Source unavailable"}[event.action] || "Update";
        heading.append(component, badge);
        const message = document.createElement("p");
        message.textContent = event.message;
        const timestamp = document.createElement("time");
        timestamp.dateTime = event.timestamp;
        timestamp.textContent = new Date(event.timestamp).toLocaleTimeString("en-GB");
        row.append(heading, message, timestamp);
        activityList.append(row);
        if (event.action === "started") activeSteps.set(event.component, {row, badge});
    }
    activityEmpty.hidden = activityIds.size > 0;
    if (followLatest) activityList.scrollTop = activityList.scrollHeight;
}

function showError(message) {
    loadingOverlay.classList.remove("visible");
    submitButton.disabled = false;
    submitButton.textContent = "Start Investigation";
    progressError.textContent = message;
    progressError.hidden = false;
}

async function pollStatus(statusUrl) {
    try {
        const response = await fetch(statusUrl, {cache: "no-store"});
        if (response.status === 404) {
            window.sessionStorage.removeItem("investigationStatusUrl");
            showError("This investigation could not be found. Please start another investigation.");
            return;
        }
        if (!response.ok) throw new Error("status");
        const status = await response.json();
        progressStatus.textContent = status.message;
        renderActivity(status.events || []);
        if (status.status === "completed") {
            window.sessionStorage.removeItem("investigationStatusUrl");
            window.location.assign(status.report_url);
        } else if (status.status === "failed") {
            window.sessionStorage.removeItem("investigationStatusUrl");
            showError(status.message);
        } else {
            window.setTimeout(() => pollStatus(statusUrl), 750);
        }
    } catch (_) {
        // Keep following this run after a temporary connection problem.
        progressStatus.textContent = "Progress connection interrupted. Reconnecting…";
        window.setTimeout(() => pollStatus(statusUrl), 3000);
    }
}

function showLoading() {
    progressError.hidden = true;
    submitButton.disabled = true;
    submitButton.textContent = "Processing...";
    progressStatus.textContent = "Waiting to start";
    loadingOverlay.classList.add("visible");
}

form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (submitButton.disabled) return;
    showLoading();
    activityList.replaceChildren();
    activityIds.clear();
    activeSteps.clear();
    activityEmpty.hidden = false;
    try {
        const response = await fetch(form.dataset.startUrl, {method: "POST", body: new FormData(form)});
        const result = await response.json();
        if (!response.ok) {
            showError(result.error || "Unable to start the investigation. Please try again.");
            return;
        }
        window.sessionStorage.setItem("investigationStatusUrl", result.status_url);
        pollStatus(result.status_url);
    } catch (_) {
        showError("Unable to connect. Please check your connection and try again.");
    }
});

const savedStatusUrl = window.sessionStorage.getItem("investigationStatusUrl");
if (savedStatusUrl) {
    showLoading();
    pollStatus(savedStatusUrl);
}
