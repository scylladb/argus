export type PlanOptions = Record<string, { labels?: string[] }>;

export interface OptionsDiff {
    options_set: PlanOptions;
    options_remove: string[];
}

export interface LabelCount {
    label: string;
    count: number;
}

export interface PlanLabelOption {
    key: string;
    planId: string;
    planName: string;
    label: string;
}

export interface LabelledPlan {
    id: string;
    name: string;
    options: PlanOptions;
}

export function parseOptions(options: string | PlanOptions | null | undefined): PlanOptions {
    if (!options) return {};
    if (typeof options !== "string") return structuredClone(options);
    try {
        const parsed = JSON.parse(options);
        return parsed && typeof parsed === "object" ? parsed : {};
    } catch {
        return {};
    }
}

function unique(labels: string[]): string[] {
    const seen = new Set<string>();
    return labels.filter((label) => {
        const key = label.toLowerCase();
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
    });
}

export function labelsOf(options: PlanOptions, testId: string, groupId?: string): string[] {
    return unique([...(options[testId]?.labels ?? []), ...(groupId ? options[groupId]?.labels ?? [] : [])]);
}

export function addLabel(options: PlanOptions, id: string, label: string): PlanOptions | string {
    const trimmed = label.trim();
    if (!trimmed) return "A label cannot be empty";
    const current = options[id]?.labels ?? [];
    if (current.some((existing) => existing.toLowerCase() === trimmed.toLowerCase())) {
        return `The label ${trimmed} is already there`;
    }
    return { ...options, [id]: { ...options[id], labels: [...current, trimmed] } };
}

export function removeLabel(options: PlanOptions, id: string, label: string): PlanOptions {
    const remaining = (options[id]?.labels ?? []).filter((existing) => existing !== label);
    const { [id]: _removed, ...rest } = options;
    return remaining.length ? { ...rest, [id]: { ...options[id], labels: remaining } } : rest;
}

export function dropEntity(options: PlanOptions, id: string): PlanOptions {
    const { [id]: _removed, ...rest } = options;
    return rest;
}

export function optionsDiff(original: PlanOptions, current: PlanOptions): OptionsDiff {
    const options_set: PlanOptions = {};
    for (const [id, option] of Object.entries(current)) {
        if (!option.labels?.length) continue;
        if (JSON.stringify(original[id]?.labels ?? []) !== JSON.stringify(option.labels)) {
            options_set[id] = option;
        }
    }
    const options_remove = Object.keys(original).filter((id) => !current[id]?.labels?.length);
    return { options_set, options_remove };
}

export function labelCounts(options: PlanOptions, testsOfGroup: (groupId: string) => number = () => 1): LabelCount[] {
    const counts = new Map<string, number>();
    for (const [id, option] of Object.entries(options)) {
        for (const label of option.labels ?? []) {
            counts.set(label, (counts.get(label) ?? 0) + testsOfGroup(id));
        }
    }
    return [...counts.entries()]
        .map(([label, count]) => ({ label, count }))
        .sort((a, b) => a.label.localeCompare(b.label));
}

export function matchesLabels(labels: string[], selected: string[]): boolean {
    if (!selected.length) return true;
    const lowered = new Set(labels.map((label) => label.toLowerCase()));
    return selected.some((label) => lowered.has(label.toLowerCase()));
}

export function planLabelOptions(plans: LabelledPlan[]): PlanLabelOption[] {
    return plans.flatMap((plan) =>
        labelCounts(plan.options).map(({ label }) => ({
            key: `${plan.id}:${label}`,
            planId: plan.id,
            planName: plan.name,
            label,
        })),
    );
}

export interface PlanLabelSelection {
    planId: string;
    label: string;
}

function selectedPlan(plans: LabelledPlan[], selection: PlanLabelSelection | undefined): LabelledPlan | undefined {
    const plan = selection && plans.find((candidate) => candidate.id === selection.planId);
    return plan && labelCounts(plan.options).some(({ label }) => label === selection.label) ? plan : undefined;
}

export function planLabelAvailable(plans: LabelledPlan[], selection: PlanLabelSelection | undefined): boolean {
    return selectedPlan(plans, selection) !== undefined;
}

export function planLabelsOfTest(
    plans: LabelledPlan[],
    selection: PlanLabelSelection | undefined,
    testId: string,
    groupId?: string,
): string[] {
    const plan = selectedPlan(plans, selection);
    return plan ? labelsOf(plan.options, testId, groupId) : [];
}

export function planLabelMatches(
    plans: LabelledPlan[],
    selection: PlanLabelSelection | undefined,
    testId: string,
    groupId?: string,
): boolean {
    if (!selection || !planLabelAvailable(plans, selection)) return true;
    return matchesLabels(planLabelsOfTest(plans, selection, testId, groupId), [selection.label]);
}
