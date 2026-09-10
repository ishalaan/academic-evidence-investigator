"use strict";

const tablist = document.getElementById("report-tabs");
const tabs = Array.from(tablist.querySelectorAll('[role="tab"]'));
function selectTab(selected, focus = false) {
    tabs.forEach((tab) => {
        const active = tab === selected;
        tab.setAttribute("aria-selected", String(active));
        tab.tabIndex = active ? 0 : -1;
        document.getElementById(tab.getAttribute("aria-controls")).hidden = !active;
    });
    if (focus) selected.focus();
}
tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => selectTab(tab));
    tab.addEventListener("keydown", (event) => {
        let next;
        if (event.key === "ArrowRight") next = tabs[(index + 1) % tabs.length];
        if (event.key === "ArrowLeft") next = tabs[(index + tabs.length - 1) % tabs.length];
        if (event.key === "Home") next = tabs[0];
        if (event.key === "End") next = tabs[tabs.length - 1];
        if (next) { event.preventDefault(); selectTab(next, true); }
    });
});
tablist.hidden = false;
selectTab(tabs[0]);
