"use strict";

function paperUrlParts(text) {
    const parts = [];
    const pattern = /https?:\/\/[^\s<>"\u201c\u201d]+/gi;
    let end = 0;
    for (const match of text.matchAll(pattern)) {
        let url = match[0].replace(/[.,;!?:]+$/, "");
        while (url.endsWith(")") && (url.match(/\)/g) || []).length > (url.match(/\(/g) || []).length) url = url.slice(0, -1);
        try { if (!new URL(url).hostname) continue; } catch (_) { continue; }
        parts.push({text: text.slice(end, match.index)}, {text: url, url});
        end = match.index + url.length;
    }
    parts.push({text: text.slice(end)});
    return parts;
}

if (typeof module !== "undefined") module.exports = {paperUrlParts};
if (typeof document !== "undefined") {
    function linkUrls(root) {
        const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
        const nodes = [];
        while (walker.nextNode()) nodes.push(walker.currentNode);
        for (const node of nodes) {
            if (!node.parentElement || node.parentElement.closest("a,script,style,textarea,input,code,pre,[contenteditable]")) continue;
            const parts = paperUrlParts(node.textContent);
            if (!parts.some(part => part.url)) continue;
            const fragment = document.createDocumentFragment();
            for (const part of parts) {
                if (!part.url) { fragment.append(document.createTextNode(part.text)); continue; }
                const link = document.createElement("a");
                link.href = part.url;
                link.textContent = part.text;
                link.target = "_blank";
                link.rel = "noopener noreferrer";
                fragment.append(link);
            }
            node.replaceWith(fragment);
        }
    }
    linkUrls(document.body);
    new MutationObserver(() => linkUrls(document.body)).observe(document.body, {childList: true, subtree: true, characterData: true});
}
