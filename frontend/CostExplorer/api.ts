import { fetchJson } from "../Common/ApiUtils";
import { apiParams } from "./filters";
import type { ExplorerFilters, ExplorerResponse, NamedEntity } from "./types";

export const loadExplorer = (filters: ExplorerFilters): Promise<ExplorerResponse> =>
    fetchJson(`/api/v1/cost/explorer?${apiParams(filters).toString()}`);

export const loadReleases = (): Promise<NamedEntity[]> => fetchJson("/api/v1/releases");

export const loadGroups = (releaseId: string): Promise<NamedEntity[]> =>
    fetchJson(`/api/v1/groups?releaseId=${encodeURIComponent(releaseId)}`);

export const loadTests = (groupId: string): Promise<NamedEntity[]> =>
    fetchJson(`/api/v1/tests?groupId=${encodeURIComponent(groupId)}`);

export const displayName = (entity: NamedEntity): string => entity.pretty_name || entity.name;
