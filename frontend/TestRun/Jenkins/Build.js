import { sendMessage } from "../../Stores/AlertStore";

export const startJobBuild = async function(buildId, buildParams) {
    try {
        const params = {
            buildId: buildId,
            parameters: buildParams,
        };
        const response = await fetch("/api/v1/jenkins/clone/build", {
            headers: {
                "Content-Type": "application/json",
            },
            method: "POST",
            body: JSON.stringify(params),
        });

        const json = await response.json();
        if (json.status != "ok") {
            throw json;
        }

        return json.response.queueItem;
    } catch (error) {
        if (error?.status === "error") {
            sendMessage(
                "error",
                `API Error when starting build.\nMessage: ${error.response.arguments[0]}`,
                "Build::startJobBuild"
            );
        } else {
            sendMessage(
                "error",
                "A backend error occurred attempting to start a build",
                "Build::startJobBuild"
            );
            console.log(error);
        }
    }
};
