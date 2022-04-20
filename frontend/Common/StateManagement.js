import { Base64 } from "js-base64";

export const stateEncoder = function(rawState) {
    let state = JSON.stringify(rawState);
    let encodedState = Base64.encode(state, true);
    return `state=${encodedState}`;
};

export const stateDecoder = function () {
    let params = new URLSearchParams(document.location.search);
    let state = params.get("state");
    if (state) {
        let decodedState = JSON.parse(Base64.decode(state));
        return decodedState;
    }
    return {};
}
