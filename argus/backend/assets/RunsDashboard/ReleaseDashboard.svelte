<script>
    export let releaseData = {};
    import { faGithub } from "@fortawesome/free-brands-svg-icons";
    import { faBug } from "@fortawesome/free-solid-svg-icons";
    import Fa from "svelte-fa";
    import ChartStats from "./ChartStats.svelte";
    import ReleaseStats from "./ReleaseStats.svelte";
    import ReleaseActivity from "./ReleaseActivity.svelte";
    import GithubIssues from "./GithubIssues.svelte";
    import ReleaseGithubIssues from "./ReleaseGithubIssues.svelte";
</script>

<div class="container-fluid border rounded mt-1 bg-white shadow-sm">
    <div class="row mb-2">
        <div class="col-8">
            <h1 class="display-1">{releaseData.release.name}</h1>
            <h3 class="text-muted">{releaseData.release.pretty_name ?? "No name"}</h3>
            <div class="input-group user-select-all">
                <span class="input-group-text">Github</span>
                <input class="form-control" type="text" disabled value="{releaseData.release.github_repo_url}">
                <a href="{releaseData.release.github_repo_url}" target="_blank" class="btn btn-dark"><Fa icon={faGithub}/></a>
                <a href="{releaseData.release.github_repo_url}/issues/new/choose" target="_blank" class="btn btn-success"><Fa icon={faBug}/></a>
            </div>
            <p class="text-muted">
                {releaseData.release.description ?? "No description provided."}
            </p>
        </div>
    </div>
    <div class="row mb-2">
        <div class="col-4">
            <ReleaseStats releaseName={releaseData.release.name} DisplayItem={ChartStats} showTestMap={true}/>
        </div>
    </div>
    <div class="row mb-2">
        <ReleaseGithubIssues release_id={releaseData.release.id} release_name={releaseData.release.name} tests={releaseData.tests}/>
    </div>
    <div class="row mb-2">
        <ReleaseActivity releaseName={releaseData.release.name} />
    </div>
    <div class="row mb-2">
        <div class="col">
            <div class="accordion">
                <div class="accordion-item">
                    <h2 class="accordion-header">
                      <button class="accordion-button collapsed" type="button" data-bs-toggle="collapse" data-bs-target="#collapseIssues">
                        All Issues
                      </button>
                    </h2>
                    <div id="collapseIssues" class="accordion-collapse collapse">
                      <div class="accordion-body">
                        <GithubIssues id={releaseData.release.id} filter_key="release_id" submitDisabled={true}/>
                      </div>
                    </div>
                  </div>
            </div>
        </div>
    </div>
</div>
