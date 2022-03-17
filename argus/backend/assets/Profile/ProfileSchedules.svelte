<script>
    export let schedules = [];
    import Fa from "svelte-fa";
    import { faExternalLinkAlt, faTasks } from "@fortawesome/free-solid-svg-icons";
    import { stateEncoder } from "../Common/StateManagement";

    const sortByStartTime = function () {
        return [...schedules].sort((a, b) => {
            let leftDate = new Date(a.period_start);
            let rightDate = new Date(b.period_start);
            if (leftDate > rightDate) {
                return 1;
            } else if (rightDate > leftDate) {
                return -1;
            }
            return 0;
        });
    };

    const prepareState = function(schedule) {
        return schedule.tests.reduce((acc, scheduledTest) => {
            let [group, test] = scheduledTest.split("/");
            let release = schedule.release;
            acc[`${release}/${group}/${test}`] = {
                release: release,
                group: group,
                test: test,
            };
            return acc;
        }, {});
    };

</script>

<div class="row p-2 justify-content-center">
    {#each sortByStartTime() as schedule}
        <div class="col-3 border rounded bg-white shadow-sm mb-2 p-2 me-2">
            <div class="d-flex flex-column text-center">
                <div class="border-bottom">
                    <h5>Release</h5>
                    <div>{schedule.release}</div>
                </div>
                <div class="border-bottom">
                    <h5>From</h5>
                    <div class="text-danger">
                        {new Date(schedule.period_start).toLocaleDateString(
                            "en-CA"
                        )}
                    </div>
                </div>
                <div class="border-bottom">
                    <h5>To</h5>
                    <div class="text-success">
                        {new Date(schedule.period_end).toLocaleDateString(
                            "en-CA"
                        )}
                    </div>
                </div>
                <div
                    class="border-bottom"
                    class:d-none={schedule.tests.length == 0}
                >
                    <h5>Tests</h5>
                    <div>
                        <div class="mb-1 text-start">
                            <a
                                href="/run_dashboard?{stateEncoder(prepareState(schedule))}"
                                class="btn btn-sm btn-outline-primary"
                            >
                                Open Workspace <Fa icon={faTasks}/>
                            </a>
                        </div>
                        <ul class="list-group">
                            {#each schedule.tests as test}
                                <li class="list-group-item text-start">
                                    <div>
                                        {test}
                                        <div class="">
                                            <a
                                                target="_blank"
                                                href="https://jenkins.scylladb.com/job/{schedule.release}/job/{test.split(
                                                    '/'
                                                )[0]}/job/{test.split('/')[1]}"
                                                class="btn btn-sm btn-outline-dark"
                                                >To Jenkins <Fa
                                                    icon={faExternalLinkAlt}
                                                /></a
                                            >
                                        </div>
                                    </div>
                                </li>
                            {/each}
                        </ul>
                    </div>
                </div>
                <div class="" class:d-none={schedule.groups.length == 0}>
                    <h5>Groups</h5>
                    <div>
                        <ul class="list-group">
                            {#each schedule.groups as group}
                                <li class="list-group-item text-start">
                                    {group}
                                    <div class="">
                                        <a
                                            target="_blank"
                                            href="https://jenkins.scylladb.com/job/{schedule.release}/job/{group}"
                                            class="btn btn-dark btn-outline"
                                            >Jenkins <Fa
                                                icon={faExternalLinkAlt}
                                            /></a
                                        >
                                    </div>
                                </li>
                            {/each}
                        </ul>
                    </div>
                </div>
            </div>
        </div>
    {/each}
</div>
