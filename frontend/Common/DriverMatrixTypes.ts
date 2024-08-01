export interface TestCase {
    name: string;
    status: string;
    time: number;
    classname: string;
    message: string;
}

export interface TestSuite {
    name: string;
    tests_total: number;
    failures: number;
    disabled: number;
    skipped: number;
    passed: number;
    errors: number;
    time: number;
    cases: Array<TestCase>;
}

export interface TestCollection {
    name: string;
    driver: string;
    failure_message: string;
    tests_total: number;
    failures: number;
    disabled: number;
    skipped: number;
    passed: number;
    errors: number;
    time: number;
    timestamp: Date;
    suites: Array<TestSuite>;
}
