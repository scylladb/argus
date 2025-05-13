/**
 * @typedef {Object} NodeStatus
 * @property {string} ip
 * @property {string} node_type
 * @property {integer} status
 * @property {any} response
 */

/**
 * @typedef {Object} ScyllaStatusResponse
 * @property {string} key
 * @property {string} value
 */

/**
 * @typedef {Object} ArgusStatus
 * @property {string} time
 * @property {NodeStatus[]} statuses
 */

const TEMPLATE_SCYLLA_NODE = `
<div class="col-md-4 col-sm-12">
<div class="p-2 m-1 shadow-sm rounded">
    <div class="fw-500 fs-5 d-flex">
        <div class="ps-1">
            Scylla Node
            <div class="" style="font-weight: 200; font-size:0.75em;">
                {{ip}}
            </div>
        </div>
        <div class="ms-auto">{{status}} <i class="fa-solid fa-circle text-{{statusColor}}"></i></div>
    </div>
    <div class="d-flex align-items-center">
        <div><img class="logo" src="static/scylla.png" alt="Scylla"></div>
        <div class="ms-auto">
            <div class="border-bottom fw-bold text-end">Network</div>
            <div class="fs-6 text-end">
                {{nodeCommunication}}
            </div>
        </div>
    </div>
</div>
</div>
`;

const TEMPLATE_SCYLLA_REPORT = `
<div>{{node}}: {{status}} <i class="fa-solid fa-circle text-{{statusColor}}"></i></div>
`;

const TEMPLATE_ERROR_MESSAGE = `
<div class="my-2 rounded p-2" style="background-color: #f0f0f0"><pre style='white-space: pre-wrap; max-height: 512px; max-width: 256px; overflow-y: scroll'>{{message}}</pre></div>
`;

/**
 * @param {string} template
 * @param {{ [string]: any }} substitutions
 */
const format = function(template, substitutions) {
    let renderedTemplate = template;
    Object.entries(substitutions).forEach(([key, value]) => {
        let searchRegexp = new RegExp(`\{\{(\s*)?${key}(\s*)?\}\}`, "g");
        renderedTemplate = renderedTemplate.replace(searchRegexp, value);
    });

    return renderedTemplate;
};

const StatusPage = {
    /**
     * @type {ArgusStatus | undefined}
     */
    status: undefined,
    statusMap: {
        200: "success",
        300: "dark",
        400: "warning",
        500: "danger",
    },
    statusText: {
        200: "UP",
        300: "UNKNOWN",
        400: "FAILING",
        500: "DOWN",
    },
    nodeStatusMap: {
        "UP": "success",
        "DOWN": "danger",
        "UNKNOWN": "warning",
    },
    PLACEHOLDER: document.querySelector("#placeholder"),
    ERRORS: document.querySelector("#errors"),
    STATUS_BLOCK: document.querySelector("#status"),
    TIME_DIV: document.querySelector("#statusTime"),
    /**
     * Fetch current status
     * @returns {ArgusStatus}
     */
    loadStatus: async function() {
        let res = await fetch("status.json");
        if (res.status != 200) return Promise.reject("HTTP Transport Error");
        try {
            let json = await res.json();
            return json;
        } catch {
            return Promise.reject("Error parsing status json.");
        }
    },

    init: async function() {
        try {
            this.status = await this.loadStatus();
        } catch (e) {
            console.log(e);
            this.ERRORS.innerText = e.message ?? e;
            this.ERRORS.classList.remove("d-none");
            this.PLACEHOLDER.classList.add("d-none");
            return;
        }

        let timestamp = Date.parse(this.status.time);
        let date = dayjs.unix(timestamp / 1000).format("YYYY-MM-DD H:mm");
        this.TIME_DIV.innerText = date;
        this.setupArgusStatus(this.status.statuses.find(val => val.node_type == "argus"));
        this.setupScyllaStatus(this.status.statuses.filter(val => val.node_type == "scylla"));
        this.PLACEHOLDER.classList.add("d-none");
        this.STATUS_BLOCK.classList.remove("d-none");
        console.log("Status Ready.");
    },

    /**
     * @param {NodeStatus} status
     */
    setupArgusStatus: function(status) {
        let argusStatusField = this.STATUS_BLOCK.querySelector("#argusStatusField");
        let argusStatusIcon = this.STATUS_BLOCK.querySelector("#argusStatusIcon");
        let argusStatusIp = this.STATUS_BLOCK.querySelector("#argusStatusIp");
        let argusCommitId = this.STATUS_BLOCK.querySelector("#commitId");

        argusStatusField.innerText = this.resolveTextStatus(status.status);
        argusStatusIcon.classList.add(`text-${this.resolveStatus(status.status)}`);
        argusStatusIp.innerText = status.ip;
        argusCommitId.innerText = status.response?.response?.commit_id ?? "#ERROR";
    },

    /**
     * @param {NodeStatus[]} statuses
     */
    setupScyllaStatus: function(statuses) {
        let renderedStatuses = statuses.map((status) => {
            /** @type {ScyllaStatusResponse[]} */
            let response = status.response;
            let renderedResponses = [];
            if (typeof response == "object" && response.map) {
                renderedResponses = response.map((val) => {
                    return format(TEMPLATE_SCYLLA_REPORT, {
                        node: val.key,
                        status: val.value,
                        statusColor: this.resolveNodeStatus(val.value),
                    });
                });
            } else {
                renderedResponses = [format(TEMPLATE_ERROR_MESSAGE, { message: typeof response == "string" ? response : JSON.stringify(response, undefined, 1) })];
            }
            let renderedStatus = format(TEMPLATE_SCYLLA_NODE, {
                ip: status.ip,
                status: this.resolveTextStatus(status.status),
                statusColor: this.resolveStatus(status.status),
                nodeCommunication: renderedResponses.join("\n"),
            });

            return renderedStatus;
        });

        let scyllaStatusBlock = document.querySelector("#scyllaNodes");
        scyllaStatusBlock.innerHTML = renderedStatuses.join("\n");
    },

    /**
     * @param {number} status
     */
    resolveStatus: function(status) {
        let category = Math.floor(status/100)*100;
        return this.statusMap[category] ?? this.statusMap[500];
    },

    /**
     * @param {number} status
     */
    resolveTextStatus: function(status) {
        let category = Math.floor(status/100)*100;
        return this.statusText[category] ?? this.statusText[500];
    },

    /**
     * @param {string} status
     * @returns {string}
     */
    resolveNodeStatus: function(status) {
        return this.nodeStatusMap[status] ?? this.nodeStatusMap.UNKNOWN;
    },
};

document.addEventListener("DOMContentLoaded", StatusPage.init())
