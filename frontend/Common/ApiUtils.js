import { sendMessage } from "../Stores/AlertStore";

export const apiMethodCall = async function (endpoint, body, method = "POST") {
    try {
        let apiResponse = await fetch(endpoint, {
            method: method,
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify(body),
        });
        let res = await apiResponse.json();
        if (res.status === "ok") {
            return res;
        } else {
            throw res;
        }
    } catch (error) {
        if (error?.status === "error") {
            sendMessage(
                "error",
                `API Error.\nMessage: ${error.response.arguments[0]}`,
                "apiMethodCall"
            );
        } else {
            sendMessage(
                "error",
                "Unhandled API Error occured. \nCheck console for details.",
                "apiMethodCall"
            );
            console.log(error);
        }
    } finally {

    }
};
