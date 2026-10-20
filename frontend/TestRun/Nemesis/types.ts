export interface NemesisTargetNode {
    name: string;
    ip: string | null;
    shards: number | null;
}

export interface NemesisInfo {
    class_name: string;
    name: string;
    duration: number;
    target_node: NemesisTargetNode;
    status: string;
    start_time: number;
    end_time: number;
    stack_trace: string;
    description_digest?: string | null;
    description?: string | null;
}

export interface NemesisResource {
    name: string;
    state: string;
    instance_info: {
        private_ip: string;
    };
}
