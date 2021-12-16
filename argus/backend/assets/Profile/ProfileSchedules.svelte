<script>
    export let schedules = [];

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
                        <ul class="list-group">
                            {#each schedule.tests as test}
                                <li class="list-group-item">{test}</li>
                            {/each}
                        </ul>
                    </div>
                </div>
                <div class="" class:d-none={schedule.groups.length == 0}>
                    <h5>Groups</h5>
                    <div>
                        <ul class="list-group">
                            {#each schedule.groups as group}
                                <li class="list-group-item">{group}</li>
                            {/each}
                        </ul>
                    </div>
                </div>
            </div>
        </div>
    {/each}
</div>
