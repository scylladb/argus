
import StatsFetcher from "./Stats/StatsFetcher.svelte";

const registeredApps = [];
const releaseElements = document.querySelectorAll("div.release-card");

// disabled due to performance overhead
// releaseElements.forEach(el => {
//     let app = new StatsFetcher({
//         target: el.querySelector("div.release-stats"),
//         props: {
//             releaseName: el.dataset.argusReleaseName
//         }
//     });
//     registeredApps.push(app);
// });
