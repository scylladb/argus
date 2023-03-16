import { Base64 } from "js-base64";
import queryString from "query-string";

export const stateEncoder = function(rawState) {
    let state = JSON.stringify(rawState);
    let encodedState = Base64.encode(state, true);
    return encodedState;
};

export const stateDecoder = function () {
    let params = queryString.parse(document.location.search);
    let state = params.state;
    if (state) {
        let decodedState = JSON.parse(Base64.decode(state));
        return decodedState;
    }
    return [];
};
